"""Utility functions for GitHub integrations."""

import re


# Zero-width joiner character (U+200D)
# We use ZWJ instead of ZWSP (U+200B) because:
# - ZWJ is semantically more appropriate (joins characters without adding space)
# - ZWJ has better support in modern renderers
# - ZWJ is invisible and doesn't affect text rendering or selection
ZWJ = "\u200d"


def sanitize_handprint_mentions(text: str) -> str:
    """Sanitize @Handprint mentions in text to prevent self-mention loops.

    This function inserts a zero-width joiner (ZWJ) after the @ symbol in
    @Handprint mentions, making them non-clickable in GitHub comments while
    preserving readability. The original case of the mention is preserved.

    Args:
        text: The text to sanitize

    Returns:
        Text with sanitized @Handprint mentions (e.g., "@Handprint" -> "@‍Handprint")

    Examples:
        >>> sanitize_handprint_mentions("Thanks @Handprint for the help!")
        'Thanks @\\u200dHandprint for the help!'
        >>> sanitize_handprint_mentions("Check @handprint and @HANDPRINT")
        'Check @\\u200dhandprint and @\\u200dHANDPRINT'
        >>> sanitize_handprint_mentions("No mention here")
        'No mention here'
    """
    # Pattern to match @Handprint mentions at word boundaries
    # Uses re.IGNORECASE so we don't need [Hh]andprint
    # Capture group preserves the original case
    pattern = r"@(Handprint)\b"

    # Replace @ with @ + ZWJ while preserving the original case
    # The \1 backreference preserves the matched case
    sanitized = re.sub(pattern, f"@{ZWJ}\\1", text, flags=re.IGNORECASE)

    return sanitized
