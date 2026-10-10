"""Track management for Handprint SDK.

This module provides the unified API for working with tracks:

**Core Track Model & Loading:**
- `Track` - The track data model
- `TrackResources` - Resource directories for a track (scripts/, references/, assets/)
- `load_tracks_from_dir` - Load tracks from a directory
- `load_project_tracks` - Load tracks from project's .agents/tracks/
- `load_user_tracks` - Load tracks from ~/.handprint/tracks/
- `load_public_tracks` - Load tracks from the public Handprint extensions repo
- `load_available_tracks` - Load and merge tracks from multiple sources
- `merge_tracks_by_name` - Merge two track collections by name (primary wins)

**Triggers:**
- `BaseTrigger`, `KeywordTrigger`, `TaskTrigger`, `PathTrigger` - activation triggers

**Installed Tracks Management:**
- `install_track` - Install a track from a source
- `uninstall_track` - Uninstall a track
- `list_installed_tracks` - List all installed tracks
- `load_installed_tracks` - Load enabled installed tracks
- `enable_track`, `disable_track` - Toggle track enabled state
- `update_track` - Update an installed track

**Types:**
- `TrackKnowledge` - Represents knowledge from a triggered track
- `InputMetadata` - Metadata for task track inputs

**Utilities:**
- `discover_track_resources` - Discover resource directories in a track
- `validate_track_name` - Validate track name per AgentTracks spec
- `to_prompt` - Generate XML prompt block for available tracks
"""

# Exceptions
from handprint.sdk.tracks.exceptions import TrackError, TrackValidationError

# Fetch utilities
from handprint.sdk.tracks.fetch import TrackFetchError, fetch_track_with_resolution

# Installed tracks management
from handprint.sdk.tracks.installed import (
    InstalledTrackInfo,
    disable_track,
    enable_track,
    get_installed_track,
    get_installed_tracks_dir,
    install_track,
    install_tracks_from_marketplace,
    list_installed_tracks,
    load_installed_tracks,
    load_marketplace_standalone_tracks,
    uninstall_track,
    update_track,
)

# Core track model and loading
from handprint.sdk.tracks.track import (
    Track,
    TrackInfo,
    TrackResources,
    load_available_tracks,
    load_project_tracks,
    load_public_tracks,
    load_tracks_from_dir,
    load_user_tracks,
    merge_tracks_by_name,
    to_prompt,
)

# Triggers
from handprint.sdk.tracks.trigger import (
    BaseTrigger,
    KeywordTrigger,
    PathTrigger,
    TaskTrigger,
)

# Types
from handprint.sdk.tracks.types import (
    InputMetadata,
    TrackContentResponse,
    TrackKnowledge,
    TrackResponse,
)

# Utilities
from handprint.sdk.tracks.utils import (
    RESOURCE_DIRECTORIES,
    discover_track_resources,
    validate_track_name,
)


__all__ = [
    # Exceptions
    "TrackError",
    "TrackValidationError",
    # Fetch
    "TrackFetchError",
    "fetch_track_with_resolution",
    # Installed tracks management
    "InstalledTrackInfo",
    "install_track",
    "install_tracks_from_marketplace",
    "load_marketplace_standalone_tracks",
    "uninstall_track",
    "list_installed_tracks",
    "load_installed_tracks",
    "get_installed_tracks_dir",
    "get_installed_track",
    "enable_track",
    "disable_track",
    "update_track",
    # Core track model and loading
    "Track",
    "TrackInfo",
    "TrackResources",
    "load_tracks_from_dir",
    "load_project_tracks",
    "load_user_tracks",
    "load_public_tracks",
    "load_available_tracks",
    "merge_tracks_by_name",
    "to_prompt",
    # Triggers
    "BaseTrigger",
    "KeywordTrigger",
    "PathTrigger",
    "TaskTrigger",
    # Types
    "TrackKnowledge",
    "InputMetadata",
    "TrackResponse",
    "TrackContentResponse",
    # Utilities
    "discover_track_resources",
    "RESOURCE_DIRECTORIES",
    "validate_track_name",
]
