"""Tests for load_project_tracks functionality."""

from handprint.sdk.tracks import (
    KeywordTrigger,
    load_project_tracks,
)


def test_load_project_tracks_no_directories(tmp_path):
    """Test load_project_tracks when no project tracks directories exist."""
    tracks = load_project_tracks(tmp_path)
    assert tracks == []


def test_load_project_tracks_agents_md_without_tracks_directory(tmp_path):
    """Test that AGENTS.md is loaded even when .handprint/tracks doesn't exist.

    This is a regression test for the bug where third-party track files like
    AGENTS.md were not loaded when the .handprint/tracks directory didn't exist.
    """
    # Create AGENTS.md in the work directory (no .handprint/tracks)
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Project Guidelines\n\nThis is the AGENTS.md content.")

    tracks = load_project_tracks(tmp_path)
    assert len(tracks) == 1
    assert tracks[0].name == "agents"
    assert "Project Guidelines" in tracks[0].content
    assert tracks[0].trigger is None  # Third-party tracks are always active


def test_load_project_tracks_agents_md_case_insensitive(tmp_path):
    """Test that AGENTS.md is loaded with case-insensitive matching."""
    # Create agents.md (lowercase) in the work directory
    agents_md = tmp_path / "agents.md"
    agents_md.write_text("# Lowercase agents.md content")

    tracks = load_project_tracks(tmp_path)
    assert len(tracks) == 1
    assert tracks[0].name == "agents"


def test_load_project_tracks_multiple_third_party_files(tmp_path):
    """Test loading multiple third-party track files."""
    # Create AGENTS.md
    (tmp_path / "AGENTS.md").write_text("# AGENTS.md content")

    # Create .cursorrules
    (tmp_path / ".cursorrules").write_text("# Cursor rules content")

    tracks = load_project_tracks(tmp_path)
    assert len(tracks) == 2
    track_names = {s.name for s in tracks}
    assert "agents" in track_names
    assert "cursorrules" in track_names


def test_load_project_tracks_third_party_with_tracks_directory(tmp_path):
    """Test third-party files are loaded alongside tracks from .handprint/tracks."""
    # Create AGENTS.md in work directory
    (tmp_path / "AGENTS.md").write_text("# AGENTS.md content")

    # Create .handprint/tracks directory with a track
    tracks_dir = tmp_path / ".handprint" / "tracks"
    tracks_dir.mkdir(parents=True)
    (tracks_dir / "test_track.md").write_text(
        "---\nname: test_track\ntriggers:\n  - test\n---\nTest track content."
    )

    tracks = load_project_tracks(tmp_path)
    assert len(tracks) == 2
    track_names = {s.name for s in tracks}
    assert "agents" in track_names
    assert "test_track" in track_names


def test_load_project_tracks_with_tracks_directory(tmp_path):
    """Test load_project_tracks loads from .handprint/tracks directory."""
    # Create .handprint/tracks directory
    tracks_dir = tmp_path / ".handprint" / "tracks"
    tracks_dir.mkdir(parents=True)

    # Create a test track file
    track_file = tracks_dir / "test_track.md"
    track_file.write_text(
        "---\nname: test_track\ntriggers:\n  - test\n---\nThis is a test track."
    )

    tracks = load_project_tracks(tmp_path)
    assert len(tracks) == 1
    assert tracks[0].name == "test_track"
    assert tracks[0].content == "This is a test track."
    assert isinstance(tracks[0].trigger, KeywordTrigger)


def test_load_project_tracks_with_agents_directory(tmp_path):
    """Test load_project_tracks loads from .agents/tracks directory."""
    # Create .agents/tracks directory
    tracks_dir = tmp_path / ".agents" / "tracks"
    tracks_dir.mkdir(parents=True)

    # Create a test track file
    track_file = tracks_dir / "agent_track.md"
    track_file.write_text(
        "---\nname: agent_track\ntriggers:\n  - agent\n---\nAgent track content."
    )

    tracks = load_project_tracks(tmp_path)
    assert len(tracks) == 1
    assert tracks[0].name == "agent_track"
    assert tracks[0].content == "Agent track content."
    assert isinstance(tracks[0].trigger, KeywordTrigger)


