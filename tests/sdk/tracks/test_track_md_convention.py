"""Tests for TRACK.md file convention and name validation (Issue #1475)."""

from pathlib import Path

import pytest

from handprint.sdk.tracks import (
    Track,
    TrackValidationError,
    load_tracks_from_dir,
)
from handprint.sdk.tracks.utils import (
    find_track_md,
    validate_track_name,
)


def test_find_track_md(tmp_path: Path) -> None:
    """find_track_md() should locate TRACK.md files case-insensitively."""
    track_dir = tmp_path / "my-track"
    track_dir.mkdir()

    # Not found
    assert find_track_md(track_dir) is None

    # Found (case-insensitive)
    track_md = track_dir / "track.MD"
    track_md.write_text("# My Track")
    assert find_track_md(track_dir) == track_md


def test_validate_track_name_valid() -> None:
    """validate_track_name() should accept valid AgentTracks names."""
    assert validate_track_name("my-track") == []
    assert validate_track_name("track2") == []
    assert validate_track_name("my-cool-track") == []
    assert validate_track_name("a") == []
    assert validate_track_name("a" * 64) == []


def test_validate_track_name_invalid_format() -> None:
    """validate_track_name() should reject invalid name formats."""
    # Uppercase - should contain format error
    errors = validate_track_name("MyTrack")
    assert any("lowercase" in e for e in errors)

    # Underscore - should contain format error
    errors = validate_track_name("my_track")
    assert any("lowercase" in e for e in errors)

    # Starts with hyphen - should contain format error
    errors = validate_track_name("-mytrack")
    assert any("lowercase" in e for e in errors)

    # Consecutive hyphens - should contain format error
    errors = validate_track_name("my--track")
    assert any("lowercase" in e for e in errors)


def test_validate_track_name_length() -> None:
    """validate_track_name() should enforce length limits."""
    # Too long - should contain length error
    errors = validate_track_name("a" * 65)
    assert any("64 characters" in e for e in errors)

    # Empty - should contain empty error
    errors = validate_track_name("")
    assert any("empty" in e.lower() for e in errors)


def test_validate_track_name_directory_mismatch() -> None:
    """validate_track_name() should detect directory name mismatch."""
    errors = validate_track_name("my-track", directory_name="other-track")
    assert any("does not match directory" in e for e in errors)


def test_track_load_with_track_md(tmp_path: Path) -> None:
    """Track.load() should use directory name for TRACK.md format."""
    track_dir = tmp_path / "tracks"
    track_dir.mkdir()
    my_track_dir = track_dir / "pdf-tools"
    my_track_dir.mkdir()
    (my_track_dir / "TRACK.md").write_text("---\ntriggers:\n  - pdf\n---\n# PDF Tools")

    # Uses directory name automatically for TRACK.md files
    track = Track.load(my_track_dir / "TRACK.md", track_dir)
    assert track.name == "pdf-tools"


def test_track_load_auto_validates_track_md(tmp_path: Path) -> None:
    """Track.load() should auto-validate TRACK.md directory names."""
    track_dir = tmp_path / "tracks"
    track_dir.mkdir()

    # Invalid directory name should raise validation error automatically
    bad_dir = track_dir / "Bad_Name"
    bad_dir.mkdir()
    (bad_dir / "TRACK.md").write_text("# Bad")
    with pytest.raises(TrackValidationError, match="Invalid track name"):
        Track.load(bad_dir / "TRACK.md", track_dir)


def test_load_tracks_from_dir_with_track_md(tmp_path: Path) -> None:
    """load_tracks_from_dir() should discover TRACK.md directories."""
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir()

    # Flat track
    (tracks_dir / "flat-track.md").write_text("---\ntriggers:\n  - flat\n---\n# Flat")

    # TRACK.md directory
    dir_track = tracks_dir / "dir-track"
    dir_track.mkdir()
    (dir_track / "TRACK.md").write_text("---\ntriggers:\n  - dir\n---\n# Dir")

    repo_tracks, knowledge_tracks, agent_tracks = load_tracks_from_dir(tracks_dir)
    assert "flat-track" in knowledge_tracks
    assert "dir-track" in agent_tracks
    assert agent_tracks["dir-track"].name == "dir-track"


def test_track_md_always_agent_track(tmp_path: Path) -> None:
    """TRACK.md directories should always be agent_tracks, even without triggers.

    AgentTracks are a separate category from Handprint tracks. They follow the
    AgentTracks standard and should be handled differently from regular .md files.
    """
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir()

    # Regular .md file without triggers -> repo_tracks
    (tracks_dir / "repo-style.md").write_text("# Repo Style\nNo triggers here.")

    # TRACK.md directory without triggers -> agent_tracks
    no_trigger_track = tracks_dir / "no-trigger-track"
    no_trigger_track.mkdir()
    (no_trigger_track / "TRACK.md").write_text("# No Trigger\nNo triggers here either.")

    repo_tracks, knowledge_tracks, agent_tracks = load_tracks_from_dir(tracks_dir)

    # Regular .md without triggers goes to repo_tracks
    assert "repo-style" in repo_tracks
    assert "repo-style" not in knowledge_tracks
    assert "repo-style" not in agent_tracks

    # TRACK.md goes to agent_tracks (separate category)
    assert "no-trigger-track" in agent_tracks
    assert "no-trigger-track" not in repo_tracks
    assert "no-trigger-track" not in knowledge_tracks
