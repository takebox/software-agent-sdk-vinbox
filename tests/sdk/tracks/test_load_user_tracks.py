"""Tests for load_user_tracks functionality."""

import tempfile
from pathlib import Path

import pytest

from handprint.sdk.context.agent_context import AgentContext
from handprint.sdk.tracks import (
    KeywordTrigger,
    Track,
    installed,
    load_user_tracks,
    track,
)
from handprint.sdk.tracks.installed import disable_track, install_track


@pytest.fixture
def temp_user_tracks_dir():
    """Create a temporary user tracks directory structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        # Create .agents/tracks directory
        agents_dir = root / ".agents" / "tracks"
        agents_dir.mkdir(parents=True)

        # Create .handprint/tracks directory
        tracks_dir = root / ".handprint" / "tracks"
        tracks_dir.mkdir(parents=True)

        yield root, agents_dir, tracks_dir


@pytest.fixture
def temp_microagents_dir():
    """Create a temporary microagents directory structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        # Create .handprint/microagents directory
        microagents_dir = root / ".handprint" / "microagents"
        microagents_dir.mkdir(parents=True)

        yield root, microagents_dir


def test_load_user_tracks_no_directories(tmp_path):
    """Test load_user_tracks when no user tracks directories exist."""
    # Point USER_TRACKS_DIRS to non-existent directories
    from handprint.sdk.tracks import track

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [
            tmp_path / "nonexistent1",
            tmp_path / "nonexistent2",
        ]
        tracks = load_user_tracks()
        assert tracks == []
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_load_user_tracks_with_agents_directory(temp_user_tracks_dir):
    """Test load_user_tracks loads from .agents/tracks directory."""
    root, agents_dir, _ = temp_user_tracks_dir

    # Create a test track file
    track_file = agents_dir / "agent_track.md"
    track_file.write_text(
        "---\nname: agent_track\ntriggers:\n  - agent\n---\nAgent track content."
    )

    from handprint.sdk.tracks import track

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [agents_dir]
        tracks = load_user_tracks()
        assert len(tracks) == 1
        assert tracks[0].name == "agent_track"
        assert tracks[0].content == "Agent track content."
        assert isinstance(tracks[0].trigger, KeywordTrigger)
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_load_user_tracks_with_tracks_directory(temp_user_tracks_dir):
    """Test load_user_tracks loads from .handprint/tracks directory."""
    root, _, tracks_dir = temp_user_tracks_dir

    # Create a test track file
    track_file = tracks_dir / "test_track.md"
    track_file.write_text(
        "---\nname: test_track\ntriggers:\n  - test\n---\nThis is a test track."
    )

    from handprint.sdk.tracks import track

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [tracks_dir]
        tracks = load_user_tracks()
        assert len(tracks) == 1
        assert tracks[0].name == "test_track"
        assert tracks[0].content == "This is a test track."
        assert isinstance(tracks[0].trigger, KeywordTrigger)
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_load_user_tracks_with_microagents_directory(temp_microagents_dir):
    """Test load_user_tracks loads from microagents directory (legacy)."""
    root, microagents_dir = temp_microagents_dir

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

    from handprint.sdk.tracks import track

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [microagents_dir]
        tracks = load_user_tracks()
        assert len(tracks) == 1
        assert tracks[0].name == "legacy_track"
        assert tracks[0].content == "This is a legacy microagent track."
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_load_user_tracks_priority_order(tmp_path):
    """Test precedence .agents/tracks > .handprint/tracks > microagents."""
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

    from handprint.sdk.tracks import track

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [agents_dir, tracks_dir, microagents_dir]
        tracks = load_user_tracks()
        assert len(tracks) == 1
        assert tracks[0].name == "duplicate"
        assert tracks[0].content == "From .agents/tracks."
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_load_user_tracks_merges_all_directories(tmp_path):
    """Test loading unique tracks from .agents/tracks, .handprint/tracks,
    microagents.
    """
    agents_dir = tmp_path / ".agents" / "tracks"
    tracks_dir = tmp_path / ".handprint" / "tracks"
    microagents_dir = tmp_path / ".handprint" / "microagents"
    agents_dir.mkdir(parents=True)
    tracks_dir.mkdir(parents=True)
    microagents_dir.mkdir(parents=True)

    (agents_dir / "agent_track.md").write_text(
        "---\nname: agent_track\n---\nAgent track content."
    )
    (tracks_dir / "track1.md").write_text("---\nname: track1\n---\nTrack 1 content.")
    (microagents_dir / "track2.md").write_text(
        "---\nname: track2\n---\nTrack 2 content."
    )

    from handprint.sdk.tracks import track

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [agents_dir, tracks_dir, microagents_dir]
        tracks = load_user_tracks()
        assert len(tracks) == 3
        track_names = {s.name for s in tracks}
        assert track_names == {"agent_track", "track1", "track2"}
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_load_user_tracks_handles_errors_gracefully(temp_user_tracks_dir):
    """Test that errors in loading are handled gracefully."""
    root, _, tracks_dir = temp_user_tracks_dir

    # Create an invalid track file
    invalid_file = tracks_dir / "invalid.md"
    invalid_file.write_text(
        "---\n"
        "triggers: not_a_list\n"  # Invalid: triggers must be a list
        "---\n"
        "Invalid track."
    )

    from handprint.sdk.tracks import track

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [tracks_dir]
        # Should not raise exception, just return empty list
        tracks = load_user_tracks()
        assert tracks == []
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_agent_context_loads_user_tracks_by_default(temp_user_tracks_dir):
    """Test that AgentContext loads user tracks when enabled."""
    root, _, tracks_dir = temp_user_tracks_dir

    # Create a test track
    track_file = tracks_dir / "auto_track.md"
    track_file.write_text("---\nname: auto_track\n---\nAutomatically loaded track.")

    from handprint.sdk.tracks import track

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [tracks_dir]
        context = AgentContext(load_user_tracks=True)
        track_names = [s.name for s in context.tracks]
        assert "auto_track" in track_names
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_agent_context_can_disable_user_tracks_loading():
    """Test that user tracks loading can be disabled."""
    context = AgentContext(load_user_tracks=False)
    assert context.tracks == []


