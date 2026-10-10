"""Tests for track validation improvements."""

from handprint.sdk.tracks import Track
from handprint.sdk.utils import DEFAULT_TRUNCATE_NOTICE


MAX_DESCRIPTION_LENGTH = 1024


def test_description_at_limit() -> None:
    """Track should accept description at 1024 chars."""
    desc = "x" * MAX_DESCRIPTION_LENGTH
    track = Track(name="test", content="# Test", description=desc)
    assert track.description is not None
    assert len(track.description) == MAX_DESCRIPTION_LENGTH


def test_description_exceeds_limit_is_truncated() -> None:
    """Track should truncate description over 1024 chars instead of erroring."""
    desc = "x" * (MAX_DESCRIPTION_LENGTH + 100)
    track = Track(name="test", content="# Test", description=desc)
    assert track.description is not None
    assert len(track.description) == MAX_DESCRIPTION_LENGTH
    # Without source, falls back to the default truncation notice
    assert DEFAULT_TRUNCATE_NOTICE in track.description


def test_description_truncation_includes_source_path() -> None:
    """When source is set, truncation notice should reference the track path."""
    desc = "x" * (MAX_DESCRIPTION_LENGTH + 500)
    source = "/path/to/my-track/TRACK.md"
    track = Track(name="test", content="# Test", description=desc, source=source)
    assert track.description is not None
    assert len(track.description) == MAX_DESCRIPTION_LENGTH
    assert source in track.description