def test_load_project_tracks_agents_directory_precedence(tmp_path):
    """Test .agents/tracks takes precedence over other directories."""
    agents_dir = tmp_path / ".agents" / "tracks"
    tracks_dir = tmp_path / ".handprint" / "tracks"
    microagents_dir = tmp_path / ".handprint" / "microagents"
    agents_dir.mkdir(parents=True)
    tracks_dir.mkdir(parents=True)
    microagents_dir.mkdir(parents=True)

    (agents_dir / "duplicate.md").write_text(
        "---\nname: duplicate\n---\nFrom .agents/tracks."
    )
    (tracks_dir / "duplicate.md").write_text(
        "---\nname: duplicate\n---\nFrom .handprint/tracks."
    )
    (microagents_dir / "duplicate.md").write_text(
        "---\nname: duplicate\n---\nFrom .handprint/microagents."
    )

    tracks = load_project_tracks(tmp_path)
    assert len(tracks) == 1
    assert tracks[0].name == "duplicate"
    assert tracks[0].content == "From .agents/tracks."


def test_load_project_tracks_merges_agents_and_handprint(tmp_path):
    """Test loading unique tracks from .agents/tracks and .handprint/tracks."""
    agents_dir = tmp_path / ".agents" / "tracks"
    handprint_dir = tmp_path / ".handprint" / "tracks"
    agents_dir.mkdir(parents=True)
    handprint_dir.mkdir(parents=True)

    (agents_dir / "agent_track.md").write_text(
        "---\nname: agent_track\n---\nAgent track content."
    )
    (handprint_dir / "legacy_track.md").write_text(
        "---\nname: legacy_track\n---\nLegacy track content."
    )

    tracks = load_project_tracks(tmp_path)
    assert len(tracks) == 2
    track_names = {track.name for track in tracks}
    assert track_names == {"agent_track", "legacy_track"}


def test_load_project_tracks_with_microagents_directory(tmp_path):
    """Test load_project_tracks loads from .handprint/microagents directory (legacy)."""
    # Create .handprint/microagents directory
    microagents_dir = tmp_path / ".handprint" / "microagents"
    microagents_dir.mkdir(parents=True)

    # Create a test microagent file
    microagent_file = microagents_dir / "legacy_track.md"
    microagent_file.write_text(
        "---\n"
        "name: legacy_track\n"
        "triggers:\n"
        "  - legacy\n"
        "---\n"
        "This is a legacy microagent track."
    )

    tracks = load_project_tracks(tmp_path)
    assert len(tracks) == 1
    assert tracks[0].name == "legacy_track"
    assert tracks[0].content == "This is a legacy microagent track."


def test_load_project_tracks_priority_order(tmp_path):
    """Test that tracks/ directory takes precedence over microagents/."""
    # Create both directories
    tracks_dir = tmp_path / ".handprint" / "tracks"
    microagents_dir = tmp_path / ".handprint" / "microagents"
    tracks_dir.mkdir(parents=True)
    microagents_dir.mkdir(parents=True)

    # Create duplicate track in both directories
    (tracks_dir / "duplicate.md").write_text(
        "---\nname: duplicate\n---\nFrom tracks directory."
    )

    (microagents_dir / "duplicate.md").write_text(
        "---\nname: duplicate\n---\nFrom microagents directory."
    )

    tracks = load_project_tracks(tmp_path)
    assert len(tracks) == 1
    assert tracks[0].name == "duplicate"
    # Should be from tracks directory (takes precedence)
    assert tracks[0].content == "From tracks directory."


def test_load_project_tracks_both_directories(tmp_path):
    """Test loading unique tracks from both directories."""
    # Create both directories
    tracks_dir = tmp_path / ".handprint" / "tracks"
    microagents_dir = tmp_path / ".handprint" / "microagents"
    tracks_dir.mkdir(parents=True)
    microagents_dir.mkdir(parents=True)

    # Create different tracks in each directory
    (tracks_dir / "track1.md").write_text("---\nname: track1\n---\nTrack 1 content.")
    (microagents_dir / "track2.md").write_text(
        "---\nname: track2\n---\nTrack 2 content."
    )

    tracks = load_project_tracks(tmp_path)
    assert len(tracks) == 2
    track_names = {s.name for s in tracks}
    assert track_names == {"track1", "track2"}


def test_load_project_tracks_handles_errors_gracefully(tmp_path):
    """Test that errors in loading are handled gracefully."""
    # Create .handprint/tracks directory
    tracks_dir = tmp_path / ".handprint" / "tracks"
    tracks_dir.mkdir(parents=True)

    # Create an invalid track file
    invalid_file = tracks_dir / "invalid.md"
    invalid_file.write_text(
        "---\n"
        "triggers: not_a_list\n"  # Invalid: triggers must be a list
        "---\n"
        "Invalid track."
    )

    # Should not raise exception, just return empty list
    tracks = load_project_tracks(tmp_path)
    assert tracks == []


