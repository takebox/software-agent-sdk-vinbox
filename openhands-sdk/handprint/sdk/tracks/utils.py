"""Utility functions for track loading and management."""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from fastmcp.mcp_config import MCPConfig

from handprint.sdk.git.cached_repo import GitHelper, try_cached_clone_or_update
from handprint.sdk.logger import get_logger
from handprint.sdk.tracks.exceptions import TrackValidationError
from handprint.sdk.utils.path import (
    get_user_persistence_dir,
    resolves_within,
    to_posix_path,
)


if TYPE_CHECKING:
    from handprint.sdk.mcp.config import MCPServer
    from handprint.sdk.tracks.track import Track, TrackResources

# Type alias for secret lookup functions
SecretLookup = Callable[[str], str | None]

logger = get_logger(__name__)

# Regex patterns for variable expansion
# Braced only: ${VAR} or ${VAR:-default}
_BRACED_VAR_PATTERN = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)(?::-([^}]*))?\}")
# Braced and unbraced: $VAR, ${VAR}, or ${VAR:-default}
_ALL_VAR_PATTERN = re.compile(
    r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)(?::-([^}]*))?\}|\$([a-zA-Z_][a-zA-Z0-9_]*)"
)


def expand_variable_references(
    data: Any,
    *,
    variables: dict[str, str] | None = None,
    get_secret: SecretLookup | None = None,
    check_env: bool = False,
    expand_defaults: bool = True,
    support_unbraced: bool = False,
) -> Any:
    """Expand variable references in data structures.

    This is the core expansion function used by both MCP config expansion
    and runtime tool parameter expansion.

    Supports variable expansion patterns:
    - ${VAR} - Braced variable reference (always supported)
    - ${VAR:-default} - With default value (always supported)
    - $VAR - Unbraced variable reference (only if support_unbraced=True)

    Resolution order (each source is checked only if provided/enabled):
    1. Provided variables dict
    2. Secrets (via get_secret callback)
    3. Environment variables (only if check_env=True)
    4. Default value (only if expand_defaults=True)

    Args:
        data: Data to expand (string, dict, list, or other).
        variables: Dictionary of variable names to values.
        get_secret: Callback to look up a secret by name.
        check_env: If True, check os.environ for unresolved variables.
        expand_defaults: If True, apply default values for unresolved variables.
        support_unbraced: If True, support $VAR syntax in addition to ${VAR}.

    Returns:
        Data with variable references expanded.
    """
    pattern = _ALL_VAR_PATTERN if support_unbraced else _BRACED_VAR_PATTERN

    def replace_var(match: re.Match) -> str:
        # For braced pattern: group(1) = var_name, group(2) = default
        # For all pattern: group(1)=braced, group(2)=default, group(3)=unbraced
        if support_unbraced:
            braced_var = match.group(1)
            default_value = match.group(2)
            unbraced_var = match.group(3)
            var_name = braced_var or unbraced_var
        else:
            var_name = match.group(1)
            default_value = match.group(2)

        # Resolution order: variables -> secrets -> env -> default
        if variables is not None and var_name in variables:
            return variables[var_name]

        if get_secret is not None:
            secret_value = get_secret(var_name)
            if secret_value is not None:
                return secret_value

        if check_env and var_name in os.environ:
            return os.environ[var_name]

        # Apply default only if expand_defaults is True and we have a default
        if expand_defaults and default_value is not None:
            return default_value

        # Return original if not found (preserves placeholder)
        return match.group(0)

    def expand_value(value: Any) -> Any:
        match value:
            case str():
                return pattern.sub(replace_var, value)
            case dict():
                return {
                    expand_value(k) if isinstance(k, str) else k: expand_value(v)
                    for k, v in value.items()
                }
            case list():
                return [expand_value(item) for item in value]
            case _:
                return value

    return expand_value(data)


# Standard resource directory names per AgentTracks spec
RESOURCE_DIRECTORIES = ("scripts", "references", "assets")

