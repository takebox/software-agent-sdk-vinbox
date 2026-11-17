from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from handprint.sdk.launch.errors import (
    AgentLaunchError,
    LaunchStoreError,
    UnresolvedProfileReferences,
)
from handprint.sdk.llm.meta_profile_store import MetaProfile
from handprint.sdk.mcp.config import MCPServer
from handprint.sdk.profiles.agent_profile import (
    ACPAgentProfile,
    LaunchedAgentProfile,
    HandprintAgentProfile,
)
from handprint.sdk.profiles.resolver import (
    ProfileNotFound,
    _apply_disabled_tracks,
    _build_acp_settings,
    _build_handprint_settings,
    _compute_mcp_filter,
)
from handprint.sdk.settings.model import ACPAgentSettings, HandprintAgentSettings
from handprint.sdk.tracks import Track


if TYPE_CHECKING:
    from handprint.sdk.llm.llm import LLM
    from handprint.sdk.llm.llm_profile_store import LLMProfileLoader
    from handprint.sdk.utils.cipher import Cipher


class AgentProfileLoader(Protocol):
    def name_for_id(self, profile_id: str | UUID) -> str | None: ...

    def load(self, name: str) -> HandprintAgentProfile | ACPAgentProfile: ...


class MetaProfileLoader(Protocol):
    def load(self, name: str) -> MetaProfile: ...


@dataclass(frozen=True, kw_only=True)
class LaunchStores:
    """The stores a launch reads, as seen by the process that holds them."""

    llm_profiles: LLMProfileLoader
    mcp_config: Mapping[str, MCPServer]
    tracks: Callable[[], Sequence[Track]]
    agent_profiles: AgentProfileLoader | None = None
    meta_profiles: MetaProfileLoader | None = None
    llm_profile_names: Callable[[], Sequence[str]] | None = None
    cipher: Cipher | None = None


@dataclass(frozen=True)
class ResolvedLaunch:
    """Reference-free agent settings plus the provenance of the launch."""

    settings: HandprintAgentSettings | ACPAgentSettings
    profile: LaunchedAgentProfile | None = None

    @property
    def allowed_secrets(self) -> frozenset[str] | None:
        if self.profile is None or self.profile.secret_refs is None:
            return None
        return frozenset(self.profile.secret_refs)


AgentProfileSource = UUID | HandprintAgentProfile | ACPAgentProfile


def resolve(source: AgentProfileSource, stores: LaunchStores) -> ResolvedLaunch:
    """Resolve a stored profile id or a profile into a ``ResolvedLaunch``.

    Every reference is copied into the result, so the runtime that finalizes it
    needs no store. All dangling references are raised together as
    :class:`UnresolvedProfileReferences`; a store that cannot be read raises
    :class:`LaunchStoreError`; an unknown profile id raises ``ProfileNotFound``.
    """
    profile = (
        _load_stored_profile(source, stores) if isinstance(source, UUID) else source
    )
    mcp_config, _, dangling_mcp = _compute_mcp_filter(
        dict(stores.mcp_config), profile.mcp_server_refs
    )
    catalog = _load_tracks(stores)
    if isinstance(profile, ACPAgentProfile):
        if dangling_mcp:
            raise UnresolvedProfileReferences(mcp_server_refs=dangling_mcp)
        try:
            settings = _build_acp_settings(
                profile, mcp_config, _apply_disabled_tracks(catalog, [])
            )
        except ValueError as exc:
            raise AgentLaunchError(str(exc)) from exc
    else:
        settings = _resolve_handprint(
            profile, stores, mcp_config, catalog, dangling_mcp
        )
    if not isinstance(settings, HandprintAgentSettings | ACPAgentSettings):
        raise AgentLaunchError(f"Unsupported agent kind {settings.agent_kind!r}")
    return ResolvedLaunch(
        settings=settings,
        profile=LaunchedAgentProfile(
            agent_profile_id=profile.id,
            revision=profile.revision,
            secret_refs=profile.secret_refs,
        ),
    )