def test_load_project_tracks_one_bad_track_does_not_break_others(tmp_path):
    """Test that one invalid track doesn't prevent other valid tracks from loading.

    This is a regression test for the bug where a single track validation error
    would cause ALL tracks in the directory to fail loading.
    """
    # Create .handprint/tracks directory
    tracks_dir = tmp_path / ".handprint" / "tracks"
    tracks_dir.mkdir(parents=True)

    # Create a valid track
    valid_track = tracks_dir / "valid-track.md"
    valid_track.write_text(
        "---\nname: valid-track\ntriggers:\n  - valid\n---\nThis is a valid track."
    )

    # Create an invalid track (name doesn't match filename)
    invalid_track_dir = tracks_dir / "bad-track"
    invalid_track_dir.mkdir()
    (invalid_track_dir / "TRACK.md").write_text(
        "---\n"
        "name: wrong_name\n"  # Name has underscore, doesn't match dir
        "---\n"
        "This track has a mismatched name."
    )

    # Create another valid track
    another_valid = tracks_dir / "another-valid.md"
    another_valid.write_text(
        "---\nname: another-valid\ntriggers:\n  - another\n---\nAnother valid track."
    )

    # Should load valid tracks despite the invalid one
    tracks = load_project_tracks(tmp_path)

    # Both valid tracks should be loaded
    track_names = {s.name for s in tracks}
    assert "valid-track" in track_names
    assert "another-valid" in track_names
    # Invalid track should NOT be loaded
    assert "wrong_name" not in track_names
    assert "bad-track" not in track_names


def test_long_description_track_does_not_break_other_tracks(tmp_path):
    """Regression test: a track with a very long description should not
    prevent other valid tracks in the same directory from loading.

    The description should be silently truncated (via maybe_truncate)
    rather than raising an error.
    """
    tracks_dir = tmp_path / ".agents" / "tracks"
    tracks_dir.mkdir(parents=True)

    # Create a valid track
    (tracks_dir / "good-track.md").write_text(
        "---\nname: good-track\ntriggers:\n  - good\n---\nGood track content."
    )

    # Create a track with a description exceeding 1024 chars
    long_desc = "A" * 2000
    bad_track_dir = tracks_dir / "bad-track"
    bad_track_dir.mkdir()
    (bad_track_dir / "TRACK.md").write_text(
        f"---\nname: bad-track\ndescription: {long_desc}\n---\n"
        "# Bad Track\nContent here."
    )

    tracks = load_project_tracks(tmp_path)
    track_names = {s.name for s in tracks}

    # The good track must load regardless
    assert "good-track" in track_names

    # The bad track should also load (description truncated, not rejected)
    assert "bad-track" in track_names
    bad = next(s for s in tracks if s.name == "bad-track")
    assert bad.description is not None
    assert len(bad.description) <= 1024


def test_load_project_tracks_with_string_path(tmp_path):
    """Test that load_project_tracks accepts string paths."""
    # Create .handprint/tracks directory
    tracks_dir = tmp_path / ".handprint" / "tracks"
    tracks_dir.mkdir(parents=True)

    # Create a test track file
    track_file = tracks_dir / "test_track.md"
    track_file.write_text("---\nname: test_track\n---\nTest track content.")

    # Pass path as string
    tracks = load_project_tracks(str(tmp_path))
    assert len(tracks) == 1
    assert tracks[0].name == "test_track"


def test_load_project_tracks_loads_from_git_root_when_called_from_subdir(tmp_path):
    """Running from a subdir should still load repo-level tracks (git root)."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("# Project Guidelines\n\nFrom root")

    subdir = tmp_path / "subdir"
    subdir.mkdir()

    tracks = load_project_tracks(subdir)
    assert any(s.name == "agents" and "From root" in s.content for s in tracks)


def test_load_project_tracks_workdir_takes_precedence_over_git_root(tmp_path):
    """More local (work dir) tracks should override repo root tracks."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("# Project Guidelines\n\nFrom root")

    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "AGENTS.md").write_text("# Project Guidelines\n\nFrom subdir")

    tracks = load_project_tracks(subdir)
    agents = [s for s in tracks if s.name == "agents"]
    assert len(agents) == 1
    assert agents[0].content.strip() == "# Project Guidelines\n\nFrom subdir"


def test_load_project_tracks_loads_tracks_directories_from_git_root(tmp_path):
    """Tracks directories (.agents/tracks etc.) should be loaded from git root."""
    (tmp_path / ".git").mkdir()

    tracks_dir = tmp_path / ".agents" / "tracks"
    tracks_dir.mkdir(parents=True)
    (tracks_dir / "root_track.md").write_text(
        "---\nname: root_track\ntriggers:\n  - root\n---\nLoaded from root"
    )

    subdir = tmp_path / "subdir"
    subdir.mkdir()

    tracks = load_project_tracks(subdir)
    assert any(
        s.name == "root_track" and "Loaded from root" in s.content for s in tracks
    )