# Regex pattern for valid AgentTracks names
# - 1-64 characters
# - Lowercase alphanumeric + hyphens only (a-z, 0-9, -)
# - Must not start or end with hyphen
# - Must not contain consecutive hyphens (--)
TRACK_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def find_track_md(track_dir: Path) -> Path | None:
    """Find TRACK.md file in a directory (case-insensitive).

    Args:
        track_dir: Path to the track directory to search.

    Returns:
        Path to TRACK.md if found, None otherwise.
    """
    if not track_dir.is_dir():
        return None
    # sorted() ensures deterministic case-collision winner (TRACK.md < track.md).
    for item in sorted(track_dir.iterdir()):
        if item.is_file() and item.name.lower() == "track.md":
            return item
    return None


def find_mcp_config(track_dir: Path) -> Path | None:
    """Find .mcp.json file in a track directory.

    Args:
        track_dir: Path to the track directory to search.

    Returns:
        Path to .mcp.json if found, None otherwise.
    """
    if not track_dir.is_dir():
        return None
    mcp_json = track_dir / ".mcp.json"
    if mcp_json.exists() and mcp_json.is_file():
        return mcp_json
    return None


def expand_mcp_variables(
    config: dict,
    variables: dict[str, str],
    get_secret: SecretLookup | None = None,
    *,  # keyword-only after this (PEP 3102)
    expand_defaults: bool = True,
) -> dict:
    """Expand variables in MCP configuration.

    Supports variable expansion similar to Haijun Code:
    - ${VAR} - Environment variables, provided variables, or secrets
    - ${VAR:-default} - With default value

    Resolution order:
    1. Provided variables (e.g., TRACK_ROOT)
    2. Secrets (via get_secret callback, if provided)
    3. Environment variables
    4. Default value (if specified and expand_defaults=True)

    Args:
        config: MCP configuration dictionary.
        variables: Dictionary of variable names to values (e.g., TRACK_ROOT).
        get_secret: Callback to look up a secret by name. We use a callback
            rather than a dict to avoid extracting all secrets into plain text.
            Pass `secret_registry.get_secret_value` or `{"K": "V"}.get` for tests.
        expand_defaults: If True, apply default values for unresolved variables.
            If False, preserve ${VAR:-default} as-is for later expansion.
            This allows deferred expansion when secrets are not yet available.

    Returns:
        Configuration with variables expanded.
    """
    # Use the shared expansion function with MCP config settings:
    # - check_env=True (check environment variables)
    # - support_unbraced=False (only ${VAR} syntax for config files)
    expanded_config = expand_variable_references(
        config,
        variables=variables,
        get_secret=get_secret,
        check_env=True,
        expand_defaults=expand_defaults,
        support_unbraced=False,
    )

    if not isinstance(expanded_config, dict):
        raise TypeError("expanded MCP config must be a dictionary")
    return expanded_config


def expand_mcp_servers(
    servers: Mapping[str, MCPServer],
    get_secret: SecretLookup | None = None,
) -> dict[str, MCPServer]:
    """Expand ``${VAR}`` placeholders in MCP servers, applying defaults.

    Servers with ``literal_values`` are returned untouched: they come from an
    Agent Plugins package, whose loader has already expanded the only two
    placeholders the standard allows, and §9.2 forbids expanding anything else
    -- a package must not be able to pull a secret into its own subprocess.
    """
    # Imported lazily: handprint.sdk.mcp imports this module.
    from handprint.sdk.mcp.config import coerce_mcp_config, dump_mcp_config

    expandable = {name: s for name, s in servers.items() if not s.literal_values}
    if not expandable:
        return dict(servers)
    expanded = expand_mcp_variables(
        {"mcpServers": dump_mcp_config(expandable)},
        {},
        get_secret=get_secret,
        expand_defaults=True,
    )
    return {**servers, **coerce_mcp_config(expanded["mcpServers"])}