def test_agent_context_merges_explicit_and_user_tracks(temp_user_tracks_dir):
    """Test that explicit tracks and user tracks are merged correctly."""
    root, _, tracks_dir = temp_user_tracks_dir

    # Create user track
    user_track_file = tracks_dir / "user_track.md"
    user_track_file.write_text("---\nname: user_track\n---\nUser track content.")

    # Create explicit track
    explicit_track = Track(
        name="explicit_track",
        content="Explicit track content.",
        trigger=None,
    )

    from handprint.sdk.tracks import track

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [tracks_dir]
        context = AgentContext(tracks=[explicit_track], load_user_tracks=True)
        track_names = [s.name for s in context.tracks]
        assert "explicit_track" in track_names
        assert "user_track" in track_names
        assert len(context.tracks) == 2
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_agent_context_explicit_track_takes_precedence(temp_user_tracks_dir):
    """Test that explicitly provided tracks take precedence over user tracks."""
    root, _, tracks_dir = temp_user_tracks_dir

    # Create user track with same name
    user_track_file = tracks_dir / "duplicate.md"
    user_track_file.write_text("---\nname: duplicate\n---\nUser track content.")

    # Create explicit track with same name
    explicit_track = Track(
        name="duplicate",
        content="Explicit track content.",
        trigger=None,
    )

    from handprint.sdk.tracks import track

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [tracks_dir]
        context = AgentContext(tracks=[explicit_track], load_user_tracks=True)
        assert len(context.tracks) == 1
        # Explicit track should be used, not the user track
        assert context.tracks[0].content == "Explicit track content."
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_load_user_tracks_includes_installed_tracks(tmp_path, monkeypatch):
    """Test that load_user_tracks also loads enabled installed tracks."""
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir()
    installed_dir = tmp_path / "tracks" / "installed"
    installed_dir.mkdir()

    # Create and install a track
    source_dir = tmp_path / "my-installed-track"
    source_dir.mkdir()
    (source_dir / "TRACK.md").write_text(
        "---\nname: my-installed-track\ndescription: Installed track\n---\n"
        "Installed track content."
    )
    install_track(str(source_dir), installed_dir=installed_dir)

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [tracks_dir]
        monkeypatch.setattr(installed, "DEFAULT_INSTALLED_TRACKS_DIR", installed_dir)
        tracks = load_user_tracks()
        track_names = {s.name for s in tracks}
        assert "my-installed-track" in track_names
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_load_user_tracks_user_track_takes_precedence_over_installed(
    tmp_path, monkeypatch
):
    """Test that user tracks take precedence over installed tracks."""
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir()
    installed_dir = tmp_path / "tracks" / "installed"
    installed_dir.mkdir()

    # Create a user track
    (tracks_dir / "duplicate.md").write_text("---\nname: duplicate\n---\nUser version.")

    # Install a track with the same name
    source_dir = tmp_path / "duplicate"
    source_dir.mkdir()
    (source_dir / "TRACK.md").write_text(
        "---\nname: duplicate\ndescription: dup\n---\nInstalled version."
    )
    install_track(str(source_dir), installed_dir=installed_dir)

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [tracks_dir]
        monkeypatch.setattr(installed, "DEFAULT_INSTALLED_TRACKS_DIR", installed_dir)
        tracks = load_user_tracks()
        dupes = [s for s in tracks if s.name == "duplicate"]
        assert len(dupes) == 1
        assert dupes[0].content == "User version."
    finally:
        track.USER_TRACKS_DIRS = original_dirs


