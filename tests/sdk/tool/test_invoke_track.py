"""Tests for the `invoke_track` built-in tool."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from handprint.sdk import LLM, Agent, AgentContext
from handprint.sdk.context import KeywordTrigger
from handprint.sdk.conversation.state import ConversationState
from handprint.sdk.tracks import Track
from handprint.sdk.tool.builtins import (
    BUILT_IN_TOOL_CLASSES,
    BUILT_IN_TOOLS,
    InvokeTrackAction,
    InvokeTrackObservation,
    InvokeTrackTool,
)
from handprint.sdk.tool.schema import Action
from handprint.sdk.workspace.local import LocalWorkspace


def _make_track(
    name: str,
    content: str = "# body\n\nSome guidance.",
    is_agenttracks_format: bool = True,
    trigger=None,
    disable_model_invocation: bool = False,
) -> Track:
    return Track(
        name=name,
        content=content,
        description=f"desc for {name}",
        source=f"/tracks/{name}/TRACK.md",
        is_agenttracks_format=is_agenttracks_format,
        trigger=trigger,
        disable_model_invocation=disable_model_invocation,
    )


def _make_conv(
    tracks: list[Track],
    working_dir: str = "/tmp",
    invoked_tracks: list[str] | None = None,
) -> Any:
    """Minimal duck-typed BaseConversation replacement for the executor.

    Returned as `Any` so pyright accepts it where a `LocalConversation`
    is declared; the executor only uses attribute access, so a
    SimpleNamespace is enough at runtime.
    """
    return SimpleNamespace(
        state=SimpleNamespace(
            agent=SimpleNamespace(
                agent_context=SimpleNamespace(tracks=tracks),
            ),
            workspace=SimpleNamespace(working_dir=working_dir),
            invoked_tracks=invoked_tracks or [],
        ),
    )


def _tool() -> InvokeTrackTool:
    (t,) = InvokeTrackTool.create()
    return t


def _run(name: str, conv: Any) -> InvokeTrackObservation:
    """Invoke the executor, silencing pyright's Optional complaint on .executor."""
    executor = _tool().executor
    assert executor is not None
    return executor(InvokeTrackAction(name=name), conversation=conv)


def test_not_in_default_builtins_but_resolvable_by_name():
    # Deliberately NOT in BUILT_IN_TOOLS: it must only attach when an
    # AgentTracks-format track is loaded.
    assert InvokeTrackTool not in BUILT_IN_TOOLS
    # Still resolvable by name so the agent can wire it up conditionally.
    assert BUILT_IN_TOOL_CLASSES["InvokeTrackTool"] is InvokeTrackTool


def test_name_auto_derived():
    assert InvokeTrackTool.name == "invoke_track"


def test_create_rejects_params():
    with pytest.raises(ValueError):
        InvokeTrackTool.create(foo="bar")


@pytest.mark.parametrize(
    ("attr", "expected"),
    [
        ("readOnlyHint", True),
        ("destructiveHint", False),
        ("idempotentHint", True),
        ("openWorldHint", False),
    ],
)
def test_annotations_are_read_only_safe(attr: str, expected: bool):
    t = _tool()
    assert t.annotations is not None
    assert getattr(t.annotations, attr) is expected


@pytest.mark.parametrize(
    ("content", "present", "absent"),
    [
        pytest.param(
            "Rule 1.\nRule 2.",
            "Rule 1.",
            None,
            id="static-content",
        ),
        pytest.param(
            "before !`echo TOKEN_OK` after",
            "TOKEN_OK",
            "!`echo",
            id="dynamic-shell-token-executed",
        ),
    ],
)
def test_invoke_renders_and_records(
    content: str, present: str, absent: str | None, tmp_path
):
    track = _make_track("s", content=content)
    conv = _make_conv([track], working_dir=str(tmp_path))

    obs = _run("s", conv)

    assert obs.is_error is False
    assert obs.track_name == "s"
    assert present in obs.text
    if absent is not None:
        assert absent not in obs.text
    assert conv.state.invoked_tracks == ["s"]


