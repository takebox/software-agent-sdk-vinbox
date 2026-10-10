# Mixed Marketplace Tracks Example

This example demonstrates how to create a marketplace that includes both local and remote tracks.

## Overview

A marketplace can reference tracks from multiple sources:
- **Local tracks**: Hosted in your project directory
- **Remote tracks**: Hosted on GitHub (or other Git repositories)

This pattern is useful when you want to:
- Maintain custom tracks locally in your project
- Reference community tracks from GitHub repositories
- Create a curated track set for your team

## Directory Structure

```
04_mixed_marketplace_tracks/
├── .plugin/
│   └── marketplace.json     # Marketplace configuration
├── tracks/
│   └── greeting-helper/
│       └── TRACK.md         # Local track
├── main.py                  # Example script
└── README.md                # This file
```

## Marketplace Schema

The `marketplace.json` file supports both plugins and tracks:

```json
{
    "name": "my-marketplace",
    "owner": {"name": "Team Name"},
    "tracks": [
        {
            "name": "local-track",
            "source": "./tracks/my-track",
            "description": "A local track"
        },
        {
            "name": "remote-track",
            "source": "https://github.com/owner/repo/blob/main/tracks/track-name",
            "description": "A remote track from GitHub"
        }
    ]
}
```

### Source Path Formats

Tracks can be sourced from:

1. **Relative local paths**: `./path` or `../path` (relative to marketplace directory)
2. **Absolute paths**: `/absolute/path`
3. **Home directory**: `~/path`
4. **File URLs**: `file:///path`
5. **GitHub URLs**: `https://github.com/{owner}/{repo}/blob/{branch}/{path}`

## Usage

```bash
# View marketplace information
python main.py

# Install all tracks from marketplace
python main.py --install

# Force reinstall existing tracks
python main.py --install --force

# List installed tracks
python main.py --list
```

## How It Works

1. **Marketplace Loading**: The `Marketplace.load()` function reads the `.plugin/marketplace.json` file

2. **Source Resolution**: Each track's source is resolved:
   - Local paths are resolved relative to the marketplace directory
   - GitHub URLs trigger a cached clone of the repository

3. **Track Installation**: The `install_tracks_from_marketplace()` function:
   - Resolves each track source
   - Copies the track to `~/.handprint/tracks/installed/`
   - Tracks installation metadata

4. **Track Loading**: Installed tracks can be loaded with `load_installed_tracks()`

## API Reference

### Install Tracks from Marketplace

```python
from handprint.sdk.tracks import install_tracks_from_marketplace

# Install all tracks from a marketplace
installed = install_tracks_from_marketplace("./my-marketplace", force=False)

for info in installed:
    print(f"Installed: {info.name}")
```

### Load Installed Tracks

```python
from handprint.sdk.tracks import load_installed_tracks

# Load all installed tracks
tracks = load_installed_tracks()

for track in tracks:
    print(f"Track: {track.name}")
    print(f"Description: {track.description}")
```

### List Installed Tracks

```python
from handprint.sdk.tracks import list_installed_tracks

# Get metadata for installed tracks
installed = list_installed_tracks()

for info in installed:
    print(f"{info.name}: {info.source}")
```
