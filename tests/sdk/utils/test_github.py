"""Tests for GitHub utility functions."""

from handprint.sdk.utils.github import ZWJ, sanitize_handprint_mentions


def test_sanitize_basic_mention():
    """Test basic @Handprint mention is sanitized."""
    text = "Thanks @Handprint for the help!"
    expected = f"Thanks @{ZWJ}Handprint for the help!"
    assert sanitize_handprint_mentions(text) == expected


def test_sanitize_case_insensitive():
    """Test that mentions are sanitized regardless of case."""
    test_cases = [
        ("Check @Handprint here", f"Check @{ZWJ}Handprint here"),
        ("Check @handprint here", f"Check @{ZWJ}handprint here"),
        ("Check @HANDPRINT here", f"Check @{ZWJ}HANDPRINT here"),
        ("Check @hAnDpRiNt here", f"Check @{ZWJ}hAnDpRiNt here"),
    ]
    for input_text, expected in test_cases:
        assert sanitize_handprint_mentions(input_text) == expected


def test_sanitize_multiple_mentions():
    """Test multiple mentions in the same text."""
    text = "Both @Handprint and @handprint should be sanitized"
    expected = f"Both @{ZWJ}Handprint and @{ZWJ}handprint should be sanitized"
    assert sanitize_handprint_mentions(text) == expected


def test_sanitize_with_punctuation():
    """Test mentions followed by punctuation."""
    test_cases = [
        ("Thanks @Handprint!", f"Thanks @{ZWJ}Handprint!"),
        ("Hello @Handprint.", f"Hello @{ZWJ}Handprint."),
        ("See @Handprint,", f"See @{ZWJ}Handprint,"),
        ("By @Handprint:", f"By @{ZWJ}Handprint:"),
        ("From @Handprint;", f"From @{ZWJ}Handprint;"),
        ("Hi @Handprint?", f"Hi @{ZWJ}Handprint?"),
        ("Use @Handprint)", f"Use @{ZWJ}Handprint)"),
        ("Try (@Handprint)", f"Try (@{ZWJ}Handprint)"),
    ]
    for input_text, expected in test_cases:
        assert sanitize_handprint_mentions(input_text) == expected


def test_no_sanitize_partial_words():
    """Test that partial word matches are NOT sanitized."""
    test_cases = [
        "HandprintTeam",
        "MyHandprint",
        "HandprintBot",
        "#Handprint",
    ]
    for text in test_cases:
        # Partial words without @ should remain unchanged
        assert sanitize_handprint_mentions(text) == text


def test_no_op_cases():
    """Test cases where no sanitization should occur."""
    test_cases = [
        "",
        "No mentions here",
        "Just some text",
        "@GitHub",
        "@Other",
        "Handprint without @",
    ]
    for text in test_cases:
        assert sanitize_handprint_mentions(text) == text


def test_sanitize_at_line_boundaries():
    """Test mentions at the start and end of lines."""
    test_cases = [
        ("@Handprint at start", f"@{ZWJ}Handprint at start"),
        ("at end @Handprint", f"at end @{ZWJ}Handprint"),
        ("@Handprint", f"@{ZWJ}Handprint"),
    ]
    for input_text, expected in test_cases:
        assert sanitize_handprint_mentions(input_text) == expected


def test_sanitize_multiline_text():
    """Test sanitization in multiline text."""
    text = """Hello @Handprint!

This is a test with @handprint mentioned.

Thanks @HANDPRINT for everything!"""

    expected = f"""Hello @{ZWJ}Handprint!

This is a test with @{ZWJ}handprint mentioned.

Thanks @{ZWJ}HANDPRINT for everything!"""

    assert sanitize_handprint_mentions(text) == expected


def test_sanitize_with_urls():
    """Test that URLs containing Handprint are handled correctly."""
    test_cases = [
        # URL should not be sanitized
        ("Visit https://github.com/HandPrint-AI", "Visit https://github.com/HandPrint-AI"),
        # But mention should be sanitized
        (
            "See @Handprint at https://github.com/HandPrint-AI",
            f"See @{ZWJ}Handprint at https://github.com/HandPrint-AI",
        ),
    ]
    for input_text, expected in test_cases:
        assert sanitize_handprint_mentions(input_text) == expected


def test_sanitize_preserves_whitespace():
    """Test that whitespace is preserved correctly."""
    text = "  @Handprint  \n  @handprint  "
    expected = f"  @{ZWJ}Handprint  \n  @{ZWJ}handprint  "
    assert sanitize_handprint_mentions(text) == expected


def test_zwj_constant():
    """Test that ZWJ constant is correctly defined."""
    assert ZWJ == "\u200d"
    assert len(ZWJ) == 1
    assert ord(ZWJ) == 0x200D
