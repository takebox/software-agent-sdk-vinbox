"""Tests for load_public_tracks functionality with git-based caching."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from handprint.sdk.context.agent_context import AgentContext
from handprint.sdk.tracks import (
    KeywordTrigger,
    Track,
    load_public_tracks,
)
from handprint.sdk.tracks.track import (
    _invalidate_public_tracks_cache,
    load_marketplace_track_names,
)
from handprint.sdk.tracks.utils import update_tracks_repository


@pytest.fixture(autouse=True)
def _clear_public_tracks_cache():
    """Clear the public-tracks in-memory cache between tests.

    The cache is process-global, so without clearing it, results from one test
    leak into later tests that mock ``update_tracks_repository`` differently.
    """
    _invalidate_public_tracks_cache()
    yield
    _invalidate_public_tracks_cache()


@pytest.fixture
def mock_repo_dir(tmp_path):
    """Create a mock git repository with tracks."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()

    # Create tracks directory
    tracks_dir = repo_dir / "tracks"
    tracks_dir.mkdir()

    # Create track files
    git_track = tracks_dir / "git.md"
    git_track.write_text(
        "---\n"
        "name: git\n"
        "triggers:\n"
        "  - git\n"
        "  - github\n"
        "---\n"
        "Git best practices and commands."
    )

    docker_track = tracks_dir / "docker.md"
    docker_track.write_text(
        "---\n"
        "name: docker\n"
        "triggers:\n"
        "  - docker\n"
        "  - container\n"
        "---\n"
        "Docker guidelines and commands."
    )

    testing_track = tracks_dir / "testing.md"
    testing_track.write_text(
        "---\nname: testing\n---\nTesting guidelines for all repos."
    )

    # Create .git directory to simulate a git repo
    git_dir = repo_dir / ".git"
    git_dir.mkdir()

    return repo_dir


@pytest.fixture
def mock_repo_with_agenttracks_references(tmp_path):
    """Create a mock repo with AgentTracks-style tracks with reference markdown files.

    This reproduces the issue where markdown files in subdirectories of a TRACK.md
    directory (like themes/ or references/) are incorrectly loaded as separate tracks.
    See: https://github.com/takebox/software-agent-sdk/issues/1981
    """
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()

    # Create tracks directory
    tracks_dir = repo_dir / "tracks"
    tracks_dir.mkdir()

    # Create theme-factory track with TRACK.md and reference markdown files in themes/
    theme_factory_dir = tracks_dir / "theme-factory"
    theme_factory_dir.mkdir()

    # Main TRACK.md file
    track_md = theme_factory_dir / "TRACK.md"
    track_md.write_text(
        "---\n"
        "name: theme-factory\n"
        "description: Toolkit for styling artifacts with a theme.\n"
        "---\n"
        "# Theme Factory Track\n\n"
        "This track provides a curated collection of professional themes.\n"
    )

    # Create themes subdirectory with reference markdown files
    themes_dir = theme_factory_dir / "themes"
    themes_dir.mkdir()

    # These are reference files, NOT separate tracks
    (themes_dir / "arctic-frost.md").write_text(
        "# Arctic Frost\n\nA cool and crisp winter-inspired theme.\n"
    )
    (themes_dir / "ocean-depths.md").write_text(
        "# Ocean Depths\n\nA professional and calming maritime theme.\n"
    )
    (themes_dir / "sunset-boulevard.md").write_text(
        "# Sunset Boulevard\n\nWarm and vibrant sunset colors.\n"
    )

    # Create readiness-report track with references/ subdirectory
    readiness_dir = tracks_dir / "readiness-report"
    readiness_dir.mkdir()

    (readiness_dir / "TRACK.md").write_text(
        "---\n"
        "name: readiness-report\n"
        "description: Generate readiness reports.\n"
        "---\n"
        "# Readiness Report Track\n"
    )

    # Create references subdirectory with reference markdown files
    refs_dir = readiness_dir / "references"
    refs_dir.mkdir()

    (refs_dir / "criteria.md").write_text("# Criteria\n\nEvaluation criteria.\n")
    (refs_dir / "maturity-levels.md").write_text(
        "# Maturity Levels\n\nMaturity level definitions.\n"
    )

    # Create a regular legacy track (not AgentTracks format)
    legacy_track = tracks_dir / "legacy-track.md"
    legacy_track.write_text(
        "---\nname: legacy-track\ntriggers:\n  - legacy\n---\nA legacy format track.\n"
    )

    # Create .git directory to simulate a git repo
    git_dir = repo_dir / ".git"
    git_dir.mkdir()

    return repo_dir


