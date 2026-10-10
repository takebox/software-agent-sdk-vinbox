from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self

from pydantic import Field
from rich.text import Text

from handprint.sdk.tracks.execute import render_content_with_commands
from handprint.sdk.tool.tool import (
    Action,
    DeclaredResources,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from handprint.sdk.utils.path import to_posix_path


if TYPE_CHECKING:
    from handprint.sdk.conversation.base import BaseConversation
    from handprint.sdk.conversation.state import ConversationState


class InvokeTrackAction(Action):
    name: str = Field(description="Name of the loaded track to invoke.")

    @property
    def visualize(self) -> Text:
        t = Text()
        t.append("Invoke track: ", style="bold blue")
        t.append(self.name)
        return t


class InvokeTrackObservation(Observation):
    track_name: str = Field(
        description="Name of the track this observation corresponds to."
    )

    @property
    def visualize(self) -> Text:
        t = Text()
        t.append(f"[track: {self.track_name}]\n", style="bold green")
        t.append(self.text)
        return t


TOOL_DESCRIPTION = """Invoke a track by name.

This is the only supported way to invoke a track listed in
`<available_tracks>`. Call it with the `<name>` shown in that block; the
track's full content is rendered (including any dynamic context) and
returned as the tool result.
"""


class InvokeTrackExecutor(ToolExecutor):
    @staticmethod
    def _get_tracks_and_working_dir(
        conversation: BaseConversation | None,
    ) -> tuple[list, Path | None]:
        """Extract the track catalog and working dir from the conversation state."""
        if conversation is None:
            return [], None

        state = conversation.state
        ctx = state.agent.agent_context
        tracks = list(ctx.tracks) if ctx else []
        working_dir = state.workspace.working_dir
        return tracks, Path(working_dir) if working_dir else None

    @staticmethod
    def _record_invocation(conversation: BaseConversation | None, name: str) -> None:
        """Append `name` to the conversation's invoked-tracks list (deduped)."""
        if conversation is None:
            return
        invoked = conversation.state.invoked_tracks
        if name not in invoked:
            invoked.append(name)

    @staticmethod
    def _error(name: str, text: str) -> InvokeTrackObservation:
        return InvokeTrackObservation.from_text(
            text=text, is_error=True, track_name=name
        )

    def __call__(
        self,
        action: InvokeTrackAction,
        conversation: BaseConversation | None = None,
    ) -> InvokeTrackObservation:
        tracks, working_dir = self._get_tracks_and_working_dir(conversation)
        name = action.name.strip()

        match = next((s for s in tracks if s.name == name), None)
        if match is None:
            available = (
                ", ".join(
                    sorted(s.name for s in tracks if not s.disable_model_invocation)
                )
                or "<none>"
            )
            return self._error(
                name, f"Unknown track '{name}'. Available tracks: {available}."
            )
        if match.disable_model_invocation:
            return self._error(
                name,
                (
                    f"Track '{name}' cannot be invoked directly. "
                    "It can only be activated by trigger matching."
                ),
            )

        rendered = render_content_with_commands(match.content, working_dir=working_dir)
        rendered = self._append_track_location_footer(
            rendered, match.source, working_dir
        )
        self._record_invocation(conversation, name)
        return InvokeTrackObservation.from_text(text=rendered, track_name=name)

    @staticmethod
    def _append_track_location_footer(
        rendered: str, source: str | None, working_dir: Path | None
    ) -> str:
        """Append a trailing note pointing the LLM at the track's on-disk directory.

        The AgentTracks spec allows tracks to bundle `scripts/`, `references/`, and
        `assets/` alongside `TRACK.md`. Track authors reference those by relative
        path, so the model needs to know where the track lives to reach them.

        When the track lives under the conversation's `working_dir`, the path is
        rendered relative to it to avoid leaking absolute home-directory paths
        into the LLM context.
        """
        if not source:
            return rendered
        try:
            track_md = Path(source).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            return rendered
        if not track_md.is_file():
            return rendered
        track_dir = track_md.parent
        display: Path = track_dir
        if working_dir is not None:
            try:
                display = track_dir.relative_to(working_dir.resolve())
            except (ValueError, OSError):
                pass  # track lives outside working_dir, keep absolute
        footer = (
            f"\n\n---\n"
            f"This track is located at `{to_posix_path(display)}`. "
            f"Any files it references (e.g. under `scripts/`, `references/`, "
            f"`assets/`) are relative to that directory."
        )
        return rendered + footer


class InvokeTrackTool(ToolDefinition[InvokeTrackAction, InvokeTrackObservation]):
    """Built-in tool for explicit invocation of progressive-disclosure tracks."""

    user_selectable: ClassVar[bool] = False

    def declared_resources(self, action: Action) -> DeclaredResources:
        # Rendering a track may execute inline `!`cmd`` tokens, which can
        # touch arbitrary on-disk state. Keying on the track name serializes
        # concurrent invocations of the same track while still allowing
        # distinct tracks to render in parallel.
        name = action.name if isinstance(action, InvokeTrackAction) else ""
        return DeclaredResources(keys=(f"track:{name.strip()}",), declared=True)

    @classmethod
    def create(
        cls,
        conv_state: ConversationState | None = None,  # noqa: ARG003
        **params,
    ) -> Sequence[Self]:
        if params:
            raise ValueError("InvokeTrackTool doesn't accept parameters")
        return [
            cls(
                action_type=InvokeTrackAction,
                observation_type=InvokeTrackObservation,
                description=TOOL_DESCRIPTION,
                executor=InvokeTrackExecutor(),
                annotations=ToolAnnotations(
                    title="invoke_track",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]