def test_load_user_tracks_disabled_installed_track_excluded(tmp_path, monkeypatch):
    """Test that disabled installed tracks are not loaded."""
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir()
    installed_dir = tmp_path / "tracks" / "installed"
    installed_dir.mkdir()

    # Install and disable a track
    source_dir = tmp_path / "disabled-track"
    source_dir.mkdir()
    (source_dir / "TRACK.md").write_text(
        "---\nname: disabled-track\ndescription: test\n---\nContent."
    )
    install_track(str(source_dir), installed_dir=installed_dir)
    disable_track("disabled-track", installed_dir=installed_dir)

    original_dirs = track.USER_TRACKS_DIRS
    try:
        track.USER_TRACKS_DIRS = [tracks_dir]
        monkeypatch.setattr(installed, "DEFAULT_INSTALLED_TRACKS_DIR", installed_dir)
        tracks = load_user_tracks()
        track_names = {s.name for s in tracks}
        assert "disabled-track" not in track_names
    finally:
        track.USER_TRACKS_DIRS = original_dirs


@pytest.mark.parametrize("enabled", [True, False])
def test_installed_track_resources_do_not_leak_into_user_tracks(
    tmp_path, monkeypatch, enabled
):
    tracks_dir = tmp_path / "tracks"
    installed_dir = tracks_dir / "installed"
    source = tmp_path / "resource-track"
    source.mkdir()
    (source / "TRACK.md").write_text(
        "---\nname: resource-track\ndescription: Resource track\n---\nInstructions."
    )
    for directory in ("commands", "references"):
        (source / directory).mkdir()
        (source / directory / "notes.md").write_text("Private resource instructions.")
    install_track(str(source), installed_dir=installed_dir)
    if not enabled:
        disable_track("resource-track", installed_dir=installed_dir)

    (tracks_dir / "legacy").mkdir()
    (tracks_dir / "legacy" / "notes.md").write_text("Legacy instructions.")
    direct = tracks_dir / "direct-track"
    direct.mkdir()
    (direct / "TRACK.md").write_text(
        "---\nname: direct-track\ndescription: Direct track\n---\nInstructions."
    )
    (direct / "reference.md").write_text("Direct resource instructions.")
    monkeypatch.setattr(track, "USER_TRACKS_DIRS", [tracks_dir])
    monkeypatch.setattr(installed, "DEFAULT_INSTALLED_TRACKS_DIR", installed_dir)

    loaded = load_user_tracks()
    expected = {"legacy/notes", "direct-track"}
    if enabled:
        expected.add("resource-track")
    assert {entry.name for entry in loaded} == expected
    assert len(loaded) == len(expected)
    assert (installed_dir / "resource-track" / "references" / "notes.md").is_file()


def test_user_tracks_survive_symlink_loop_next_to_installed_dir(tmp_path, monkeypatch):
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir()
    (tracks_dir / "good.md").write_text("Good instructions.")
    (tracks_dir / "a.md").symlink_to(tracks_dir / "b.md")
    (tracks_dir / "b.md").symlink_to(tracks_dir / "a.md")
    monkeypatch.setattr(track, "USER_TRACKS_DIRS", [tracks_dir])
    monkeypatch.setattr(
        installed, "DEFAULT_INSTALLED_TRACKS_DIR", tracks_dir / "installed"
    )

    assert [entry.name for entry in load_user_tracks()] == ["good"]


def test_installed_dir_excluded_through_symlinked_user_tracks_dir(
    tmp_path, monkeypatch
):
    tracks_dir = tmp_path / "handprint" / "tracks"
    installed_dir = tracks_dir / "installed"
    (installed_dir / "pkg" / "references").mkdir(parents=True)
    (installed_dir / "pkg" / "references" / "notes.md").write_text("Package notes.")
    agents_tracks_dir = tmp_path / "agents" / "tracks"
    agents_tracks_dir.parent.mkdir()
    agents_tracks_dir.symlink_to(tracks_dir, target_is_directory=True)
    monkeypatch.setattr(track, "USER_TRACKS_DIRS", [agents_tracks_dir, tracks_dir])
    monkeypatch.setattr(installed, "DEFAULT_INSTALLED_TRACKS_DIR", installed_dir)

    assert load_user_tracks() == []


def test_load_tracks_from_dir_keeps_installed_dir_without_exclusion(tmp_path):
    tracks_dir = tmp_path / "tracks"
    (tracks_dir / "installed" / "pkg" / "references").mkdir(parents=True)
    (tracks_dir / "installed" / "pkg" / "references" / "notes.md").write_text(
        "Package notes."
    )

    repo_tracks, _, _ = track.load_tracks_from_dir(tracks_dir)

    assert "installed/pkg/references/notes" in repo_tracks