@pytest.mark.parametrize(
    "requested",
    ["pdf-analyst", "  pdf-analyst  ", "\tpdf-analyst\n"],
    ids=["exact", "padded-spaces", "padded-tabs-newlines"],
)
def test_name_is_trimmed_before_lookup(requested: str):
    conv = _make_conv([_make_track("pdf-analyst")])

    obs = _run(requested, conv)

    assert obs.is_error is False
    assert obs.track_name == "pdf-analyst"


def test_footer_uses_absolute_path_when_outside_working_dir(tmp_path):
    """Track outside the conversation's working_dir: footer shows absolute path."""
    track_dir = tmp_path / "pdf-analyst"
    track_dir.mkdir()
    track_md = track_dir / "TRACK.md"
    track_md.write_text("placeholder")
    track = Track(
        name="pdf-analyst",
        content="# body\n\nSee scripts/extract.py.",
        description="desc",
        source=str(track_md),
        is_agenttracks_format=True,
    )
    # working_dir is unrelated, so the footer must stay absolute.
    conv = _make_conv([track], working_dir=str(tmp_path / "elsewhere"))

    obs = _run("pdf-analyst", conv)

    assert obs.is_error is False
    assert track_dir.resolve().as_posix() in obs.text
    assert "scripts/" in obs.text and "references/" in obs.text
    assert obs.text.rstrip().endswith("relative to that directory.")


