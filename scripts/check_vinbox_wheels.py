#!/usr/bin/env python3
"""Periksa wheel Vinbox sebelum diunggah.

Dipakai sebelum ``twine upload``:

    python scripts/check_vinbox_wheels.py dist-vinbox

Yang diperiksa:

1. kelima distribusi ada, dengan versi yang sama;
2. nama distribusi memang nama Vinbox (bukan nama proyek umum);
3. tidak ada entri yang memakai nama lama;
4. tidak ada tes, cache, atau ``__pycache__`` yang ikut ke wheel;
5. paket meta mengunci keempat paket Vinbox pada versi yang sama;
6. kontrak ``handprint/sdk/vinbox.py`` ikut di wheel SDK.

Keluar dengan kode 1 kalau ada satu saja yang gagal, supaya CI berhenti
sebelum ada paket salah yang terbit.
"""

from __future__ import annotations

import email.parser
import pathlib
import sys
import zipfile


EXPECTED = {
    "handprint-vinbox-sdk": "handprint/sdk/vinbox.py",
    "handprint-vinbox-tools": "handprint/tools/__init__.py",
    "handprint-vinbox-workspace": "handprint/workspace/__init__.py",
    "handprint-vinbox-agent-server": "handprint/agent_server/__main__.py",
    "software-agent-sdk-vinbox": None,
}

META = "software-agent-sdk-vinbox"
META_REQUIRES = {
    "handprint-vinbox-sdk",
    "handprint-vinbox-tools",
    "handprint-vinbox-workspace",
    "handprint-vinbox-agent-server",
}

FORBIDDEN_ENTRY_PARTS = ("tests/", "__pycache__/", ".pytest_cache/")
FORBIDDEN_TEXT = ("openhands",)


def read_metadata(archive: zipfile.ZipFile) -> email.message.Message:
    for name in archive.namelist():
        if name.endswith(".dist-info/METADATA"):
            raw = archive.read(name).decode("utf-8", "replace")
            return email.parser.Parser().parsestr(raw)
    raise SystemExit("METADATA tidak ditemukan di dalam wheel")


def main(argv: list[str]) -> int:
    target = pathlib.Path(argv[1] if len(argv) > 1 else "dist-vinbox")
    wheels = sorted(target.glob("*.whl"))
    problems: list[str] = []

    if not wheels:
        print(f"TIDAK ADA wheel di {target}")
        return 1

    found: dict[str, tuple[pathlib.Path, email.message.Message]] = {}
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            meta = read_metadata(archive)
            name = meta["Name"]
            version = meta["Version"]
            entries = archive.namelist()

        if name in found:
            problems.append(f"{name}: muncul lebih dari sekali ({wheel.name})")
        found[name] = (wheel, meta)

        for entry in entries:
            if any(part in entry for part in FORBIDDEN_ENTRY_PARTS):
                problems.append(f"{wheel.name}: memuat entri terlarang {entry}")
        for entry in entries:
            lowered = entry.lower()
            for word in FORBIDDEN_TEXT:
                if word in lowered:
                    problems.append(f"{wheel.name}: entri memakai nama lama: {entry}")

        required = EXPECTED.get(name)
        if required is not None and required not in entries:
            problems.append(f"{wheel.name}: wajib memuat {required}")

        print(f"OK  {name} {version}  ({len(entries)} entri)  {wheel.name}")

    missing = set(EXPECTED) - set(found)
    for name in sorted(missing):
        problems.append(f"{name}: wheel tidak ada di {target}")

    versions = {meta["Version"] for _, meta in found.values()}
    if len(versions) > 1:
        problems.append(f"versi tidak seragam: {sorted(versions)}")

    if META in found:
        meta = found[META][1]
        requires = {
            req.split(";")[0].split("==")[0].strip().lower()
            for req in (meta.get_all("Requires-Dist") or [])
        }
        pinned = {
            req.split(";")[0].split("==")[0].strip().lower()
            for req in (meta.get_all("Requires-Dist") or [])
            if "==" in req
        }
        if requires != META_REQUIRES:
            problems.append(
                f"{META}: dependensi harus tepat {sorted(META_REQUIRES)}, "
                f"ditemukan {sorted(requires)}"
            )
        if pinned != META_REQUIRES:
            problems.append(f"{META}: semua dependensi harus dikunci dengan '=='")

    if problems:
        print("\nGAGAL:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nSemua wheel valid: 5 distribusi, versi seragam, tanpa nama lama.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
