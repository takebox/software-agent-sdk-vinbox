"""Installed tracks management for Handprint SDK.

Public API for managing AgentTracks installed in the user's home directory.
All heavy lifting is delegated to ``InstallationManager``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from handprint.sdk.extensions.installation import (
    InstallationInfo,
    InstallationInterface,
    InstallationManager,
)
from handprint.sdk.logger import get_logger
from handprint.sdk.tracks.exceptions import TrackValidationError
from handprint.sdk.tracks.track import Track
from handprint.sdk.tracks.utils import find_track_md
from handprint.sdk.utils.path import get_user_persistence_dir, to_posix_path


if TYPE_CHECKING:
    from handprint.sdk.marketplace import Marketplace, MarketplaceRegistration


logger = get_logger(__name__)

# Public type alias — keeps existing import sites working.
InstalledTrackInfo = InstallationInfo

DEFAULT_INSTALLED_TRACKS_DIR = get_user_persistence_dir() / "tracks" / "installed"


def get_installed_tracks_dir() -> Path:
    """Get the default directory for installed tracks."""
    return DEFAULT_INSTALLED_TRACKS_DIR


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_track_from_dir(track_root: Path, strict: bool = True) -> Track:
    """Load a track from its root directory."""
    track_md = find_track_md(track_root)
    if not track_md:
        raise TrackValidationError(f"Track directory is missing TRACK.md: {track_root}")
    return Track.load(track_md, strict=strict)


def load_marketplace_standalone_tracks(
    marketplace: Marketplace,
    marketplace_path: Path,
    registration: MarketplaceRegistration,
) -> list[Track]:
    """Load a marketplace's auto-loadable standalone tracks.

    Mirrors the plugin auto-load path for ``marketplace.tracks``: each track the
    registration auto-loads is resolved (relative to the marketplace repo, or a
    remote source) and loaded. Unresolvable sources and tracks missing TRACK.md
    are skipped with a warning so one bad entry never blocks the rest.
    """
    from handprint.sdk.plugin import resolve_source_path

    tracks: list[Track] = []
    for entry in marketplace.tracks:
        if not registration.auto_loads_track(entry.name):
            continue
        track_dir = resolve_source_path(entry.source, base_path=marketplace_path)
        if track_dir is None:
            logger.warning(
                "Track '%s' from marketplace '%s' could not be resolved; skipping",
                entry.name,
                registration.name,
            )
            continue
        try:
            tracks.append(_load_track_from_dir(track_dir, strict=False))
        except Exception:
            logger.warning(
                "Failed to load track '%s' from marketplace '%s'",
                entry.name,
                registration.name,
                exc_info=True,
            )
    return tracks


class TrackInstallationInterface(InstallationInterface[Track]):
    @staticmethod
    def load_from_dir(extension_dir: Path) -> Track:
        return _load_track_from_dir(extension_dir)


def _resolve_installed_dir(installed_dir: Path | None) -> Path:
    return installed_dir if installed_dir is not None else DEFAULT_INSTALLED_TRACKS_DIR


def _manager(installed_dir: Path) -> InstallationManager[Track]:
    return InstallationManager(
        installation_dir=installed_dir,
        installation_interface=TrackInstallationInterface(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_track(
    source: str,
    ref: str | None = None,
    repo_path: str | None = None,
    installed_dir: Path | None = None,
    force: bool = False,
) -> InstalledTrackInfo:
    """Install a track from a source.

    Args:
        source: Track source — git URL, GitHub shorthand, or local path.
        ref: Optional branch, tag, or commit to install.
        repo_path: Subdirectory path within the repository (for monorepos).
        installed_dir: Directory for installed tracks.
            Defaults to ``~/.handprint/tracks/installed/``.
        force: If True, overwrite existing installation.

    Returns:
        InstalledTrackInfo with details about the installation.
    """
    return _manager(_resolve_installed_dir(installed_dir)).install(
        source, ref=ref, repo_path=repo_path, force=force
    )


def uninstall_track(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """Uninstall a track by name.

    Returns:
        True if the track was uninstalled, False if it wasn't installed.
    """
    return _manager(_resolve_installed_dir(installed_dir)).uninstall(name)


def enable_track(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """Enable an installed track by name."""
    return _manager(_resolve_installed_dir(installed_dir)).enable(name)


def disable_track(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """Disable an installed track by name."""
    return _manager(_resolve_installed_dir(installed_dir)).disable(name)


def list_installed_tracks(
    installed_dir: Path | None = None,
) -> list[InstalledTrackInfo]:
    """List all installed tracks.

    Self-healing: reconciles metadata with what is on disk.
    """
    return _manager(_resolve_installed_dir(installed_dir)).list_installed()


def load_installed_tracks(
    installed_dir: Path | None = None,
) -> list[Track]:
    """Load all enabled installed tracks as ``Track`` objects."""
    return _manager(_resolve_installed_dir(installed_dir)).load_installed()


def get_installed_track(
    name: str,
    installed_dir: Path | None = None,
) -> InstalledTrackInfo | None:
    """Get information about a specific installed track."""
    return _manager(_resolve_installed_dir(installed_dir)).get(name)


def update_track(
    name: str,
    installed_dir: Path | None = None,
) -> InstalledTrackInfo | None:
    """Update an installed track to the latest version."""
    return _manager(_resolve_installed_dir(installed_dir)).update(name)


def install_tracks_from_marketplace(
    marketplace_path: str | Path,
    installed_dir: Path | None = None,
    force: bool = False,
) -> list[InstalledTrackInfo]:
    """Install all tracks defined in a marketplace.json file.

    Args:
        marketplace_path: Path to the directory containing
            ``.plugin/marketplace.json``.
        installed_dir: Directory for installed tracks.
            Defaults to ``~/.handprint/tracks/installed/``.
        force: If True, overwrite existing installations.

    Returns:
        List of InstalledTrackInfo for successfully installed tracks.
    """
    from handprint.sdk.marketplace import Marketplace
    from handprint.sdk.plugin import resolve_source_path

    marketplace_path = Path(marketplace_path)
    installed_dir = _resolve_installed_dir(installed_dir)

    marketplace = Marketplace.load(marketplace_path)
    installed: list[InstalledTrackInfo] = []

    track_dirs: list[tuple[str, Path]] = []

    for entry in marketplace.tracks:
        resolved = resolve_source_path(
            entry.source, base_path=marketplace_path, update=True
        )
        if resolved and resolved.exists():
            track_dirs.append((entry.name, resolved))
        else:
            logger.warning(f"Failed to resolve track '{entry.name}'")

    for plugin in marketplace.plugins:
        if isinstance(plugin.source, str):
            source = plugin.source
        elif plugin.source.repo:
            source = f"https://github.com/{plugin.source.repo}.git"
        elif plugin.source.url:
            source = plugin.source.url
        else:
            logger.warning(f"Plugin '{plugin.name}' has unsupported source")
            continue

        resolved = resolve_source_path(source, base_path=marketplace_path, update=True)
        if not resolved or not resolved.exists():
            logger.warning(f"Failed to resolve plugin '{plugin.name}'")
            continue

        tracks_dir = resolved / "tracks"
        if not tracks_dir.exists():
            continue

        for track_path in sorted(tracks_dir.iterdir()):
            if track_path.is_dir() and (track_path / "TRACK.md").exists():
                track_dirs.append((track_path.name, track_path))

    logger.info(f"Found {len(track_dirs)} tracks to install from marketplace")

    for name, path in track_dirs:
        try:
            info = install_track(
                to_posix_path(path), installed_dir=installed_dir, force=force
            )
            installed.append(info)
            logger.info(f"Installed track '{info.name}'")
        except FileExistsError:
            logger.info(f"Track '{name}' already installed (use force=True)")
        except Exception as e:
            logger.warning(f"Failed to install track '{name}': {e}")

    logger.info(f"Installed {len(installed)} tracks")
    return installed
