"""Tests for AgentTracks standard fields in the Track model."""

import pytest
from pydantic import ValidationError

from handprint.sdk.tracks import Track, TrackValidationError


def test_track_with_agenttracks_fields(tmp_path) -> None:
    """Track should support AgentTracks standard fields."""
    track_content = """---
name: pdf-processing
description: Extract text from PDF files.
license: Apache-2.0
compatibility: Requires poppler-utils
metadata:
  author: example-org
  version: "1.0"
allowed-tools: Bash(pdftotext:*) Read Write
disable-model-invocation: true
triggers:
  - pdf
---
# PDF Processing
"""
    path = tmp_path / "pdf.md"
    path.write_text(track_content)
    track = Track.load(path)

    assert track.name == "pdf-processing"
    assert track.description == "Extract text from PDF files."
    assert track.license == "Apache-2.0"
    assert track.compatibility == "Requires poppler-utils"
    assert track.metadata == {"author": "example-org", "version": "1.0"}
    assert track.allowed_tools == ["Bash(pdftotext:*)", "Read", "Write"]
    assert track.disable_model_invocation is True
    assert track.match_trigger("process pdf") == "pdf"


def test_track_allowed_tools_formats(tmp_path) -> None:
    """allowed-tools should accept string or list format."""
    # String format
    path = tmp_path / "s1.md"
    path.write_text("---\nname: s\nallowed-tools: A B\n---\n#")
    track = Track.load(path)
    assert track.allowed_tools == ["A", "B"]

    # List format
    path = tmp_path / "s2.md"
    path.write_text("---\nname: s\nallowed-tools:\n  - A\n  - B\n---\n#")
    track = Track.load(path)
    assert track.allowed_tools == ["A", "B"]

    # Underscore variant
    path = tmp_path / "s3.md"
    path.write_text("---\nname: s\nallowed_tools: A B\n---\n#")
    track = Track.load(path)
    assert track.allowed_tools == ["A", "B"]


def test_track_invalid_field_types(tmp_path) -> None:
    """Track should reject invalid field types via Pydantic validation."""
    # Invalid description - Pydantic validates string type
    path = tmp_path / "invalid_desc.md"
    path.write_text("---\nname: s\ndescription:\n  - list\n---\n#")
    with pytest.raises(ValidationError, match="description"):
        Track.load(path)

    # Invalid metadata - custom validator raises TrackValidationError
    path = tmp_path / "invalid_meta.md"
    path.write_text("---\nname: s\nmetadata: string\n---\n#")
    with pytest.raises(TrackValidationError, match="metadata must be a dictionary"):
        Track.load(path)

    # Invalid allowed-tools - custom validator raises TrackValidationError
    path = tmp_path / "invalid_tools.md"
    path.write_text("---\nname: s\nallowed-tools: 123\n---\n#")
    with pytest.raises(TrackValidationError, match="allowed-tools must be"):
        Track.load(path)


def test_track_backward_compatibility(tmp_path) -> None:
    """Tracks without AgentTracks fields should still work."""
    path = tmp_path / "s.md"
    path.write_text("---\nname: legacy\ntriggers:\n  - test\n---\n#")
    track = Track.load(path)
    assert track.name == "legacy"
    assert track.description is None
    assert track.license is None
    assert track.disable_model_invocation is False
    assert track.match_trigger("test") == "test"
