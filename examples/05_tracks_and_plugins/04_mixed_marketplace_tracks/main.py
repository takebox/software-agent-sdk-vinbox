"""Example: Mixed Marketplace with Local and Remote Tracks

This example demonstrates how to create a marketplace that includes both:
1. Local tracks hosted in your project directory
2. Remote tracks from GitHub (Handprint/extensions repository)

The marketplace.json schema supports source paths in these formats:
- Local paths: ./path, ../path, /absolute/path, ~/path, file:///path
- GitHub URLs: https://github.com/{owner}/{repo}/blob/{branch}/{path}

This pattern is useful for teams that want to:
- Maintain their own custom tracks locally
- Reference specific tracks from remote repositories
- Create a curated track set for their specific workflows

Directory Structure:
    04_mixed_marketplace_tracks/
    ├── .plugin/
    │   └── marketplace.json     # Marketplace with local and remote tracks
    ├── tracks/
    │   └── greeting-helper/
    │       └── TRACK.md         # Local track content
    ├── main.py                  # This file
    └── README.md                # Documentation

Usage:
    # Install all tracks from marketplace to ~/.handprint/tracks/installed/
    python main.py --install

    # Force reinstall (overwrite existing)
    python main.py --install --force

    # Show installed tracks
    python main.py --list
"""

import sys
from pathlib import Path

from handprint.sdk.marketplace import Marketplace
from handprint.sdk.tracks import (
    install_tracks_from_marketplace,
    list_installed_tracks,
)


def main():
    script_dir = Path(__file__).parent

    if "--list" in sys.argv:
        # List installed tracks
        print("=" * 80)
        print("Installed Tracks")
        print("=" * 80)
        installed = list_installed_tracks()
        if not installed:
            print("\nNo tracks installed.")
            print("Run with --install to install tracks from the marketplace.")
        else:
            for info in installed:
                desc = (info.description or "No description")[:60]
                print(f"\n  {info.name}")
                print(f"    Description: {desc}...")
                print(f"    Source: {info.source}")
        return

    if "--install" in sys.argv:
        # Install tracks from marketplace
        print("=" * 80)
        print("Installing Tracks from Marketplace")
        print("=" * 80)
        print(f"\nMarketplace directory: {script_dir}")

        force = "--force" in sys.argv
        installed = install_tracks_from_marketplace(script_dir, force=force)

        print(f"\n\nInstalled {len(installed)} tracks:")
        for info in installed:
            print(f"  - {info.name}")

        # Show all installed tracks
        print("\n" + "=" * 80)
        print("All Installed Tracks")
        print("=" * 80)
        all_installed = list_installed_tracks()
        for info in all_installed:
            desc = (info.description or "No description")[:50]
            print(f"  - {info.name}: {desc}...")
        return

    # Default: show marketplace info
    print("=" * 80)
    print("Marketplace Information")
    print("=" * 80)
    print(f"\nMarketplace directory: {script_dir}")

    marketplace = Marketplace.load(script_dir)
    print(f"Name: {marketplace.name}")
    print(f"Description: {marketplace.description}")
    print(f"Tracks defined: {len(marketplace.tracks)}")

    print("\nTracks:")
    for entry in marketplace.tracks:
        source_type = "remote" if entry.source.startswith("http") else "local"
        print(f"  - {entry.name} ({source_type})")
        print(f"    Source: {entry.source}")
        if entry.description:
            print(f"    Description: {entry.description}")

    print("\n" + "-" * 80)
    print("Usage:")
    print("  python main.py --install        # Install all tracks")
    print("  python main.py --install --force # Force reinstall")
    print("  python main.py --list           # List installed tracks")


if __name__ == "__main__":
    main()
    print("EXAMPLE_COST: 0")
