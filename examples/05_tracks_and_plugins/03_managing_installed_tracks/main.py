"""Example: Installing and Managing Tracks

This example demonstrates installed track lifecycle operations in the SDK:

1. Install tracks from local paths into persistent storage
2. List tracked tracks and load only the enabled ones
3. Inspect the `.installed.json` metadata file and `enabled` flag
4. Disable and re-enable a track without reinstalling it
5. Uninstall a track while leaving other installed tracks available

For marketplace installation flows, see:
`examples/05_tracks_and_plugins/04_mixed_marketplace_tracks/`.
"""

import json
import tempfile
from pathlib import Path

from handprint.sdk.tracks import (
    disable_track,
    enable_track,
    install_track,
    list_installed_tracks,
    load_installed_tracks,
    uninstall_track,
)


script_dir = Path(__file__).resolve().parent
example_tracks_dir = script_dir.parent / "01_loading_agenttracks" / "example_tracks"


def print_state(label: str, installed_dir: Path) -> None:
    """Print tracked, loaded, and persisted track state."""
    print(f"\n{label}")
    print("-" * len(label))

    installed = list_installed_tracks(installed_dir=installed_dir)
    print("Tracked tracks:")
    for info in installed:
        print(f"  - {info.name} (enabled={info.enabled}, source={info.source})")

    loaded = load_installed_tracks(installed_dir=installed_dir)
    print(f"Loaded tracks: {[track.name for track in loaded]}")

    metadata = json.loads((installed_dir / ".installed.json").read_text())
    print("Metadata file:")
    print(json.dumps(metadata, indent=2))


def demo_install_tracks(installed_dir: Path) -> list[str]:
    """Install the sample tracks into the isolated installed directory."""
    print("\n" + "=" * 60)
    print("DEMO 1: Installing local tracks")
    print("=" * 60)

    installed_names: list[str] = []
    for track_dir in sorted(example_tracks_dir.iterdir()):
        if not track_dir.is_dir():
            continue
        info = install_track(source=str(track_dir), installed_dir=installed_dir)
        installed_names.append(info.name)
        print(f"✓ Installed: {info.name}")
        print(f"  Source: {info.source}")
        print(f"  Path: {info.install_path}")

    return installed_names


def demo_list_and_load_tracks(installed_dir: Path) -> None:
    """List tracked tracks and load them as runtime Track objects."""
    print("\n" + "=" * 60)
    print("DEMO 2: Listing and loading installed tracks")
    print("=" * 60)

    installed = list_installed_tracks(installed_dir=installed_dir)
    print("Tracked tracks:")
    for info in installed:
        desc = (info.description or "No description")[:60]
        print(f"  - {info.name} (enabled={info.enabled})")
        print(f"    Description: {desc}...")

    loaded = load_installed_tracks(installed_dir=installed_dir)
    print(f"\nLoaded {len(loaded)} track(s):")
    for track in loaded:
        desc = (track.description or "No description")[:60]
        print(f"  - {track.name}: {desc}...")


def demo_enable_disable_track(installed_dir: Path, track_name: str) -> None:
    """Disable then re-enable a track and show the persisted metadata."""
    print("\n" + "=" * 60)
    print("DEMO 3: Disabling and re-enabling a track")
    print("=" * 60)

    print_state("Before disable", installed_dir)

    assert disable_track(track_name, installed_dir=installed_dir) is True
    print_state("After disable", installed_dir)
    assert track_name not in [
        track.name for track in load_installed_tracks(installed_dir=installed_dir)
    ]

    metadata = json.loads((installed_dir / ".installed.json").read_text())
    assert metadata["tracks"][track_name]["enabled"] is False

    assert enable_track(track_name, installed_dir=installed_dir) is True
    print_state("After re-enable", installed_dir)

    metadata = json.loads((installed_dir / ".installed.json").read_text())
    assert metadata["tracks"][track_name]["enabled"] is True
    assert track_name in [
        track.name for track in load_installed_tracks(installed_dir=installed_dir)
    ]


def demo_uninstall_track(
    installed_dir: Path, track_name: str, remaining_track_name: str
) -> None:
    """Uninstall one track and confirm the other track remains available."""
    print("\n" + "=" * 60)
    print("DEMO 4: Uninstalling a track")
    print("=" * 60)

    assert uninstall_track(track_name, installed_dir=installed_dir) is True
    print_state("After uninstall", installed_dir)

    assert not (installed_dir / track_name).exists()
    metadata = json.loads((installed_dir / ".installed.json").read_text())
    assert track_name not in metadata["tracks"]
    assert remaining_track_name in metadata["tracks"]


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmpdir:
        installed_dir = Path(tmpdir) / "installed-tracks"
        installed_dir.mkdir(parents=True)

        installed_names = demo_install_tracks(installed_dir)
        demo_list_and_load_tracks(installed_dir)
        demo_enable_disable_track(installed_dir, track_name="rot13-encryption")
        demo_uninstall_track(
            installed_dir,
            track_name="rot13-encryption",
            remaining_track_name="code-style-guide",
        )

        remaining_names = [
            info.name for info in list_installed_tracks(installed_dir=installed_dir)
        ]
        assert remaining_names == ["code-style-guide"]
        assert sorted(installed_names) == ["code-style-guide", "rot13-encryption"]

    print("\nEXAMPLE_COST: 0")
