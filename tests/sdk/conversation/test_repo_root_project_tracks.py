from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from handprint.sdk.agent import Agent
from handprint.sdk.context.agent_context import AgentContext
from handprint.sdk.conversation.impl.local_conversation import LocalConversation
from handprint.sdk.event import SystemPromptEvent
from handprint.sdk.llm import Message, TextContent
from handprint.sdk.tracks import Track, load_project_tracks
from handprint.sdk.testing import TestLLM


def _agent(agent_context: AgentContext) -> Agent:
    return Agent(
        llm=TestLLM.from_messages(
            [Message(role="assistant", content=[TextContent(text="ok")])],
            model="test-model",
        ),
        tools=[],
        include_default_tools=[],
        agent_context=agent_context,
    )


def test_system_prompt_includes_repo_root_agents_md_when_workdir_is_subdir(
    tmp_path: Path,
):
    """Repo-root AGENTS.md should still be injected when starting from a subdir.

    This is the integration-style equivalent of the CLI manual test:
    - work_dir is a subdirectory
    - git repo root contains AGENTS.md
    - AgentContext is built from load_project_tracks(work_dir)
    - LocalConversation initialization emits a SystemPromptEvent

    We assert the sentinel from the repo root AGENTS.md appears in the
    SystemPromptEvent.dynamic_context.
    """

    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("# Project Guidelines\n\nSENTINEL_ROOT_123\n")

    subdir = tmp_path / "subdir"
    subdir.mkdir()

    tracks = load_project_tracks(subdir)
    ctx = AgentContext(
        tracks=tracks,
        # Keep deterministic across environments.
        current_datetime="2026-01-01T00:00:00Z",
    )

    agent = Agent(
        llm=TestLLM.from_messages(
            [
                Message(
                    role="assistant",
                    content=[TextContent(text="ok")],
                )
            ],
            model="test-model",
        ),
        tools=[],
        include_default_tools=[],
        agent_context=ctx,
    )

    conversation = LocalConversation(
        agent=agent,
        workspace=subdir,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    conversation.send_message("hi")

    system_prompt_event = next(
        e for e in conversation.state.events if isinstance(e, SystemPromptEvent)
    )
    assert system_prompt_event.dynamic_context is not None
    assert "SENTINEL_ROOT_123" in system_prompt_event.dynamic_context.text

    conversation.close()


def test_load_project_tracks_flag_injects_tracks_in_standalone_sdk(tmp_path: Path):
    """``AgentContext(load_project_tracks=True)`` works without agent-server.

    LocalConversation resolves project tracks from the workspace at startup,
    so the flag behaves consistently for standalone SDK usage (agent-viczin#574).
    """
    (tmp_path / "AGENTS.md").write_text("# Guidelines\n\nSENTINEL_FLAG_456\n")

    agent = _agent(
        AgentContext(
            load_project_tracks=True,
            current_datetime="2026-01-01T00:00:00Z",
        )
    )
    conversation = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    conversation.send_message("hi")

    # Tracks are merged into the live agent context...
    assert conversation.agent.agent_context is not None
    assert "agents" in {s.name for s in conversation.agent.agent_context.tracks}
    # ...and rendered into the system prompt.
    system_prompt_event = next(
        e for e in conversation.state.events if isinstance(e, SystemPromptEvent)
    )
    assert system_prompt_event.dynamic_context is not None
    assert "SENTINEL_FLAG_456" in system_prompt_event.dynamic_context.text

    conversation.close()


def test_load_project_tracks_flag_off_does_not_inject(tmp_path: Path):
    """With the flag unset (default), project tracks are not loaded."""
    (tmp_path / "AGENTS.md").write_text("# Guidelines\n\nSENTINEL_OFF_789\n")

    agent = _agent(AgentContext(current_datetime="2026-01-01T00:00:00Z"))
    conversation = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    conversation.send_message("hi")

    assert conversation.agent.agent_context is not None
    assert conversation.agent.agent_context.tracks == []
    system_prompt_event = next(
        e for e in conversation.state.events if isinstance(e, SystemPromptEvent)
    )
    dynamic = system_prompt_event.dynamic_context
    assert dynamic is None or "SENTINEL_OFF_789" not in dynamic.text

    conversation.close()


def test_load_project_tracks_flag_merges_with_project_precedence(tmp_path: Path):
    """Project tracks override same-named context tracks; others are preserved."""
    (tmp_path / "AGENTS.md").write_text("# Guidelines\n\nSENTINEL_NEW\n")

    agent = _agent(
        AgentContext(
            tracks=[
                Track(name="keep", content="keep me"),
                Track(name="agents", content="OLD_CONTENT"),
            ],
            load_project_tracks=True,
            current_datetime="2026-01-01T00:00:00Z",
        )
    )
    conversation = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    conversation.send_message("hi")

    assert conversation.agent.agent_context is not None
    tracks = {s.name: s for s in conversation.agent.agent_context.tracks}
    assert tracks["keep"].content == "keep me"
    assert "SENTINEL_NEW" in tracks["agents"].content
    assert "OLD_CONTENT" not in tracks["agents"].content

    conversation.close()


def test_disabled_tracks_drops_project_track_at_lazy_merge(tmp_path: Path):
    """A project track whose name is in ``disabled_tracks`` is dropped during the
    lazy ``LocalConversation`` merge — the ``model_copy`` path that bypasses the
    ``AgentContext`` validator. An unrelated disabled name is a harmless no-op.
    """
    # AGENTS.md becomes a project track named "agents".
    (tmp_path / "AGENTS.md").write_text("# Guidelines\n\nSENTINEL\n")

    agent = _agent(
        AgentContext(
            tracks=[Track(name="keep", content="keep me")],
            load_project_tracks=True,
            disabled_tracks=["agents", "not-in-catalog"],
            current_datetime="2026-01-01T00:00:00Z",
        )
    )
    conversation = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    conversation.send_message("hi")

    assert conversation.agent.agent_context is not None
    names = {s.name for s in conversation.agent.agent_context.tracks}
    # The lazily-loaded project track "agents" is disabled -> dropped at merge.
    assert "agents" not in names
    # A non-disabled track is unaffected; the absent "not-in-catalog" is a no-op.
    assert "keep" in names

    conversation.close()


def test_load_project_tracks_failure_does_not_block_conversation(tmp_path: Path):
    """Project-track loading is best-effort: a load error must not break startup."""
    (tmp_path / "AGENTS.md").write_text("# Guidelines\n\nSENTINEL\n")

    agent = _agent(
        AgentContext(
            tracks=[Track(name="keep", content="keep me")],
            load_project_tracks=True,
            current_datetime="2026-01-01T00:00:00Z",
        )
    )
    conversation = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )

    with patch(
        "handprint.sdk.conversation.impl.local_conversation.load_available_tracks",
        side_effect=PermissionError("workspace unreadable"),
    ):
        conversation.send_message("hi")  # must not raise

    # Conversation started; pre-existing tracks are untouched.
    assert conversation.agent.agent_context is not None
    assert {s.name for s in conversation.agent.agent_context.tracks} == {"keep"}

    conversation.close()
