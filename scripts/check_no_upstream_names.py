#!/usr/bin/env python3
"""Fail if the upstream project name comes back into this repository.

Vinbox installs this fork's wheels only. A stray `ghcr.io/openhands/...` image
reference is not cosmetic: it tells a future reader (or a future sandbox lane)
to pull an image and a package set that this fork does not control, which is
exactly the failure this repo was forked to avoid.

The two install checkers keep the literal word on purpose — they exist to fail
when it appears — so they are allowlisted here.

Run: python scripts/check_no_openhands.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN = "openhands"

ALLOWLIST = {
    # Checkers: their whole job is to detect this name.
    "scripts/check_no_upstream_names.py",
    "scripts/check_vinbox_wheels.py",
    "scripts/check_vinbox_install.sh",
}


def tracked_text_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [ROOT / p.decode() for p in out.split(b"\0") if p]


def main() -> int:
    offenders: list[str] = []

    for path in tracked_text_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWLIST:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: not a source reference

        for number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN in line.lower():
                offenders.append(f"{rel}:{number}: {line.strip()[:120]}")

    if offenders:
        print(f"ERROR: {FORBIDDEN} masih muncul di {len(offenders)} tempat:")
        for line in offenders:
            print("  " + line)
        print(
            "\nGanti ke namespace Vinbox (ghcr.io/handprint/agent-server) atau "
            "hapus referensinya. Jangan menambah pengecualian selain checker."
        )
        return 1

    print(f"OK: tidak ada '{FORBIDDEN}' di file yang di-track")
    return 0


if __name__ == "__main__":
    sys.exit(main())
