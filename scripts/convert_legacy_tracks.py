#!/usr/bin/env python3
"""Convert legacy Handprint tracks to AgentTracks standard format.

This script converts single .md track files to the AgentTracks directory format:
- Creates track-name/ directory with TRACK.md
- Converts mcp_tools frontmatter to .mcp.json files
- Preserves Handprint-specific fields (triggers, inputs) for compatibility

Usage:
    # Convert a single track file
    python convert_legacy_tracks.py track.md --output-dir ./converted/

    # Convert all tracks in a directory
    python convert_legacy_tracks.py ./tracks/ --output-dir ./converted/

    # Dry run (show what would be converted)
    python convert_legacy_tracks.py ./tracks/ --output-dir ./converted/ --dry-run
"""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import frontmatter


# AgentTracks name validation pattern
TRACK_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def normalize_track_name(name: str) -> str:
    """Normalize a track name to conform to AgentTracks spec.

    Converts to lowercase, replaces underscores with hyphens,
    and removes invalid characters.
    """
    normalized = name.lower()
    normalized = normalized.replace("_", "-")
    normalized = re.sub(r"[^a-z0-9-]", "", normalized)
    normalized = re.sub(r"-+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized


def validate_track_name(name: str) -> list[str]:
    """Validate track name according to AgentTracks spec."""
    errors = []
    if not name:
        errors.append("Name cannot be empty")
        return errors
    if len(name) > 64:
        errors.append(f"Name exceeds 64 characters: {len(name)}")
    if not TRACK_NAME_PATTERN.match(name):
        errors.append(
            "Name must be lowercase alphanumeric with single hyphens "
            "(e.g., 'my-track', 'pdf-tools')"
        )
    return errors


def generate_description(
    content: str,
    triggers: list[str] | None = None,
    name: str | None = None,
) -> str:
    """Generate a description for the track from content or triggers."""
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("<") and stripped.endswith(">"):
            continue
        return stripped[:1024]

    if triggers:
        trigger_str = ", ".join(triggers[:5])
        if len(triggers) > 5:
            trigger_str += f" (+{len(triggers) - 5} more)"
        return f"Activated by: {trigger_str}"[:1024]

    if name:
        return f"Track: {name}"[:1024]

    return "A track for Handprint agent."


def convert_legacy_track(
    source_path: Path,
    output_dir: Path,
    dry_run: bool = False,
) -> Path | None:
    """Convert a legacy Handprint track to AgentTracks format."""
    if not source_path.exists():
        print(f"Error: Source file not found: {source_path}", file=sys.stderr)
        return None

    if source_path.name == "README.md":
        return None

    with open(source_path) as f:
        file_content = f.read()

    file_io = io.StringIO(file_content)
    loaded = frontmatter.load(file_io)
    content = loaded.content
    metadata = dict(loaded.metadata) if loaded.metadata else {}

    original_name = metadata.get("name", source_path.stem)
    track_name = normalize_track_name(str(original_name))

    name_errors = validate_track_name(track_name)
    if name_errors:
        print(
            f"Warning: Track name '{original_name}' -> '{track_name}' "
            f"has issues: {'; '.join(name_errors)}",
            file=sys.stderr,
        )
        track_name = normalize_track_name(source_path.stem)
        if validate_track_name(track_name):
            print(
                f"Error: Cannot normalize track name for {source_path}",
                file=sys.stderr,
            )
            return None

    track_dir = output_dir / track_name
    track_md_path = track_dir / "TRACK.md"
    mcp_json_path = track_dir / ".mcp.json"

    print(f"Converting: {source_path} -> {track_dir}/")

    if dry_run:
        return track_dir

    track_dir.mkdir(parents=True, exist_ok=True)

    new_metadata: dict[str, Any] = {}
    new_metadata["name"] = track_name

    triggers_raw = metadata.get("triggers", [])
    triggers: list[str] = triggers_raw if isinstance(triggers_raw, list) else []
    description = metadata.get("description") or generate_description(
        content, triggers, track_name
    )
    new_metadata["description"] = description

    if "license" in metadata:
        new_metadata["license"] = metadata["license"]
    if "compatibility" in metadata:
        new_metadata["compatibility"] = metadata["compatibility"]

    extra_metadata: dict[str, str] = {}
    if "version" in metadata:
        extra_metadata["version"] = str(metadata["version"])
    if "author" in metadata:
        extra_metadata["author"] = str(metadata["author"])
    if "agent" in metadata:
        extra_metadata["agent"] = str(metadata["agent"])
    if "type" in metadata:
        extra_metadata["type"] = str(metadata["type"])

    if "metadata" in metadata and isinstance(metadata["metadata"], dict):
        for k, v in metadata["metadata"].items():
            extra_metadata[str(k)] = str(v)

    if extra_metadata:
        new_metadata["metadata"] = extra_metadata

    if triggers:
        new_metadata["triggers"] = triggers
    if "inputs" in metadata:
        new_metadata["inputs"] = metadata["inputs"]
    if "allowed-tools" in metadata:
        new_metadata["allowed-tools"] = metadata["allowed-tools"]
    if "allowed_tools" in metadata:
        new_metadata["allowed-tools"] = metadata["allowed_tools"]

    mcp_tools = metadata.get("mcp_tools")

    new_post = frontmatter.Post(content, **new_metadata)
    with open(track_md_path, "w") as f:
        f.write(frontmatter.dumps(new_post))

    if mcp_tools and isinstance(mcp_tools, dict):
        with open(mcp_json_path, "w") as f:
            json.dump(mcp_tools, f, indent=2)
            f.write("\n")

    return track_dir


def convert_tracks_directory(
    source_dir: Path,
    output_dir: Path,
    dry_run: bool = False,
) -> list[Path]:
    """Convert all legacy tracks in a directory to AgentTracks format."""
    if not source_dir.exists():
        print(f"Error: Source directory not found: {source_dir}", file=sys.stderr)
        return []

    converted: list[Path] = []

    md_files = [
        f
        for f in source_dir.glob("*.md")
        if f.name != "README.md" and f.name.lower() != "track.md"
    ]

    print(f"Found {len(md_files)} track files to convert")

    for md_file in sorted(md_files):
        result = convert_legacy_track(md_file, output_dir, dry_run=dry_run)
        if result:
            converted.append(result)

    print(f"Converted {len(converted)} tracks")
    return converted


def main():
    parser = argparse.ArgumentParser(
        description="Convert legacy Handprint tracks to AgentTracks standard format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Source track file (.md) or directory containing track files",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        required=True,
        help="Output directory for converted tracks",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be converted without writing files",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove output directory before converting",
    )

    args = parser.parse_args()

    if args.clean and args.output_dir.exists() and not args.dry_run:
        print(f"Cleaning output directory: {args.output_dir}")
        shutil.rmtree(args.output_dir)

    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.source.is_file():
        result = convert_legacy_track(
            args.source, args.output_dir, dry_run=args.dry_run
        )
        if result:
            print(f"\nSuccess: Created {result}")
        else:
            sys.exit(1)
    elif args.source.is_dir():
        results = convert_tracks_directory(
            args.source, args.output_dir, dry_run=args.dry_run
        )
        if not results:
            print("No tracks were converted", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Error: Source not found: {args.source}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
