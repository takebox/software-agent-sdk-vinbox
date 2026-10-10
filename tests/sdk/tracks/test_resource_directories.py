"""Tests for resource directories support (Issue #1477)."""

from pathlib import Path

from handprint.sdk.tracks import (
    RESOURCE_DIRECTORIES,
    Track,
    TrackResources,
    discover_track_resources,
)
from handprint.sdk.utils.path import to_posix_path


def test_track_resources_model(tmp_path: Path) -> None:
    """TrackResources should track resources and provide directory paths."""
    # Empty resources
    resources = TrackResources(track_root="/path/to/track")
    assert not resources.has_resources()

    # With resources
    resources = TrackResources(track_root="/path", scripts=["run.sh"])
    assert resources.has_resources()

    # Directory path getters
    track_dir = tmp_path / "my-track"
    track_dir.mkdir()
    (track_dir / "scripts").mkdir()
    resources = TrackResources(track_root=str(track_dir))
    assert resources.get_scripts_dir() == track_dir / "scripts"
    assert resources.get_references_dir() is None  # Doesn't exist


def test_discover_track_resources(tmp_path: Path) -> None:
    """discover_track_resources() should find files in resource directories."""
    track_dir = tmp_path / "my-track"
    track_dir.mkdir()

    # Create resource directories with files
    scripts_dir = track_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.sh").write_text("#!/bin/bash")
    subdir = scripts_dir / "utils"
    subdir.mkdir()
    (subdir / "helper.py").write_text("# helper")

    refs_dir = track_dir / "references"
    refs_dir.mkdir()
    (refs_dir / "guide.md").write_text("# Guide")

    resources = discover_track_resources(track_dir)
    assert isinstance(resources, TrackResources)
    assert "run.sh" in resources.scripts
    assert "utils/helper.py" in resources.scripts  # Nested files
    assert "guide.md" in resources.references
    assert resources.assets == []  # No assets dir
    assert resources.track_root == to_posix_path(track_dir.resolve())


def test_resource_directories_constant() -> None:
    """RESOURCE_DIRECTORIES should contain standard directory names."""
    assert set(RESOURCE_DIRECTORIES) == {"scripts", "references", "assets"}


def test_track_load_with_resources(tmp_path: Path) -> None:
    """Track.load() should discover resources for TRACK.md directories."""
    track_dir = tmp_path / "tracks"
    track_dir.mkdir()
    my_track_dir = track_dir / "my-track"
    my_track_dir.mkdir()

    (my_track_dir / "TRACK.md").write_text("# My Track")
    scripts_dir = my_track_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.sh").write_text("#!/bin/bash")

    # TRACK.md directory format - should have resources (auto-detects directory name)
    track = Track.load(my_track_dir / "TRACK.md", track_dir)
    assert track.resources is not None
    assert "run.sh" in track.resources.scripts

    # Flat file format - should not have resources
    flat_track = track_dir / "flat.md"
    flat_track.write_text("# Flat Track")
    track = Track.load(flat_track, track_dir)
    assert track.resources is None
