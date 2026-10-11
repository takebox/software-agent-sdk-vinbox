"""Tracks service for Handprint Agent Server.

This module contains the business logic for track loading and management,
keeping the router clean and focused on HTTP concerns.

Track Sources:
- Public tracks: registered marketplace plugins or GitHub Handprint/extensions
- User tracks: ~/.handprint/tracks/ and ~/.handprint/microagents/
- Project tracks: {workspace}/.handprint/tracks/, .cursorrules, agents.md
- Organization tracks: {org}/.handprint or {org}/handprint-config
- Sandbox tracks: Exposed URLs from sandbox environment

Precedence (later overrides earlier):
sandbox < registered marketplace/public < user < org < project
"""

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from pydantic import BaseModel, ValidationError

from handprint.sdk.logger import get_logger
from handprint.sdk.marketplace import Marketplace
from handprint.sdk.marketplace.registration import MarketplaceRegistration
from handprint.sdk.marketplace.registry import MarketplaceRegistry
from handprint.sdk.plugin import Plugin
from handprint.sdk.tracks import (
    InstalledTrackInfo,
    Track,
    disable_track,
    enable_track,
    get_installed_track,
    install_track,
    list_installed_tracks,
    load_available_tracks,
    load_marketplace_standalone_tracks,
    uninstall_track,
    update_track,
)
from handprint.sdk.tracks.track import (
    DEFAULT_MARKETPLACE_PATH,
    PUBLIC_TRACKS_REF,
    PUBLIC_TRACKS_REPO,
    _invalidate_public_tracks_cache,
    load_tracks_from_dir,
)
from handprint.sdk.tracks.utils import (
    get_tracks_cache_dir,
    update_tracks_repository,
)
from handprint.sdk.utils import sanitized_env
from handprint.sdk.utils.path import to_posix_path


logger = get_logger(__name__)


# Content template for sandbox work hosts track
WORK_HOSTS_TRACK_CONTENT = (
    "The user has access to the following hosts for accessing "
    "a web application, each of which has a corresponding port:\n{hosts}"
)

# Prefix for sandbox URLs that should be exposed as work_hosts track.
# URLs with names starting with this prefix represent web applications
# or services running in the sandbox that the agent should be aware of.
SANDBOX_WORKER_URL_PREFIX = "WORKER_"


@dataclass
class ExposedUrlData:
    """Internal representation of an exposed URL from the sandbox."""

    name: str
    url: str
    port: int


@dataclass
class TrackLoadResult:
    """Result of loading tracks from all sources."""

    tracks: list[Track]
    sources: dict[str, int]


