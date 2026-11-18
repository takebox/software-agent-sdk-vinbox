"""Startup banner for Handprint SDK.

Prints a welcome message with helpful links when the SDK is first imported.
Can be suppressed by setting the HANDPRINT_SUPPRESS_BANNER environment variable.
"""

import os
import sys


# Not guarded by a lock; worst case in a race is the banner prints twice.
_BANNER_PRINTED = False


def _print_banner(version: str) -> None:
    """Print the Handprint SDK startup banner to stderr."""
    global _BANNER_PRINTED

    # Check if banner should be suppressed (check this first, before setting flag)
    suppress = os.environ.get("HANDPRINT_SUPPRESS_BANNER", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if suppress:
        return

    if _BANNER_PRINTED:
        return
    _BANNER_PRINTED = True

    body = [
        f"Handprint SDK v{version}",
        "",
        "Report a bug: github.com/takebox/software-agent-sdk-vinbox/issues",
        "Get help: handprint.dev/joinslack",
        "Scale up: handprint.dev/product/sdk",
        "",
        "Set HANDPRINT_SUPPRESS_BANNER=1 to hide this message",
    ]
    # Width follows the longest line so a longer repository URL can never
    # break the box.
    content_width = max(len(line) for line in body)
    border = "+" + "-" * (content_width + 4) + "+"
    lines = [border, *(f"|  {line:<{content_width}}  |" for line in body), border]
    print("\n".join(lines), file=sys.stderr)
