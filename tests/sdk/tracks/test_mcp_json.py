"""Tests for .mcp.json support in AgentTracks (Issue #1476).

Key behaviors tested:
1. AgentTracks (TRACK.md) load .mcp.json when present
2. AgentTracks ignore mcp_tools frontmatter (only use .mcp.json)
3. Legacy tracks load mcp_tools from frontmatter
4. Legacy tracks don't load .mcp.json
5. Variable expansion works (${VAR}, ${VAR:-default}, ${TRACK_ROOT})
"""

import json
from pathlib import Path

import pytest

from handprint.sdk.tracks import (
    Track,
    TrackValidationError,
    load_tracks_from_dir,
)


def test_agenttracks_loads_mcp_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AgentTracks (TRACK.md) should load .mcp.json with variable expansion."""
    monkeypatch.delenv("PORT", raising=False)
    track_dir = tmp_path / "my-track"
    track_dir.mkdir()
    (track_dir / "TRACK.md").write_text("# My Track")
    mcp_config = {
        "mcpServers": {
            "server": {
                "command": "${TRACK_ROOT}/run.py",
                "args": ["--port", "${PORT:-8080}"],
            }
        }
    }
    (track_dir / ".mcp.json").write_text(json.dumps(mcp_config))

    track = Track.load(track_dir / "TRACK.md")

    assert track.mcp_tools is not None
    # ${TRACK_ROOT} should be expanded
    assert track.mcp_tools["server"].command == f"{track_dir}/run.py"
    # ${PORT:-8080} should use default
    assert track.mcp_tools["server"].args == ["--port", "8080"]


def test_agenttracks_ignores_frontmatter_mcp_tools(tmp_path: Path) -> None:
    """AgentTracks should ONLY use .mcp.json, ignoring mcp_tools frontmatter."""
    track_dir = tmp_path / "my-track"
    track_dir.mkdir()
    # Frontmatter has mcp_tools but no .mcp.json file
    (track_dir / "TRACK.md").write_text(
        "---\nmcp_tools:\n  server: {command: python}\n---\n# Track"
    )

    track = Track.load(track_dir / "TRACK.md")
    assert track.mcp_tools is None


def test_legacy_track_loads_frontmatter_mcp_tools(tmp_path: Path) -> None:
    """Legacy tracks (.md files) should load mcp_tools from frontmatter."""
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir()
    (tracks_dir / "legacy.md").write_text(
        "---\nmcp_tools:\n  server: {command: python}\n---\n# Legacy"
    )

    track = Track.load(tracks_dir / "legacy.md", tracks_dir)

    assert track.mcp_tools is not None
    assert "server" in track.mcp_tools


def test_legacy_track_ignores_mcp_json_in_directory(tmp_path: Path) -> None:
    """Legacy tracks should NOT load .mcp.json even if present in directory."""
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir()
    (tracks_dir / "legacy.md").write_text("# Legacy Track")
    (tracks_dir / ".mcp.json").write_text(
        '{"mcpServers": {"server": {"command": "python", "args": []}}}'
    )

    track = Track.load(tracks_dir / "legacy.md", tracks_dir)
    assert track.mcp_tools is None


def test_mcp_json_invalid_json_raises_error(tmp_path: Path) -> None:
    """Invalid JSON in .mcp.json should raise TrackValidationError."""
    track_dir = tmp_path / "my-track"
    track_dir.mkdir()
    (track_dir / "TRACK.md").write_text("# Track")
    (track_dir / ".mcp.json").write_text("not valid json")

    with pytest.raises(TrackValidationError, match="Invalid JSON"):
        Track.load(track_dir / "TRACK.md")


def test_load_tracks_from_dir_mcp_json_only_for_agenttracks(tmp_path: Path) -> None:
    """load_tracks_from_dir() should only load .mcp.json for agent_tracks."""
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir()

    # AgentTrack with .mcp.json
    agent_dir = tracks_dir / "agent-track"
    agent_dir.mkdir()
    (agent_dir / "TRACK.md").write_text("# Agent Track")
    (agent_dir / ".mcp.json").write_text(
        '{"mcpServers": {"server": {"command": "python", "args": []}}}'
    )

    # Legacy track
    (tracks_dir / "legacy.md").write_text("# Legacy Track")

    repo_tracks, _, agent_tracks = load_tracks_from_dir(tracks_dir)

    assert agent_tracks["agent-track"].mcp_tools is not None
    assert repo_tracks["legacy"].mcp_tools is None
