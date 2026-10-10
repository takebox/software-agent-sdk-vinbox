"""ACP track sourcing: who supplies an ACP agent's tracks (#4019).

An ACP CLI reads ``AGENTS.md`` / ``HAIJUN.md`` and its own project tracks from
the session cwd, so Handprint never injects those. Whether it injects its
*managed* catalog is a per-deployment choice (``Config.acp_track_sourcing``):
a host-local CLI reaches the user's own configuration, one in a container
cannot.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from handprint.agent_server.config import ACPTrackSourcing, Config
from handprint.sdk import LLM, Agent, Conversation
from handprint.sdk.agent import ACPAgent, AgentBase
from handprint.sdk.context import AgentContext
from handprint.sdk.launch import LaunchRuntime, finalize
from handprint.sdk.marketplace.registration import MarketplaceRegistration
from handprint.sdk.settings.model import validate_agent_settings
from handprint.sdk.tracks import Track


AGENTS_MD_BODY = "sentinel-agents-md-body"
MANAGED_TRACK = "managed-catalog-track"


def _managed_track() -> Track:
    return Track(
        name=MANAGED_TRACK,
        content="managed content",
        description="from the server catalog",
        source="public",
        is_agenttracks_format=True,
    )


def _acp_agent(**context_kwargs) -> ACPAgent:
    settings = validate_agent_settings(
        {
            "agent_kind": "acp",
            "acp_server": "haijun-code",
            "agent_context": AgentContext(**context_kwargs).model_dump(),
        }
    )
    agent = settings.create_agent()
    assert isinstance(agent, ACPAgent)
    return agent


def _workspace(root: Path) -> Path:
    project = root / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text(f"# Repo\n\n{AGENTS_MD_BODY}\n")
    track_dir = project / ".agents" / "tracks" / "project-track"
    track_dir.mkdir(parents=True)
    (track_dir / "TRACK.md").write_text(
        "---\nname: project-track\ndescription: local\n---\n\nbody\n"
    )
    return project


def _apply_acp_track_sourcing(
    agent: AgentBase, sourcing: ACPTrackSourcing
) -> AgentBase:
    return finalize(agent, LaunchRuntime(acp_track_sourcing=sourcing)).agent


def _installed_suffix(agent: AgentBase, project: Path) -> str:
    """The suffix ``init_state`` renders into the ACP subprocess's prompt.

    Only the subprocess spawn is stubbed; the render is the production one.
    """
    with patch.object(ACPAgent, "_start_acp_server", lambda self, state: None):
        conversation = Conversation(agent=agent, workspace=str(project))
        conversation._ensure_agent_ready()
        agent_after_load = conversation.agent
        assert isinstance(agent_after_load, ACPAgent)
        return agent_after_load._installed_suffix or ""


def test_config_defaults_to_native_sourcing() -> None:
    assert Config().acp_track_sourcing == "native"


def test_acp_agent_clears_load_project_tracks() -> None:
    agent = _acp_agent(load_project_tracks=True)
    assert agent.agent_context is not None
    assert agent.agent_context.load_project_tracks is False


def test_handprint_agent_keeps_load_project_tracks() -> None:
    """The guard is ACP-only — a regular agent still loads project tracks."""
    agent = Agent(
        llm=LLM(model="gpt-4o", usage_id="agent"),
        tools=[],
        agent_context=AgentContext(load_project_tracks=True),
    )
    assert agent.agent_context is not None
    assert agent.agent_context.load_project_tracks is True


@pytest.mark.parametrize("sourcing", ["native", "handprint_managed"])
def test_repo_context_never_reaches_the_acp_prompt(
    tmp_path: Path, sourcing: ACPTrackSourcing
) -> None:
    project = _workspace(tmp_path)
    agent = _apply_acp_track_sourcing(
        _acp_agent(tracks=[_managed_track()], load_project_tracks=True), sourcing
    )
    suffix = _installed_suffix(agent, project)
    assert AGENTS_MD_BODY not in suffix
    assert "project-track" not in suffix


def test_native_sourcing_strips_managed_tracks(tmp_path: Path) -> None:
    project = _workspace(tmp_path)
    agent = _apply_acp_track_sourcing(
        _acp_agent(tracks=[_managed_track()], load_project_tracks=True), "native"
    )
    assert agent.agent_context is not None
    assert agent.agent_context.tracks == []
    assert MANAGED_TRACK not in _installed_suffix(agent, project)


def test_managed_sourcing_keeps_managed_tracks(tmp_path: Path) -> None:
    project = _workspace(tmp_path)
    agent = _apply_acp_track_sourcing(
        _acp_agent(tracks=[_managed_track()], load_project_tracks=True),
        "handprint_managed",
    )
    assert agent.agent_context is not None
    assert [s.name for s in agent.agent_context.tracks] == [MANAGED_TRACK]
    assert MANAGED_TRACK in _installed_suffix(agent, project)


def test_native_sourcing_clears_lazy_track_sources() -> None:
    """Flags and marketplace registrations resolve to tracks later, so a strip
    that only emptied ``tracks`` would let them back in."""
    agent = _apply_acp_track_sourcing(
        _acp_agent(
            load_user_tracks=True,
            load_public_tracks=True,
            registered_marketplaces=[
                MarketplaceRegistration(
                    name="mkt", source="https://example.invalid/mkt.git"
                )
            ],
        ),
        "native",
    )
    context = agent.agent_context
    assert context is not None
    assert context.load_user_tracks is False
    assert context.load_public_tracks is False
    assert context.registered_marketplaces == []


def test_native_sourcing_leaves_a_non_acp_agent_alone() -> None:
    agent = Agent(
        llm=LLM(model="gpt-4o", usage_id="agent"),
        tools=[],
        agent_context=AgentContext(tracks=[_managed_track()]),
    )
    sourced = _apply_acp_track_sourcing(agent, "native")
    assert sourced.agent_context is not None
    assert [s.name for s in sourced.agent_context.tracks] == [MANAGED_TRACK]


def test_native_sourcing_is_a_no_op_without_tracks() -> None:
    agent = _acp_agent(current_datetime=None)
    assert _apply_acp_track_sourcing(agent, "native") is agent
