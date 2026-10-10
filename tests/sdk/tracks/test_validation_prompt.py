"""Tests for prompt generation utilities (Issue #1478)."""

from handprint.sdk.tracks import (
    Track,
    to_prompt,
)


def test_to_prompt_generates_xml() -> None:
    """to_prompt() should generate valid XML for tracks in AgentTracks format."""
    # Empty list shows "no available tracks"
    assert (
        to_prompt([])
        == "<available_tracks>\n  no available tracks\n</available_tracks>"
    )

    # Single track with description
    track = Track(name="pdf-tools", content="# PDF", description="Process PDFs.")
    result = to_prompt([track])
    assert "<track>" in result
    assert "<name>pdf-tools</name>" in result
    assert "<description>Process PDFs.</description>" in result
    assert "<available_tracks>" in result

    # Multiple tracks
    tracks = [
        Track(name="pdf-tools", content="# PDF", description="Process PDFs."),
        Track(name="code-review", content="# Code", description="Review code."),
    ]
    result = to_prompt(tracks)
    assert result.count("<track>") == 2


def test_to_prompt_never_emits_location() -> None:
    """to_prompt() must not emit <location>: invoke_track is the only entry
    point and the agent must not be given the file path."""
    track = Track(
        name="pdf-tools",
        content="# PDF",
        description="Process PDFs.",
        source="/path/to/track.md",
    )
    result = to_prompt([track])
    assert "<location>" not in result
    assert "/path/to/track.md" not in result


def test_to_prompt_escapes_xml() -> None:
    """to_prompt() should escape XML special characters."""
    track = Track(
        name="test", content="# Test", description='Handle <tags> & "quotes".'
    )
    result = to_prompt([track])
    assert "&lt;tags&gt;" in result
    assert "&amp;" in result
    # Quotes don't need escaping in XML element content (only in attributes)
    assert '"quotes"' in result


def test_to_prompt_uses_content_fallback() -> None:
    """to_prompt() should use content when no description."""
    track = Track(name="test", content="# Header\n\nActual content here.")
    result = to_prompt([track])
    assert "Actual content here." in result
    assert "# Header" not in result


def test_to_prompt_content_fallback_counts_remaining_as_truncated() -> None:
    """to_prompt() should count content after first line as truncated."""
    # Content with header, description line, and additional content
    content = "# Header\n\nFirst line used as description.\n\nMore content here."
    track = Track(name="test", content=content, source="/tracks/test.md")
    result = to_prompt([track])

    # Should use first non-header line as description
    assert "First line used as description." in result
    # Should indicate truncation for remaining content and point the agent at
    # invoke_track (not the file path) as the way to load the full content.
    assert "characters truncated" in result
    assert 'invoke_track(name="test")' in result
    assert "/tracks/test.md" not in result


def test_to_prompt_truncates_long_descriptions() -> None:
    """to_prompt() should truncate long descriptions with indicator."""
    track = Track(name="test", content="# Test", description="short")
    track.description = "A" * 1034
    result = to_prompt([track])

    # Should contain truncation indicator pointing at invoke_track
    assert "... [10 characters truncated" in result
    assert 'invoke_track(name="test")' in result
    # Should contain first 1024 chars
    assert "A" * 1024 in result


def test_to_prompt_truncation_points_at_invoke_track_not_source() -> None:
    """Truncation message must direct the agent to invoke_track, not the
    track's source path."""
    track = Track(
        name="test",
        content="# Test",
        description="short",
        source="/path/to/track.md",
    )
    track.description = "B" * 1034
    result = to_prompt([track])

    assert "... [10 characters truncated" in result
    assert 'invoke_track(name="test")' in result
    assert "/path/to/track.md" not in result