def load_mcp_config(
    mcp_json_path: Path,
    track_root: Path | None = None,
    get_secret: SecretLookup | None = None,
    *,  # keyword-only after this (PEP 3102)
    expand_defaults: bool = True,
) -> dict:
    """Load and parse .mcp.json with variable expansion.

    Args:
        mcp_json_path: Path to the .mcp.json file.
        track_root: Root directory of the track (for ${TRACK_ROOT} expansion).
        get_secret: Optional callback to look up per-conversation secrets.
            See expand_mcp_variables() for details on why this is a callback.
        expand_defaults: If True, apply default values for unresolved variables.
            If False, preserve ${VAR:-default} as-is for later expansion.
            Use False during plugin loading to defer until secrets are available.

    Returns:
        Parsed MCP configuration dictionary.

    Raises:
        TrackValidationError: If the file cannot be parsed or is invalid.
    """
    try:
        with open(mcp_json_path, encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise TrackValidationError(f"Invalid JSON in {mcp_json_path}: {e}") from e
    except OSError as e:
        raise TrackValidationError(f"Cannot read {mcp_json_path}: {e}") from e

    if not isinstance(config, dict):
        raise TrackValidationError(
            f"Invalid .mcp.json format: expected object, got {type(config).__name__}"
        )

    # Prepare variables for expansion
    variables: dict[str, str] = {}
    if track_root:
        variables["TRACK_ROOT"] = str(track_root)

    # Expand variables (includes secrets if provided)
    config = expand_mcp_variables(
        config, variables, get_secret=get_secret, expand_defaults=expand_defaults
    )

    # Validate the external .mcp.json shape using FastMCP's config model.
    try:
        MCPConfig.model_validate(config)
    except Exception as e:
        raise TrackValidationError(f"Invalid MCP configuration: {e}") from e

    return config


def validate_track_name(name: str, directory_name: str | None = None) -> list[str]:
    """Validate track name according to AgentTracks spec.

    Args:
        name: The track name to validate.
        directory_name: Optional directory name to check for match.

    Returns:
        List of validation error messages (empty if valid).
    """
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

    if directory_name and name != directory_name:
        errors.append(f"Name '{name}' does not match directory '{directory_name}'")

    return errors


def find_third_party_files(
    repo_root: Path, third_party_track_names: dict[str, str]
) -> list[Path]:
    """Find third-party track files in the repository root.

    Searches for files like .cursorrules, AGENTS.md, HAIJUN.md, etc.
    with case-insensitive matching.

    Resolves symlinks so that e.g. ``HAIJUN.md -> AGENTS.md`` is detected
    as a duplicate and only the canonical (non-symlink) file is returned.

    Args:
        repo_root: Path to the repository root directory.
        third_party_track_names: Mapping of lowercase filenames to track names.

    Returns:
        List of paths to third-party track files found.
    """
    if not repo_root.exists():
        return []

    # Build a set of target filenames (lowercase) for case-insensitive matching
    target_names = {name.lower() for name in third_party_track_names}

    files: list[Path] = []
    seen_names: set[str] = set()
    seen_real_paths: set[Path] = set()
    # sorted() so an AGENTS.md/agents.md collision and the order are deterministic.
    for item in sorted(repo_root.iterdir()):
        if item.is_file() and item.name.lower() in target_names:
            # Avoid duplicates (e.g., AGENTS.md and agents.md in same dir)
            name_lower = item.name.lower()
            if name_lower in seen_names:
                logger.warning(
                    f"Duplicate third-party track file ignored: {item} "
                    f"(already found a file with name '{name_lower}')"
                )
                continue

            # Resolve symlinks to detect e.g. HAIJUN.md -> AGENTS.md
            real_path = item.resolve()
            if real_path in seen_real_paths:
                logger.debug(
                    f"Symlinked third-party track file ignored: {item} "
                    f"(resolves to already-loaded {real_path})"
                )
                continue

            files.append(item)
            seen_names.add(name_lower)
            seen_real_paths.add(real_path)
    return files


def _git_worktree_relpaths(work_dir: Path) -> list[PurePosixPath] | None:
    """Return worktree file paths under ``work_dir`` (relative to it): tracked
    plus untracked files that ``.gitignore`` does not exclude, so a freshly
    written (uncommitted) file still counts. None when git is unavailable, so the
    caller can walk instead."""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(work_dir),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return None
        text = proc.stdout.decode("utf-8", "surrogateescape")
        return [PurePosixPath(p) for p in text.split("\0") if p]
    return None


def _walk_relpaths(work_dir: Path) -> list[PurePosixPath]:
    """Filesystem-walk fallback: file paths under ``work_dir`` (relative to it),
    skipping hidden and ``node_modules`` directories. Used only when git is
    unavailable (the git path relies on ``.gitignore`` instead)."""
    results: list[PurePosixPath] = []
    for dirpath, dirnames, filenames in os.walk(work_dir):
        # Prune in place so os.walk does not descend into skipped directories.
        dirnames[:] = [
            d for d in dirnames if not d.startswith(".") and d != "node_modules"
        ]
        rel_dir = Path(dirpath).relative_to(work_dir)
        for filename in filenames:
            results.append(PurePosixPath((rel_dir / filename).as_posix()))
    return results


def find_nested_third_party_files(
    work_dir: Path, third_party_track_names: dict[str, str]
) -> list[tuple[Path, PurePosixPath]]:
    """Find third-party instruction files *nested* under ``work_dir`` (top-level
    ones are handled by :func:`find_third_party_files`), so each can become a
    directory-scoped path rule. Uses ``git ls-files`` when available, else a
    pruned walk. Returns ``(absolute_path, relative_dir)`` tuples with
    ``relative_dir`` POSIX-relative to ``work_dir``."""
    if not work_dir.exists():
        return []

    target_names = {name.lower() for name in third_party_track_names}
    rel_paths = _git_worktree_relpaths(work_dir)
    if rel_paths is None:
        rel_paths = _walk_relpaths(work_dir)

    results: list[tuple[Path, PurePosixPath]] = []
    seen_real_paths: set[Path] = set()
    for rel in rel_paths:
        if rel.name.lower() not in target_names:
            continue
        rel_dir = rel.parent
        # Skip top-level files: those belong to find_third_party_files.
        if rel_dir == PurePosixPath("."):
            continue
        abs_path = work_dir / rel
        if not abs_path.is_file():
            continue
        real_path = abs_path.resolve()
        if real_path in seen_real_paths:
            continue
        seen_real_paths.add(real_path)
        results.append((abs_path, rel_dir))
    return sorted(results, key=lambda pair: pair[1].as_posix())


def find_track_md_directories(track_dir: Path, root: Path | None = None) -> list[Path]:
    """Find AgentTracks-style directories containing TRACK.md files.

    Args:
        track_dir: Path to the tracks directory.
        root: If given, directories and TRACK.md files that resolve outside it
            are skipped, and an escaping directory is never listed.

    Returns:
        List of paths to TRACK.md files.
    """
    results: list[Path] = []
    if not track_dir.exists():
        return results
    for subdir in sorted(track_dir.iterdir()):
        if root is not None and not resolves_within(subdir, root):
            continue
        if subdir.is_dir():
            track_md = find_track_md(subdir)
            if track_md and (root is None or resolves_within(track_md, root)):
                results.append(track_md)
    return results


def find_regular_md_files(
    track_dir: Path,
    exclude_dirs: set[Path],
    recursive: bool = True,
    root: Path | None = None,
) -> list[Path]:
    """Find regular .md track files, excluding TRACK.md and files in excluded dirs.

    Args:
        track_dir: Path to the tracks directory.
        exclude_dirs: Set of directories to exclude (e.g., TRACK.md directories).
        recursive: If False, only scan the immediate children of track_dir,
            where every .md file except a README is a track.
        root: If given, files that resolve outside it are skipped.

    Returns:
        List of paths to regular .md track files.
    """
    files: list[Path] = []
    if not track_dir.exists():
        return files
    if not recursive:
        return [
            f
            for f in sorted(track_dir.glob("*.md"))
            if f.is_file()
            and f.name.lower() != "readme.md"
            and (root is None or resolves_within(f, root))
        ]
    for f in sorted(track_dir.rglob("*.md")):
        is_readme = f.name == "README.md"
        is_track_md = f.name.lower() == "track.md"
        is_in_excluded_dir = any(f.is_relative_to(d) for d in exclude_dirs)
        if not is_readme and not is_track_md and not is_in_excluded_dir:
            if root is None or resolves_within(f, root):
                files.append(f)
    return files


def load_and_categorize(
    path: Path,
    track_base_dir: Path,
    repo_tracks: dict[str, Track],
    knowledge_tracks: dict[str, Track],
    agent_tracks: dict[str, Track],
    strict: bool = True,
    root: Path | None = None,
) -> None:
    """Load a track and categorize it.

    Categorizes into repo_tracks, knowledge_tracks, or agent_tracks.

    Args:
        path: Path to the track file.
        track_base_dir: Base directory for tracks (used to derive relative names).
        repo_tracks: Dictionary for tracks with trigger=None (permanent context).
        knowledge_tracks: Dictionary for tracks with triggers (progressive).
        agent_tracks: Dictionary for AgentTracks standard TRACK.md files.
        strict: If True, enforce strict AgentTracks name validation.
        root: If given, a track-level ``.mcp.json`` that resolves outside it is
            not loaded.
    """
    # Import here to avoid circular dependency
    from handprint.sdk.tracks.track import Track

    skip_mcp = False
    if root is not None:
        mcp_json = find_mcp_config(path.parent)
        skip_mcp = mcp_json is not None and not resolves_within(mcp_json, root)
    track = Track.load(path, track_base_dir, strict=strict, skip_mcp=skip_mcp)

    # AgentTracks (TRACK.md directories) are a separate category from Handprint tracks.
    # They follow the AgentTracks standard and should be handled differently.
    is_track_md = path.name.lower() == "track.md"
    if is_track_md:
        agent_tracks[track.name] = track
    elif track.trigger is None:
        repo_tracks[track.name] = track
    else:
        knowledge_tracks[track.name] = track


def get_tracks_cache_dir() -> Path:
    """Get the local cache directory for public tracks repository.

    Returns:
        Path to the ``cache/tracks`` subdirectory of the user persistence
        directory (``~/.handprint/cache/tracks`` absent OH_PERSISTENCE_DIR).
    """
    cache_dir = get_user_persistence_dir() / "cache" / "tracks"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def update_tracks_repository(
    repo_url: str,
    ref: str,
    cache_dir: Path,
) -> Path | None:
    """Clone or update the local tracks repository.

    Uses the shared git caching infrastructure from handprint.sdk.git.cached_repo.
    When updating, performs: fetch -> checkout ref -> reset --hard to origin/ref.

    Args:
        repo_url: URL of the tracks repository.
        ref: Branch name, tag, or full commit SHA to checkout.
        cache_dir: Directory where the repository should be cached.

    Returns:
        Path to the local repository if successful, None otherwise.
    """
    repo_path = cache_dir / "public-tracks"
    return try_cached_clone_or_update(repo_url, repo_path, ref=ref, update=True)


def is_tracks_repo_pinned(repo_path: Path) -> bool:
    """Return True if the local tracks repo is pinned to a fixed ref.

    A pinned ref is one that cannot change over time — a tag or a specific
    commit SHA. After checking out such a ref the repository is left in
    detached HEAD state, which is the signal used here.

    Returns False on any git error so callers can safely treat the result
    as ``False`` (i.e., keep polling) when the state cannot be determined.
    """
    try:
        return GitHelper().get_current_branch(repo_path) is None
    except Exception:
        return False


def discover_track_resources(track_dir: Path) -> TrackResources:
    """Discover resource directories in a track directory.

    Scans for standard AgentTracks resource directories:
    - scripts/: Executable scripts
    - references/: Reference documentation
    - assets/: Static assets

    Args:
        track_dir: Path to the track directory.

    Returns:
        TrackResources with lists of files in each resource directory.
    """
    # Import here to avoid circular dependency
    from handprint.sdk.tracks.track import TrackResources

    collected: dict[str, list[str]] = {}
    for resource_type in RESOURCE_DIRECTORIES:
        resource_dir = track_dir / resource_type
        if resource_dir.is_dir():
            collected[resource_type] = _list_resource_files(resource_dir, resource_type)

    return TrackResources(
        track_root=to_posix_path(track_dir.resolve()),
        scripts=collected.get("scripts", []),
        references=collected.get("references", []),
        assets=collected.get("assets", []),
    )


def _list_resource_files(
    resource_dir: Path,
    resource_type: str,
) -> list[str]:
    """List files in a resource directory.

    Args:
        resource_dir: Path to the resource directory.
        resource_type: Type of resource (scripts, references, assets).

    Returns:
        List of relative file paths within the resource directory.
    """
    files: list[str] = []
    try:
        for item in resource_dir.rglob("*"):
            if item.is_file():
                # Store relative path from resource directory
                rel_path = item.relative_to(resource_dir)
                files.append(to_posix_path(rel_path))
    except OSError as e:
        logger.warning(f"Error listing {resource_type} directory: {e}")
    return sorted(files)