def test_load_public_tracks_success(mock_repo_dir, tmp_path):
    """Test successfully loading tracks from cached repository."""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_dir

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks()
        assert len(tracks) == 3
        track_names = {s.name for s in tracks}
        assert track_names == {"git", "docker", "testing"}

        # Check git track details
        git_track = next(s for s in tracks if s.name == "git")
        assert isinstance(git_track.trigger, KeywordTrigger)
        assert "git" in git_track.trigger.keywords

        # Check testing track (no trigger - always active)
        testing_track = next(s for s in tracks if s.name == "testing")
        assert testing_track.trigger is None


def test_load_public_tracks_repo_update_fails(tmp_path):
    """Test handling when repository update fails."""

    def mock_update_repo(repo_url, branch, cache_dir):
        return None

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks()
        assert tracks == []


def test_load_public_tracks_no_tracks_directory(tmp_path):
    """Test handling when tracks directory doesn't exist in repo."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    # No tracks directory created

    def mock_update_repo(repo_url, branch, cache_dir):
        return repo_dir

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks()
        assert tracks == []


def test_load_public_tracks_with_invalid_track(tmp_path):
    """Test that invalid tracks are skipped gracefully."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    tracks_dir = repo_dir / "tracks"
    tracks_dir.mkdir()

    # Valid track
    valid_track = tracks_dir / "valid.md"
    valid_track.write_text("---\nname: valid\n---\nValid track content.")

    # Invalid track
    invalid_track = tracks_dir / "invalid.md"
    invalid_track.write_text(
        "---\nname: invalid\ntriggers: not_a_list\n---\nInvalid track."
    )

    def mock_update_repo(repo_url, branch, cache_dir):
        return repo_dir

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks()
        # Only valid track should be loaded, invalid one skipped
        assert len(tracks) == 1
        assert tracks[0].name == "valid"


def test_update_tracks_repository_clone_new(tmp_path):
    """Test cloning a new repository."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch(
        "handprint.sdk.git.utils.subprocess.run", return_value=mock_result
    ) as mock_run:
        repo_path = update_tracks_repository(
            "https://github.com/takebox/extensions",
            "main",
            cache_dir,
        )

        assert repo_path is not None
        # Check that git clone was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0][0] == "git"
        assert call_args[0][0][1] == "clone"
        assert "--branch" in call_args[0][0]
        assert "main" in call_args[0][0]


def test_update_tracks_repository_update_existing(tmp_path):
    """Test updating an existing repository."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    # Create existing repo with .git directory
    repo_path = cache_dir / "public-tracks"
    repo_path.mkdir()
    git_dir = repo_path / ".git"
    git_dir.mkdir()

    mock_result = MagicMock()
    mock_result.returncode = 0
    # Simulate being on a branch (not detached HEAD) so reset is called
    mock_result.stdout = "main"

    with patch(
        "handprint.sdk.git.utils.subprocess.run", return_value=mock_result
    ) as mock_run:
        result_path = update_tracks_repository(
            "https://github.com/takebox/extensions",
            "main",
            cache_dir,
        )

        assert result_path == repo_path
        # For a branch ref, the sequence is:
        #   1. checkout (optimistic local attempt)
        #   2. rev-parse (detects we're on a branch → fall through to fetch)
        #   3. fetch
        #   4. checkout (proper update inside _try_checkout_and_reset)
        #   5. rev-parse (detects branch again inside _checkout_ref)
        #   6. reset --hard origin/main
        assert mock_run.call_count == 6
        all_commands = [call[0][0] for call in mock_run.call_args_list]
        assert all_commands[0][:2] == ["git", "checkout"]
        assert all_commands[1] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]
        assert all_commands[2][:3] == ["git", "fetch", "origin"]
        assert all_commands[3][:2] == ["git", "checkout"]
        assert all_commands[4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]
        assert all_commands[5][:3] == ["git", "reset", "--hard"]