def _resolve_handprint(
    profile: HandprintAgentProfile,
    stores: LaunchStores,
    mcp_config: dict[str, MCPServer],
    catalog: list[Track],
    dangling_mcp: list[str],
) -> HandprintAgentSettings | ACPAgentSettings:
    llm = _load_llm(stores, profile.llm_profile_ref)
    meta_profile, meta_llms, dangling_meta, dangling_meta_llms = _load_meta_profile(
        profile, stores
    )
    if llm is None or dangling_mcp or dangling_meta or dangling_meta_llms:
        raise UnresolvedProfileReferences(
            llm_profile_ref=profile.llm_profile_ref if llm is None else None,
            mcp_server_refs=dangling_mcp,
            meta_profile_ref=dangling_meta,
            meta_profile_llm_refs=dangling_meta_llms,
        )
    try:
        return _build_handprint_settings(
            profile,
            # A profile cannot express streaming; LLM degrades to non-streaming
            # when the runtime wires no token callback.
            llm.model_copy(update={"stream": True}),
            mcp_config,
            _apply_disabled_tracks(catalog, profile.disabled_tracks),
            browser_available=None,
            meta_profile=meta_profile,
            meta_profile_llms=meta_llms,
        )
    except ValueError as exc:
        raise AgentLaunchError(str(exc)) from exc


def _load_stored_profile(
    profile_id: UUID, stores: LaunchStores
) -> HandprintAgentProfile | ACPAgentProfile:
    if stores.agent_profiles is None:
        raise ProfileNotFound(f"Agent profile with id '{profile_id}' not found")
    try:
        name = stores.agent_profiles.name_for_id(profile_id)
        if name is None:
            raise ProfileNotFound(f"Agent profile with id '{profile_id}' not found")
        return stores.agent_profiles.load(name)
    except ProfileNotFound:
        raise
    except FileNotFoundError as exc:
        raise ProfileNotFound(
            f"Agent profile with id '{profile_id}' not found"
        ) from exc
    except TimeoutError as exc:
        raise LaunchStoreError("Agent profile store is busy", retryable=True) from exc
    except (OSError, ValueError) as exc:
        raise LaunchStoreError(f"Could not load agent profile: {exc}") from exc


def _load_tracks(stores: LaunchStores) -> list[Track]:
    try:
        return list(stores.tracks())
    except Exception as exc:
        raise LaunchStoreError(f"Track discovery failed: {exc}") from exc


def _load_llm(stores: LaunchStores, name: str) -> LLM | None:
    from handprint.sdk.llm.provider_connection_store import ProviderConnectionNotFound

    try:
        return stores.llm_profiles.load(name, cipher=stores.cipher)
    except FileNotFoundError:
        return None
    except ProviderConnectionNotFound as exc:
        raise AgentLaunchError(f"LLM profile {name!r}: {exc}") from exc
    except TimeoutError as exc:
        raise LaunchStoreError("LLM profile store is busy", retryable=True) from exc
    except (OSError, ValueError) as exc:
        raise LaunchStoreError(f"Could not load LLM profile {name!r}: {exc}") from exc


def _load_meta_profile(
    profile: HandprintAgentProfile, stores: LaunchStores
) -> tuple[MetaProfile | None, dict[str, LLM], str | None, list[str]]:
    name = profile.meta_profile_ref
    if not profile.enable_classify_and_switch_llm_tool or name is None:
        return None, {}, None, []
    if stores.meta_profiles is None:
        return None, {}, name, []
    try:
        meta = stores.meta_profiles.load(name)
    except FileNotFoundError:
        return None, {}, name, []
    except TimeoutError as exc:
        raise LaunchStoreError("Meta-profile store is busy", retryable=True) from exc
    except (OSError, ValueError) as exc:
        raise LaunchStoreError(f"Could not load meta-profile {name!r}: {exc}") from exc

    llms: dict[str, LLM] = {}
    dangling: list[str] = []
    refs = [meta.classifier_model, *(cls.model for cls in meta.classes)]
    for ref in dict.fromkeys(refs):
        llm = _load_llm(stores, ref)
        if llm is None:
            dangling.append(ref)
        else:
            llms[ref] = llm
    if meta.prompt_template is not None and stores.llm_profile_names is not None:
        try:
            names = stores.llm_profile_names()
        except TimeoutError as exc:
            raise LaunchStoreError("LLM profile store is busy", retryable=True) from exc
        except OSError as exc:
            raise LaunchStoreError(f"Could not list LLM profiles: {exc}") from exc
        # Direct routing may pick any saved LLM profile, so an unreadable one
        # that the meta-profile does not name is skipped rather than fatal.
        for ref in names:
            if ref in llms:
                continue
            try:
                llm = _load_llm(stores, ref)
            except (AgentLaunchError, LaunchStoreError):
                continue
            if llm is not None:
                llms[ref] = llm
    return meta, llms, None, dangling
