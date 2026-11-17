"""Track fetching utilities for AgentTracks sources.

Delegates to :mod:`handprint.sdk.extensions.fetch` for the actual fetch logic
and re-raises errors as :class:`TrackFetchError` to preserve the existing
public interface.
"""

from __future__ import annotations

from pathlib import Path

from handprint.sdk.extensions.fetch import (
    ExtensionFetchError,
    fetch_with_resolution as _ext_fetch_with_resolution,
)
from handprint.sdk.git.cached_repo import GitHelper
from handprint.sdk.utils.path import get_user_persistence_dir


DEFAULT_CACHE_DIR = get_user_persistence_dir() / "cache" / "tracks"


class TrackFetchError(Exception):
    """Raised when fetching a track fails."""


def fetch_track(
    source: str,
    cache_dir: Path | None = None,
    ref: str | None = None,
    update: bool = True,
    repo_path: str | None = None,
    git_helper: GitHelper | None = None,
) -> Path:
    """Fetch a track from a source and return the local path.

    Args:
        source: Track source - git URL, GitHub shorthand, or local path.
        cache_dir: Directory for caching. Defaults to ~/.handprint/cache/tracks/.
        ref: Optional branch, tag, or commit to checkout.
        update: If True and cache exists, update it.
        repo_path: Subdirectory path within the repository.
        git_helper: GitHelper instance (for testing).

    Returns:
        Path to the local track directory.
    """
    path, _ = fetch_track_with_resolution(
        source=source,
        cache_dir=cache_dir,
        ref=ref,
        update=update,
        repo_path=repo_path,
        git_helper=git_helper,
    )
    return path


def fetch_track_with_resolution(
    source: str,
    cache_dir: Path | None = None,
    ref: str | None = None,
    update: bool = True,
    repo_path: str | None = None,
    git_helper: GitHelper | None = None,
) -> tuple[Path, str | None]:
    """Fetch a track and return both the path and resolved commit SHA.

    Args:
        source: Track source (git URL, GitHub shorthand, or local path).
        cache_dir: Directory for caching. Defaults to ~/.handprint/cache/tracks/.
        ref: Optional branch, tag, or commit to checkout.
        update: If True and cache exists, update it.
        repo_path: Subdirectory path within the repository.
        git_helper: GitHelper instance (for testing).

    Returns:
        Tuple of (path, resolved_ref) where resolved_ref is the commit SHA for git
        sources and None for local paths.

    Raises:
        TrackFetchError: If fetching the track fails.
    """
    resolved_cache_dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
    try:
        return _ext_fetch_with_resolution(
            source=source,
            cache_dir=resolved_cache_dir,
            ref=ref,
            update=update,
            repo_path=repo_path,
            git_helper=git_helper,
        )
    except ExtensionFetchError as exc:
        raise TrackFetchError("Failed to fetch track") from exc