def test_update_tracks_repository_clone_timeout(tmp_path):
    """Test handling of timeout during clone."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    with patch(
        "handprint.sdk.git.utils.subprocess.run",
        side_effect=subprocess.TimeoutExpired("git", 60),
    ) as mock_run:
        repo_path = update_tracks_repository(
            "https://github.com/takebox/extensions",
            "main",
            cache_dir,
        )

        assert repo_path is None
        mock_run.assert_called_once()


def test_update_tracks_repository_update_fails_uses_cache(tmp_path):
    """Test that existing cache is used when update fails."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    # Create existing repo with .git directory
    repo_path = cache_dir / "public-tracks"
    repo_path.mkdir()
    git_dir = repo_path / ".git"
    git_dir.mkdir()

    # Mock subprocess.run to return a failed result (non-zero return code)
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "Error: fetch failed"

    with patch(
        "handprint.sdk.git.utils.subprocess.run",
        return_value=mock_result,
    ):
        result_path = update_tracks_repository(
            "https://github.com/takebox/extensions",
            "main",
            cache_dir,
        )

        # Should still return the cached path even though update failed
        assert result_path == repo_path


def test_agent_context_loads_public_tracks(mock_repo_dir, tmp_path):
    """Test that AgentContext loads public tracks when enabled."""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_dir

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        context = AgentContext(load_public_tracks=True)
        track_names = {s.name for s in context.tracks}
        assert "git" in track_names
        assert "docker" in track_names
        assert "testing" in track_names


def test_agent_context_uses_custom_marketplace_path(
    mock_repo_with_marketplace, tmp_path
):
    """Test that AgentContext forwards marketplace_path to public track loading."""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_with_marketplace

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        context = AgentContext(
            load_public_tracks=True,
            marketplace_path="marketplaces/custom.json",
        )

    track_names = {s.name for s in context.tracks}
    assert track_names == {"git", "internal-only"}


def test_agent_context_can_disable_public_tracks_loading():
    """Test that public tracks loading can be disabled."""
    context = AgentContext(load_public_tracks=False)
    assert context.tracks == []


def test_agent_context_merges_explicit_and_public_tracks(mock_repo_dir, tmp_path):
    """Test that explicit tracks and public tracks are merged correctly."""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_dir

    # Create explicit track
    explicit_track = Track(
        name="explicit_track",
        content="Explicit track content.",
        trigger=None,
    )

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        context = AgentContext(tracks=[explicit_track], load_public_tracks=True)
        track_names = {s.name for s in context.tracks}
        assert "explicit_track" in track_names
        assert "git" in track_names
        assert len(context.tracks) == 4  # 1 explicit + 3 public


def test_agent_context_explicit_track_takes_precedence(mock_repo_dir, tmp_path):
    """Test that explicitly provided tracks take precedence over public tracks."""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_dir

    # Create explicit track with same name as public track
    explicit_track = Track(
        name="git",
        content="Explicit git track content.",
        trigger=None,
    )

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        context = AgentContext(tracks=[explicit_track], load_public_tracks=True)
        # Should have 3 tracks (1 explicit git + 2 other public tracks)
        assert len(context.tracks) == 3
        git_track = next(s for s in context.tracks if s.name == "git")
        # Explicit track should be used, not the public track
        assert git_track.content == "Explicit git track content."


