"""Tests for plugin source path handling."""

from pathlib import Path

import pytest

from handprint.sdk.plugin.source import (
    is_local_path,
    parse_github_url,
    resolve_source_path,
    validate_source_path,
)


class TestParseGitHubURL:
    def test_parse_blob_url(self):
        result = parse_github_url(
            "https://github.com/HandPrint-AI/extensions/blob/main/tracks/github"
        )
        assert result is not None
        assert result.owner == "Handprint"
        assert result.repo == "extensions"
        assert result.branch == "main"
        assert result.path == "tracks/github"

    def test_parse_tree_url(self):
        result = parse_github_url(
            "https://github.com/HandPrint-AI/extensions/tree/main/tracks/github"
        )
        assert result is not None
        assert result.path == "tracks/github"

    def test_returns_none_for_non_github(self):
        assert parse_github_url("./tracks/my-track") is None
        assert parse_github_url("https://gitlab.com/o/r/blob/main/p") is None


class TestIsLocalPath:
    def test_local_paths(self):
        assert is_local_path("./tracks/my-track")
        assert is_local_path("../parent/track")
        assert is_local_path("/absolute/path")
        assert is_local_path("~/home/path")
        assert is_local_path("file:///path/to/file")

    def test_non_local_paths(self):
        assert not is_local_path("https://github.com/o/r/blob/main/p")
        assert not is_local_path("just-a-name")


class TestValidateSourcePath:
    def test_valid_paths(self):
        assert validate_source_path("./tracks/my-track") == "./tracks/my-track"
        assert validate_source_path("/absolute/path") == "/absolute/path"
        url = "https://github.com/owner/repo/blob/main/path"
        assert validate_source_path(url) == url

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="Invalid source path"):
            validate_source_path("just-a-name")


class TestResolveSourcePath:
    def test_resolve_file_url(self):
        assert resolve_source_path("file:///tmp/track") == Path("/tmp/track")

    def test_resolve_absolute_path(self):
        assert resolve_source_path("/absolute/path") == Path("/absolute/path")

    def test_resolve_relative_with_base(self):
        result = resolve_source_path("./track", base_path=Path("/project"))
        assert result == (Path("/project") / "track").resolve()

    def test_resolve_home_path(self):
        result = resolve_source_path("~/documents/track")
        assert result == Path.home() / "documents" / "track"