def load_org_tracks_from_url(
    org_repo_url: str,
    org_name: str,
    working_dir: str | Path | None = None,
) -> list[Track]:
    """Load tracks from an organization repository.

    This function clones an organization-level tracks repository to a temporary
    directory, loads tracks from the tracks/ and microagents/ directories, and
    then cleans up the temporary directory.

    The org_repo_url should be a pre-authenticated Git URL (e.g., containing
    credentials or tokens) as provided by the app-server.

    Note:
        This is a blocking I/O operation that may take up to 120 seconds due to
        the git clone timeout. When called from FastAPI endpoints defined with
        `def` (not `async def`), FastAPI automatically runs this in a thread
        pool to avoid blocking the event loop. Do not call this function
        directly from async code without wrapping it in asyncio.to_thread().

    Args:
        org_repo_url: Pre-authenticated Git URL for the organization repository.
            This should be a full Git URL that includes authentication.
        org_name: Name of the organization (used for temp directory naming).
        working_dir: Optional working directory for git operations. If None,
            uses a subdirectory of the system temp directory.

    Returns:
        List of Track objects loaded from the organization repository.
        Returns empty list if the repository doesn't exist or loading fails.
    """
    all_tracks: list[Track] = []

    # Determine a unique temporary directory for cloning. Two repos can share
    # the same org_name (e.g. {login}/.handprint and {login}/.agents), and
    # concurrent conversations may clone the same org, so the directory must be
    # unique per call rather than derived solely from org_name.
    if working_dir:
        base_dir = Path(working_dir) if isinstance(working_dir, str) else working_dir
        base_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(
            tempfile.mkdtemp(prefix=f"_org_tracks_{org_name}_", dir=base_dir)
        )
    else:
        temp_dir = Path(tempfile.mkdtemp(prefix=f"handprint_org_tracks_{org_name}_"))

    try:
        # Clone the organization repository (shallow clone for efficiency)
        logger.info(f"Cloning organization tracks repository for {org_name}")
        try:
            env = sanitized_env()
            env["GIT_TERMINAL_PROMPT"] = "0"
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    org_repo_url,
                    str(temp_dir),
                ],
                check=True,
                capture_output=True,
                timeout=120,
                env=env,
            )
        except subprocess.CalledProcessError:
            # Repository doesn't exist or access denied - this is expected.
            # Note: We intentionally don't log stderr as it may contain credentials.
            logger.debug(
                f"Organization repository not found or access denied for {org_name}"
            )
            return all_tracks
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Git clone timed out for organization repository {org_name}"
            )
            return all_tracks

        logger.debug(f"Successfully cloned org repository to {temp_dir}")

        # Load tracks from tracks/ directory (preferred)
        tracks_dir = temp_dir / "tracks"
        if tracks_dir.exists():
            try:
                repo_tracks, knowledge_tracks, agent_tracks = load_tracks_from_dir(
                    tracks_dir
                )
                for tracks_dict in [repo_tracks, knowledge_tracks, agent_tracks]:
                    all_tracks.extend(tracks_dict.values())
                logger.debug(
                    f"Loaded {len(all_tracks)} tracks from org tracks/ directory"
                )
            except Exception as e:
                logger.warning(f"Failed to load tracks from {tracks_dir}: {e}")

        # Load tracks from microagents/ directory (legacy support)
        microagents_dir = temp_dir / "microagents"
        if microagents_dir.exists():
            seen_names = {s.name for s in all_tracks}
            try:
                repo_tracks, knowledge_tracks, agent_tracks = load_tracks_from_dir(
                    microagents_dir
                )
                for tracks_dict in [repo_tracks, knowledge_tracks, agent_tracks]:
                    for name, track in tracks_dict.items():
                        if name not in seen_names:
                            all_tracks.append(track)
                            seen_names.add(name)
                        else:
                            logger.debug(
                                f"Skipping duplicate org track '{name}' "
                                "from microagents/"
                            )
            except Exception as e:
                logger.warning(f"Failed to load tracks from {microagents_dir}: {e}")

        logger.info("Loaded %d organization tracks for %s", len(all_tracks), org_name)

    except Exception as e:
        logger.warning(f"Failed to load organization tracks for {org_name}: {e}")

    finally:
        # Clean up the temporary directory
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temp directory {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")

    return all_tracks


def create_sandbox_track(
    exposed_urls: list[ExposedUrlData],
) -> Track | None:
    """Create a track from sandbox exposed URLs.

    This function creates a track that informs the agent about web applications
    and services available in the sandbox environment via exposed ports/URLs.

    Only URLs with names starting with SANDBOX_WORKER_URL_PREFIX are included,
    as these represent web applications the agent should be aware of.

    Args:
        exposed_urls: List of ExposedUrlData objects containing name, url, and port.

    Returns:
        A Track object with work_hosts content if there are matching URLs,
        or None if no relevant URLs are provided.
    """
    if not exposed_urls:
        return None

    # Filter for URLs with the worker prefix
    worker_urls = [
        url for url in exposed_urls if url.name.startswith(SANDBOX_WORKER_URL_PREFIX)
    ]

    if not worker_urls:
        return None

    # Build the hosts content
    hosts_lines = []
    for url_info in worker_urls:
        hosts_lines.append(f"* {url_info.url} (port {url_info.port})")

    hosts_content = "\n".join(hosts_lines)
    content = WORK_HOSTS_TRACK_CONTENT.format(hosts=hosts_content)

    return Track(
        name="work_hosts",
        content=content,
        trigger=None,  # Always active
        source=None,  # Programmatically generated
    )


def merge_tracks(track_lists: list[list[Track]]) -> list[Track]:
    """Merge multiple track lists with precedence.

    Later lists override earlier lists for duplicate names.

    Args:
        track_lists: List of track lists to merge in order of precedence.

    Returns:
        Merged list of tracks with duplicates resolved.
    """
    tracks_by_name: dict[str, Track] = {}

    for track_list in track_lists:
        for track in track_list:
            if track.name in tracks_by_name:
                logger.info(
                    f"Overriding track '{track.name}' from earlier source "
                    "with later source"
                )
            tracks_by_name[track.name] = track

    return list(tracks_by_name.values())


def load_registered_marketplace_tracks(
    registered_marketplaces: list[MarketplaceRegistration],
) -> list[Track]:
    """Load tracks from auto-load plugins and standalone tracks in marketplaces."""
    if not registered_marketplaces:
        return []

    registry = MarketplaceRegistry(registered_marketplaces)
    all_tracks: list[Track] = []
    for registration in registry.get_auto_load_registrations():
        try:
            marketplace, marketplace_path = registry.get_marketplace(registration.name)
        except Exception:
            logger.warning(
                "Failed to load marketplace '%s'; continuing without it",
                registration.name,
                exc_info=True,
            )
            continue

        # Standalone tracks first: the tier is merged last-wins, so appending
        # plugins after lets a plugin win over a same-named standalone track —
        # matching the catalog's plugin-over-standalone rule.
        all_tracks.extend(
            load_marketplace_standalone_tracks(
                marketplace, marketplace_path, registration
            )
        )

        for entry in marketplace.plugins:
            if not registration.auto_loads_plugin(entry.name):
                continue
            try:
                source, ref, repo_path = marketplace.resolve_plugin_source(entry)
                plugin_path = Plugin.fetch(
                    source=source,
                    ref=ref,
                    repo_path=repo_path,
                )
                all_tracks.extend(Plugin.load(plugin_path).get_all_tracks())
            except Exception:
                logger.warning(
                    "Failed to load plugin '%s' from marketplace '%s'",
                    entry.name,
                    registration.name,
                    exc_info=True,
                )
    return all_tracks


def load_all_tracks(
    load_public: bool = True,
    load_user: bool = True,
    load_project: bool = True,
    load_org: bool = True,
    project_dir: str | None = None,
    org_repos: list[tuple[str, str]] | None = None,
    sandbox_exposed_urls: list[ExposedUrlData] | None = None,
    marketplace_path: str | None = DEFAULT_MARKETPLACE_PATH,
    registered_marketplaces: list[MarketplaceRegistration] | None = None,
) -> TrackLoadResult:
    """Merge tracks: sandbox < marketplace < public < user < org < project."""
    sources: dict[str, int] = {}
    track_lists: list[list[Track]] = []

    # 1. Load sandbox tracks (lowest precedence)
    sandbox_tracks: list[Track] = []
    if sandbox_exposed_urls:
        sandbox_track = create_sandbox_track(sandbox_exposed_urls)
        if sandbox_track:
            sandbox_tracks.append(sandbox_track)
    sources["sandbox"] = len(sandbox_tracks)
    track_lists.append(sandbox_tracks)

    auto_load_registrations = [
        registration
        for registration in registered_marketplaces or []
        if registration.auto_load
    ]

    marketplace_tracks: list[Track] = []
    if load_public and auto_load_registrations:
        marketplace_tracks = load_registered_marketplace_tracks(auto_load_registrations)
    sources["registered_marketplaces"] = len(marketplace_tracks)
    track_lists.append(marketplace_tracks)

    sdk_base = load_available_tracks(
        work_dir=None,
        include_user=load_user,
        include_project=False,
        include_public=load_public,
        marketplace_path=marketplace_path,
    )
    sources["sdk_base"] = len(sdk_base)
    track_lists.append(list(sdk_base.values()))

    # 4. Load organization tracks (one or more repos merged into a single tier;
    # later repos override earlier ones on name collision).
    org_tracks: list[Track] = []
    if load_org and org_repos:
        per_repo_tracks: list[list[Track]] = []
        for org_repo_url, org_name in org_repos:
            try:
                per_repo_tracks.append(
                    load_org_tracks_from_url(
                        org_repo_url=org_repo_url,
                        org_name=org_name,
                    )
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load organization tracks for {org_name}: {e}"
                )
        org_tracks = merge_tracks(per_repo_tracks)
        # Always log the count (including 0) so a failed/empty org load is
        # visible when org loading was requested.
        logger.info(f"Loaded {len(org_tracks)} organization tracks")
    sources["org"] = len(org_tracks)
    track_lists.append(org_tracks)

    # 5. Load project tracks (highest precedence)
    project_tracks = load_available_tracks(
        work_dir=project_dir if load_project else None,
        include_user=False,
        include_project=load_project,
        include_public=False,
    )
    sources["project"] = len(project_tracks)
    track_lists.append(list(project_tracks.values()))

    # Merge all tracks with precedence
    all_tracks = merge_tracks(track_lists)

    logger.info("Loaded %d tracks", len(all_tracks))

    return TrackLoadResult(tracks=all_tracks, sources=sources)


def discover_profile_tracks() -> list[Track]:
    """Track catalog an Handprint profile launches with (#4017).

    Returns the merged user + public tracks — the deterministic sources of
    :func:`load_all_tracks`. ``resolve_agent_profile`` keeps all of them except
    the profile's ``disabled_tracks`` deny-list. ``load_all_tracks`` already
    absorbs and logs benign per-source failures, so this does not swallow errors:
    an unexpected failure propagates rather than silently resolving the profile
    to a zero-track agent.

    Org / project tracks need auth / workspace context not available at resolve
    time, so they are not in this catalog. That is safe under the deny-list
    model: a track missing from the catalog is simply never disabled (it stays
    on when it does load, e.g. project tracks loaded lazily by
    ``LocalConversation``) — the old allow-list would instead have dangled and
    failed the launch.
    """
    return list(
        load_all_tracks(
            load_public=True,
            load_user=True,
            load_org=False,
            load_project=False,
        ).tracks
    )


def sync_public_tracks() -> tuple[bool, str]:
    """Force refresh of public tracks from GitHub repository.

    This triggers a git pull on the cached tracks repository to get
    the latest tracks from the Handprint/extensions repository.

    Returns:
        Tuple of (success: bool, message: str).
    """
    try:
        cache_dir = get_tracks_cache_dir()
        result = update_tracks_repository(
            PUBLIC_TRACKS_REPO, PUBLIC_TRACKS_REF, cache_dir
        )

        if result:
            _invalidate_public_tracks_cache()
            return (True, "Tracks repository synced successfully")
        else:
            return (False, "Failed to sync tracks repository")
    except Exception as e:
        logger.warning(f"Failed to sync tracks repository: {e}")
        return (False, f"Sync failed: {str(e)}")


# ---------------------------------------------------------------------------
# Installed Tracks Management (CRUD Operations)
# ---------------------------------------------------------------------------


def service_install_track(
    source: str,
    ref: str | None = None,
    repo_path: str | None = None,
    force: bool = False,
    installed_dir: Path | None = None,
) -> InstalledTrackInfo:
    """Install a track from a source.

    Args:
        source: Track source - git URL, GitHub shorthand, or local path.
            Supports formats like:
            - GitHub URL: https://github.com/takebox/extensions/tree/main/tracks/github
            - GitHub shorthand: github:Handprint/extensions/tracks/github
            - Local path: /path/to/track
        ref: Optional branch, tag, or commit to install.
        repo_path: Subdirectory path within the repository (for monorepos).
        force: If True, overwrite existing installation.
        installed_dir: Directory for installed tracks.
            Defaults to ~/.handprint/tracks/installed/.

    Returns:
        InstalledTrackInfo with details about the installation.

    Raises:
        FileExistsError: If track is already installed and force=False.
        TrackFetchError: If fetching the track source fails.
        TrackValidationError: If the track is invalid.
    """
    return install_track(
        source=source,
        ref=ref,
        repo_path=repo_path,
        force=force,
        installed_dir=installed_dir,
    )


def service_uninstall_track(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """Uninstall a track by name.

    Args:
        name: Name of the track to uninstall.
        installed_dir: Directory for installed tracks.
            Defaults to ~/.handprint/tracks/installed/.

    Returns:
        True if the track was uninstalled, False if it wasn't installed.
    """
    return uninstall_track(name=name, installed_dir=installed_dir)


def service_enable_track(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """Enable an installed track by name.

    Args:
        name: Name of the track to enable.
        installed_dir: Directory for installed tracks.
            Defaults to ~/.handprint/tracks/installed/.

    Returns:
        True if the track was enabled, False if it wasn't found.
    """
    return enable_track(name=name, installed_dir=installed_dir)


def service_disable_track(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """Disable an installed track by name.

    Args:
        name: Name of the track to disable.
        installed_dir: Directory for installed tracks.
            Defaults to ~/.handprint/tracks/installed/.

    Returns:
        True if the track was disabled, False if it wasn't found.
    """
    return disable_track(name=name, installed_dir=installed_dir)


def service_list_installed_tracks(
    installed_dir: Path | None = None,
) -> list[InstalledTrackInfo]:
    """List all installed tracks.

    Self-healing: reconciles metadata with what is on disk.

    Args:
        installed_dir: Directory for installed tracks.
            Defaults to ~/.handprint/tracks/installed/.

    Returns:
        List of InstalledTrackInfo objects for all installed tracks.
    """
    return list_installed_tracks(installed_dir=installed_dir)


def service_get_installed_track(
    name: str,
    installed_dir: Path | None = None,
) -> InstalledTrackInfo | None:
    """Get information about a specific installed track.

    Args:
        name: Name of the track to get.
        installed_dir: Directory for installed tracks.
            Defaults to ~/.handprint/tracks/installed/.

    Returns:
        InstalledTrackInfo if found, None otherwise.
    """
    return get_installed_track(name=name, installed_dir=installed_dir)


def service_update_track(
    name: str,
    installed_dir: Path | None = None,
) -> InstalledTrackInfo | None:
    """Update an installed track to the latest version.

    Args:
        name: Name of the track to update.
        installed_dir: Directory for installed tracks.
            Defaults to ~/.handprint/tracks/installed/.

    Returns:
        Updated InstalledTrackInfo if successful, None if track not found.
    """
    return update_track(name=name, installed_dir=installed_dir)


class MarketplaceTrackInfo(BaseModel):
    """Information about a track in the marketplace catalog."""

    name: str
    description: str | None
    source: str
    installed: bool


# ---------------------------------------------------------------------------
# Marketplace catalog cache
# ---------------------------------------------------------------------------
# Each call to service_get_marketplace_catalog triggers a git fetch via
# update_tracks_repository, which is a network-bound operation that takes
# multiple seconds. A short TTL cache avoids that hit on every tab open.
#
# Only the catalog structure (name, description, source) is cached; the
# `installed` field is always derived fresh from the local FS so that
# install/uninstall actions are reflected immediately.
#
# Thread safety: concurrent cache misses (cold start or TTL expiry) may
# trigger parallel git fetches, but each fetch is idempotent and produces
# the same result (last writer wins). For this low-traffic endpoint the
# thundering-herd risk is acceptable without an explicit lock.
#
# Type: (timestamp, list-of-(name, description, source)) or None
_CatalogEntry = tuple[str, str | None, str]
_catalog_cache: tuple[float, list[_CatalogEntry]] | None = None
_CATALOG_TTL_SECONDS = 300  # 5 minutes


def service_get_marketplace_catalog(
    marketplace_path: str = DEFAULT_MARKETPLACE_PATH,
    installed_dir: Path | None = None,
) -> list[MarketplaceTrackInfo]:
    """Get the marketplace catalog with installation status.

    Loads the marketplace JSON from the public extensions repository and
    enriches each entry with installation status.

    The catalog structure (name, description, source) is cached for
    _CATALOG_TTL_SECONDS to avoid a git fetch on every call. The
    ``installed`` field is always resolved fresh from the local FS.

    Args:
        marketplace_path: Relative path to marketplace JSON file.
            Defaults to marketplaces/default.json.
        installed_dir: Directory for installed tracks to check status.
            Defaults to ~/.handprint/tracks/installed/.

    Returns:
        List of MarketplaceTrackInfo with track details and installation status.
    """
    global _catalog_cache

    now = monotonic()
    if _catalog_cache is not None and now - _catalog_cache[0] < _CATALOG_TTL_SECONDS:
        entries = _catalog_cache[1]
    else:
        entries = _fetch_catalog_entries(marketplace_path)
        _catalog_cache = (now, entries)

    # Always-fresh installed check — local FS scan, not a network call.
    installed_names = {
        s.name for s in service_list_installed_tracks(installed_dir=installed_dir)
    }
    return [
        MarketplaceTrackInfo(
            name=name, description=desc, source=src, installed=name in installed_names
        )
        for name, desc, src in entries
    ]


def _fetch_catalog_entries(marketplace_path: str) -> list[_CatalogEntry]:
    """Fetch marketplace catalog entries from the public extensions repository.

    This is the slow path: it does a git fetch + reads the marketplace JSON.
    Results are cached by the caller.

    Returns:
        List of (name, description, source) tuples, or an empty list on error.
    """
    cache_dir = get_tracks_cache_dir()
    repo_path = update_tracks_repository(
        PUBLIC_TRACKS_REPO, PUBLIC_TRACKS_REF, cache_dir
    )

    if repo_path is None:
        logger.warning("Failed to access public tracks repository")
        return []

    marketplace_file = repo_path / marketplace_path
    if not marketplace_file.exists():
        logger.warning(f"Marketplace file not found: {marketplace_file}")
        return []

    try:
        marketplace = Marketplace.load(repo_path)
    except (FileNotFoundError, ValueError) as e:
        # Fallback to loading from specific path
        try:
            with open(marketplace_file, encoding="utf-8") as f:
                data = json.load(f)
            marketplace = Marketplace.model_validate(
                {**data, "path": to_posix_path(repo_path)}
            )
        except (json.JSONDecodeError, ValidationError, OSError) as e2:
            logger.warning(f"Failed to load marketplace: {e}, {e2}")
            return []

    # Build catalog from plugins and tracks.
    # Plugins take priority: if a name appears in both plugins and tracks,
    # the plugin version is used (since plugins are added first).
    entries: dict[str, _CatalogEntry] = {}

    for plugin in marketplace.plugins:
        source, ref, subpath = marketplace.resolve_plugin_source(plugin)
        # Build full source string for marketplace catalog.
        # Format: "github:owner/repo@ref/path" - the SDK's install_track
        # can parse this format, so frontends can pass it directly to the
        # install endpoint's source field.
        if ref:
            source = f"{source}@{ref}"
        if subpath:
            source = f"{source}/{subpath}"
        entries[plugin.name] = (plugin.name, plugin.description, source)

    for track_entry in marketplace.tracks:
        if track_entry.name not in entries:
            entries[track_entry.name] = (
                track_entry.name,
                track_entry.description,
                track_entry.source,
            )

    return list(entries.values())