def test_load_public_tracks_custom_repo(mock_repo_dir, tmp_path):
    """Test loading from a custom repository URL."""

    def mock_update_repo(repo_url, branch, cache_dir):
        assert repo_url == "https://github.com/custom-org/custom-tracks"
        return mock_repo_dir

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks(
            repo_url="https://github.com/custom-org/custom-tracks"
        )
        assert len(tracks) == 3


def test_load_public_tracks_custom_branch(mock_repo_dir, tmp_path):
    """Test loading from a specific branch."""

    def mock_update_repo(repo_url, ref, cache_dir):
        assert ref == "develop"
        return mock_repo_dir

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks(ref="develop")
        assert len(tracks) == 3


def test_load_public_tracks_excludes_reference_markdown_in_agenttracks_folders(
    mock_repo_with_agenttracks_references, tmp_path
):
    """Test that markdown files in TRACK.md subdirs are NOT loaded as tracks.

    This is a regression test for issue #1981:
    https://github.com/takebox/software-agent-sdk/issues/1981

    When a track directory contains a TRACK.md file (AgentTracks format), any
    markdown files in subdirectories (like themes/, references/, etc.) should
    be treated as reference materials for that track, NOT as separate tracks.

    Expected behavior:
    - theme-factory/TRACK.md -> loaded as "theme-factory" track
    - theme-factory/themes/*.md -> NOT loaded (reference files)
    - readiness-report/TRACK.md -> loaded as "readiness-report" track
    - readiness-report/references/*.md -> NOT loaded (reference files)
    - legacy-track.md -> loaded as "legacy-track" track
    """

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_with_agenttracks_references

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks()

        # Get all track names
        track_names = {s.name for s in tracks}

        # Should have exactly 3 tracks: theme-factory, readiness-report, legacy-track
        assert len(tracks) == 3, (
            f"Expected 3 tracks but got {len(tracks)}. "
            f"Track names: {track_names}. "
            "Reference markdown files in themes/ or references/ subdirectories "
            "should NOT be loaded as separate tracks."
        )

        # Verify the correct tracks are loaded
        assert "theme-factory" in track_names
        assert "readiness-report" in track_names
        assert "legacy-track" in track_names

        # Verify reference files are NOT loaded as tracks
        # These would be loaded with names like "theme-factory/themes/arctic-frost"
        for track in tracks:
            assert "arctic-frost" not in track.name, (
                f"Reference arctic-frost.md loaded as track: {track.name}"
            )
            assert "ocean-depths" not in track.name, (
                f"Reference ocean-depths.md loaded as track: {track.name}"
            )
            assert "sunset-boulevard" not in track.name, (
                f"Reference sunset-boulevard.md loaded as track: {track.name}"
            )
            assert "criteria" not in track.name, (
                f"Reference criteria.md loaded as track: {track.name}"
            )
            assert "maturity-levels" not in track.name, (
                f"Reference maturity-levels.md loaded as track: {track.name}"
            )


# Tests for marketplace-based track filtering