def test_footer_uses_relative_path_when_inside_working_dir(tmp_path):
    """Track under working_dir: footer uses the relative path, avoiding leakage
    of absolute home-directory paths into the LLM context."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    track_dir = workspace / "tracks" / "pdf-analyst"
    track_dir.mkdir(parents=True)
    track_md = track_dir / "TRACK.md"
    track_md.write_text("placeholder")
    track = Track(
        name="pdf-analyst",
        content="body",
        description="desc",
        source=str(track_md),
        is_agenttracks_format=True,
    )
    conv = _make_conv([track], working_dir=str(workspace))

    obs = _run("pdf-analyst", conv)

    assert obs.is_error is False
    assert "`tracks/pdf-analyst`" in obs.text
    assert str(workspace.resolve()) not in obs.text


def test_footer_omitted_when_track_has_no_source():
    """Programmatic tracks (source=None) should not get a footer."""
    track = Track(
        name="prog",
        content="inline body",
        description="desc",
        source=None,
        is_agenttracks_format=True,
    )
    conv = _make_conv([track])

    obs = _run("prog", conv)

    assert obs.is_error is False
    assert "located at" not in obs.text
    assert obs.text.strip() == "inline body"


def test_footer_omitted_when_source_is_not_a_real_path():
    """Sentinels like `'local'` or `'github:owner/repo'` must not produce a footer
    pointing at a made-up path."""
    track = Track(
        name="remote",
        content="body",
        description="desc",
        source="github:owner/repo",
        is_agenttracks_format=True,
    )
    conv = _make_conv([track])

    obs = _run("remote", conv)

    assert obs.is_error is False
    assert "located at" not in obs.text


def test_invoked_tracks_dedupes():
    conv = _make_conv([_make_track("x")])

    _run("x", conv)
    _run("x", conv)

    assert conv.state.invoked_tracks == ["x"]


def test_legacy_triggered_track_is_invocable():
    """Any Track in agent_context.tracks is resolvable, not just
    AgentTracks-format. This keeps the executor consistent with what the
    `<available_tracks>` prompt block advertises."""
    legacy = _make_track(
        "flarglebargle",
        content="legacy body",
        is_agenttracks_format=False,
        trigger=KeywordTrigger(keywords=["flarglebargle"]),
    )
    conv = _make_conv([legacy])

    obs = _run("flarglebargle", conv)

    assert obs.is_error is False
    assert "legacy body" in obs.text
    assert conv.state.invoked_tracks == ["flarglebargle"]


def test_disable_model_invocation_rejects_direct_invocation():
    track = _make_track(
        "trigger-only",
        disable_model_invocation=True,
        trigger=KeywordTrigger(keywords=["trigger-only"]),
    )
    conv = _make_conv([track])

    obs = _run("trigger-only", conv)

    assert obs.is_error is True
    assert obs.track_name == "trigger-only"
    assert "cannot be invoked directly" in obs.text
    assert conv.state.invoked_tracks == []


@pytest.mark.parametrize(
    ("conv_factory", "requested", "expected_substrings"),
    [
        pytest.param(
            lambda: _make_conv([_make_track("alpha"), _make_track("beta")]),
            "gamma",
            ("Unknown track 'gamma'", "alpha", "beta"),
            id="name-not-in-catalog",
        ),
        pytest.param(
            lambda: _make_conv([]),
            "anything",
            ("Unknown track 'anything'", "<none>"),
            id="empty-catalog",
        ),
        pytest.param(
            lambda: None,
            "anything",
            ("Unknown track 'anything'", "<none>"),
            id="no-conversation",
        ),
    ],
)
def test_error_paths_do_not_mutate_state(
    conv_factory, requested: str, expected_substrings: tuple[str, ...]
):
    conv = conv_factory()

    obs = _run(requested, conv)

    assert obs.is_error is True
    assert obs.track_name == requested
    for expected in expected_substrings:
        assert expected in obs.text
    if conv is not None:
        assert conv.state.invoked_tracks == []


@pytest.mark.parametrize(
    "track_name",
    ["pdf-analyst", "frontend-design", "with space"],
)
def test_declared_resources_keyed_on_track_name(track_name: str):
    res = _tool().declared_resources(InvokeTrackAction(name=track_name))

    assert res.declared is True
    assert res.keys == (f"track:{track_name.strip()}",)


def _make_agent(tracks: list[Track]) -> Agent:
    llm = LLM(
        usage_id="agent",
        model="juglow/haijun-codtral",
        api_key=SecretStr("x"),
    )
    return Agent(llm=llm, tools=[], agent_context=AgentContext(tracks=tracks))


@pytest.mark.parametrize(
    ("tracks", "expect_attached"),
    [
        pytest.param([], False, id="no-tracks"),
        pytest.param(
            [_make_track("legacy", is_agenttracks_format=False)],
            False,
            id="only-legacy-track",
        ),
        pytest.param(
            [_make_track("frontend-design", is_agenttracks_format=True)],
            True,
            id="agenttracks-present",
        ),
        pytest.param(
            [
                _make_track(
                    "trigger-only",
                    is_agenttracks_format=True,
                    disable_model_invocation=True,
                )
            ],
            False,
            id="only-disabled-agenttracks",
        ),
        pytest.param(
            [
                _make_track(
                    "trigger-only",
                    is_agenttracks_format=True,
                    disable_model_invocation=True,
                ),
                _make_track("frontend-design", is_agenttracks_format=True),
            ],
            True,
            id="mixed-disabled-and-invocable-agenttracks",
        ),
    ],
)
def test_agent_auto_attaches_invoke_track_tool(
    tracks: list[Track], expect_attached: bool, tmp_path
):
    """`Agent._initialize` must attach `invoke_track` iff an AgentTracks-format
    track is loaded — regardless of what's in `include_default_tools`."""
    agent = _make_agent(tracks)
    state = ConversationState.create(
        id=uuid.uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=str(tmp_path)),
    )
    agent._initialize(state)

    attached = "invoke_track" in agent._tools
    assert attached is expect_attached


def test_invoke_track_declared_resources_typed():
    """InvokeTrackTool.declared_resources accesses action.name typed."""
    tool = InvokeTrackTool(description="invoke track", action_type=InvokeTrackAction)
    action = InvokeTrackAction(name="test-track")
    res = tool.declared_resources(action)
    assert res.keys == ("track:test-track",)

    class OtherAction(Action):
        pass

    other_action = OtherAction()
    res_other = tool.declared_resources(other_action)
    assert res_other.keys == ("track:",)