@pytest.fixture
def mock_repo_with_marketplace(tmp_path):
    """Create a mock git repository with marketplace file and tracks."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()

    # Create tracks directory
    tracks_dir = repo_dir / "tracks"
    tracks_dir.mkdir()

    # Create marketplaces directory
    marketplaces_dir = repo_dir / "marketplaces"
    marketplaces_dir.mkdir()

    # Create multiple tracks (some in marketplace, some not)
    # Track 1: git (in marketplace)
    git_dir = tracks_dir / "git"
    git_dir.mkdir()
    (git_dir / "TRACK.md").write_text(
        "---\nname: git\ndescription: Git best practices\n---\nGit track content."
    )

    # Track 2: docker (in marketplace)
    docker_dir = tracks_dir / "docker"
    docker_dir.mkdir()
    (docker_dir / "TRACK.md").write_text(
        "---\nname: docker\ndescription: Docker guidelines\n---\nDocker track content."
    )

    # Track 3: internal-only (NOT in marketplace)
    internal_dir = tracks_dir / "internal-only"
    internal_dir.mkdir()
    (internal_dir / "TRACK.md").write_text(
        "---\nname: internal-only\ndescription: Internal track\n---\nInternal content."
    )

    # Track 4: experimental (NOT in marketplace)
    experimental_dir = tracks_dir / "experimental"
    experimental_dir.mkdir()
    (experimental_dir / "TRACK.md").write_text(
        "---\nname: experimental\ndescription: Experimental\n---\nExperimental content."
    )

    # Create default marketplace with only git and docker
    marketplace = {
        "name": "default",
        "owner": {"name": "Handprint", "email": "test@test.com"},
        "metadata": {"description": "Test marketplace", "version": "1.0.0"},
        "plugins": [
            {"name": "git", "source": "./git", "description": "Git track"},
            {"name": "docker", "source": "./docker", "description": "Docker track"},
        ],
    }
    (marketplaces_dir / "default.json").write_text(json.dumps(marketplace))

    custom_marketplace = {
        "name": "custom",
        "owner": {"name": "Handprint", "email": "test@test.com"},
        "metadata": {"description": "Custom test marketplace", "version": "1.0.0"},
        "plugins": [
            {"name": "git", "source": "./git", "description": "Git track"},
            {
                "name": "internal-only",
                "source": "./internal-only",
                "description": "Internal track",
            },
        ],
    }
    (marketplaces_dir / "custom.json").write_text(json.dumps(custom_marketplace))

    # Create .git directory to simulate a git repo
    (repo_dir / ".git").mkdir()

    return repo_dir


def test_load_marketplace_track_names_returns_track_names(mock_repo_with_marketplace):
    """Test that load_marketplace_track_names correctly extracts track names."""
    track_names = load_marketplace_track_names(
        mock_repo_with_marketplace, "marketplaces/default.json"
    )

    assert track_names is not None
    assert track_names == {"git", "docker"}


def test_load_marketplace_track_names_returns_none_when_file_missing(tmp_path):
    """Test that load_marketplace_track_names returns None when file doesn't exist."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    result = load_marketplace_track_names(repo_dir, "marketplaces/default.json")
    assert result is None


def test_load_marketplace_track_names_returns_none_for_invalid_json(tmp_path):
    """Test that load_marketplace_track_names handles invalid JSON gracefully."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    marketplaces_dir = repo_dir / "marketplaces"
    marketplaces_dir.mkdir()
    (marketplaces_dir / "default.json").write_text("{ invalid json }")

    result = load_marketplace_track_names(repo_dir, "marketplaces/default.json")
    assert result is None


def test_load_marketplace_track_names_returns_none_for_missing_plugins(tmp_path):
    """Test that load_marketplace_track_names handles missing plugins key."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    marketplaces_dir = repo_dir / "marketplaces"
    marketplaces_dir.mkdir()
    (marketplaces_dir / "default.json").write_text(json.dumps({"name": "test"}))

    result = load_marketplace_track_names(repo_dir, "marketplaces/default.json")
    assert result is None


def test_load_public_tracks_filters_by_marketplace(
    mock_repo_with_marketplace, tmp_path
):
    """Test that load_public_tracks only loads tracks listed in the marketplace."""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_with_marketplace

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks()

    track_names = {track.name for track in tracks}
    assert track_names == {"git", "docker"}
    assert "internal-only" not in track_names
    assert "experimental" not in track_names


def test_load_public_tracks_uses_custom_marketplace_path(
    mock_repo_with_marketplace, tmp_path
):
    """Test that a custom marketplace_path selects a different track set."""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_with_marketplace

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks(marketplace_path="marketplaces/custom.json")

    assert {track.name for track in tracks} == {"git", "internal-only"}


def test_load_public_tracks_returns_empty_for_invalid_custom_marketplace_path(
    mock_repo_with_marketplace, tmp_path
):
    """Test that an invalid custom marketplace_path does not broaden track loading."""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_with_marketplace

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks(marketplace_path="marketplaces/missing.json")

    assert tracks == []


def test_load_public_tracks_loads_all_when_no_marketplace(tmp_path):
    """Test that load_public_tracks loads all tracks when no marketplace exists."""
    # Create repo without marketplace
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    tracks_dir = repo_dir / "tracks"
    tracks_dir.mkdir()

    # Create tracks
    for name in ["git", "docker", "internal-only"]:
        track_dir = tracks_dir / name
        track_dir.mkdir()
        (track_dir / "TRACK.md").write_text(
            f"---\nname: {name}\ndescription: {name}\n---\n{name} content."
        )

    (repo_dir / ".git").mkdir()

    def mock_update_repo(repo_url, branch, cache_dir):
        return repo_dir

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks()

        # Should have all tracks since no marketplace exists
        track_names = {s.name for s in tracks}
        assert track_names == {"git", "docker", "internal-only"}


def test_load_public_tracks_handles_legacy_md_files_with_marketplace(tmp_path):
    """Test marketplace filtering works with legacy .md track files."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    tracks_dir = repo_dir / "tracks"
    tracks_dir.mkdir()

    # Create legacy .md tracks
    (tracks_dir / "git.md").write_text(
        "---\nname: git\ntriggers:\n  - git\n---\nGit track."
    )
    (tracks_dir / "docker.md").write_text(
        "---\nname: docker\ntriggers:\n  - docker\n---\nDocker track."
    )
    (tracks_dir / "internal.md").write_text(
        "---\nname: internal\ntriggers:\n  - internal\n---\nInternal track."
    )

    # Create marketplace that includes git and docker but not internal
    marketplaces_dir = repo_dir / "marketplaces"
    marketplaces_dir.mkdir()
    marketplace = {
        "name": "default",
        "owner": {"name": "Test Team"},
        "plugins": [
            {"name": "git", "source": "./git.md"},
            {"name": "docker", "source": "./docker.md"},
        ],
    }
    (marketplaces_dir / "default.json").write_text(json.dumps(marketplace))

    (repo_dir / ".git").mkdir()

    def mock_update_repo(repo_url, branch, cache_dir):
        return repo_dir

    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        tracks = load_public_tracks()

        # Should only have git and docker from marketplace
        track_names = {s.name for s in tracks}
        assert track_names == {"git", "docker"}
        assert "internal" not in track_names


def test_load_public_tracks_caches_result_within_ttl(mock_repo_dir, tmp_path):
    """Second call within the TTL window must not re-run update_tracks_repository.

    Regression test for the slow conversation-creation path: AgentContext was
    being (re-)validated several times per request, causing load_public_tracks
    to do a git fetch + parse every time.
    """
    update_mock = MagicMock(return_value=mock_repo_dir)
    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            update_mock,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        first = load_public_tracks()
        second = load_public_tracks()

    assert update_mock.call_count == 1
    assert {s.name for s in first} == {s.name for s in second}


def test_invalidate_public_tracks_cache_forces_recompute(mock_repo_dir, tmp_path):
    """After explicit invalidation, the next call re-runs update_tracks_repository."""
    update_mock = MagicMock(return_value=mock_repo_dir)
    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            update_mock,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        load_public_tracks()
        _invalidate_public_tracks_cache()
        load_public_tracks()

    assert update_mock.call_count == 2


def test_load_public_tracks_does_not_cache_empty_results(mock_repo_dir, tmp_path):
    """Transient failures must not poison the cache for the full TTL.

    First call simulates a git/repo failure (no tracks returned); second call
    succeeds and should hit the real path again instead of the empty cache.
    """
    update_mock = MagicMock(side_effect=[None, mock_repo_dir])
    with (
        patch(
            "handprint.sdk.tracks.track.update_tracks_repository",
            update_mock,
        ),
        patch(
            "handprint.sdk.tracks.track.get_tracks_cache_dir",
            return_value=tmp_path,
        ),
    ):
        first = load_public_tracks()
        second = load_public_tracks()

    assert first == []
    assert {s.name for s in second} == {"git", "docker", "testing"}
    assert update_mock.call_count == 2
