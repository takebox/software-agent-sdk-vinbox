"""Tests for EXTENSIONS_REF environment variable support.

Subprocess-based tests isolate module-level state (PUBLIC_TRACKS_REF is read
at import time). In-process tests cover runtime cache behaviour.
"""

import subprocess
import sys
import threading
import time
from unittest.mock import patch


def _run_in_subprocess(test_code: str, env_extra: dict | None = None) -> None:
    """Run test code in a subprocess with the given environment variables."""
    import os

    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)

    result = subprocess.run(
        [sys.executable, "-c", test_code],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Subprocess test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


def test_extensions_ref_default():
    """PUBLIC_TRACKS_REF should default to 'main' when EXTENSIONS_REF is not set."""
    code = """
import os
if "EXTENSIONS_REF" in os.environ:
    del os.environ["EXTENSIONS_REF"]
from handprint.sdk.tracks.track import PUBLIC_TRACKS_REF
assert PUBLIC_TRACKS_REF == "main", (
    f"Expected 'main' but got '{PUBLIC_TRACKS_REF}'"
)
"""
    _run_in_subprocess(code)


def test_extensions_ref_custom_branch():
    """PUBLIC_TRACKS_REF should use EXTENSIONS_REF when set to a branch name."""
    code = """
from handprint.sdk.tracks.track import PUBLIC_TRACKS_REF
assert PUBLIC_TRACKS_REF == "feature-branch", (
    f"Expected 'feature-branch' but got '{PUBLIC_TRACKS_REF}'"
)
"""
    _run_in_subprocess(code, {"EXTENSIONS_REF": "feature-branch"})


def test_extensions_ref_with_load_public_tracks():
    """load_public_tracks should respect EXTENSIONS_REF environment variable."""
    code = """
from unittest import mock
from handprint.sdk.tracks.track import (
    PUBLIC_TRACKS_REF,
    load_public_tracks,
)
assert PUBLIC_TRACKS_REF == "test-branch", (
    f"Expected 'test-branch' but got '{PUBLIC_TRACKS_REF}'"
)
with mock.patch(
    "handprint.sdk.tracks.track.update_tracks_repository"
) as mock_update:
    mock_update.return_value = None
    load_public_tracks()
    mock_update.assert_called_once()
    call_args = mock_update.call_args
    # ref is 2nd positional arg: (repo_url, ref, cache_dir)
    assert call_args[0][1] == "test-branch", (
        f"Expected ref='test-branch' but got {call_args[0][1]}"
    )
"""
    _run_in_subprocess(code, {"EXTENSIONS_REF": "test-branch"})


def test_extensions_ref_with_tag():
    """PUBLIC_TRACKS_REF should accept a tag value via EXTENSIONS_REF."""
    code = """
from handprint.sdk.tracks.track import PUBLIC_TRACKS_REF
assert PUBLIC_TRACKS_REF == "v1.2.3", (
    f"Expected 'v1.2.3' but got '{PUBLIC_TRACKS_REF}'"
)
"""
    _run_in_subprocess(code, {"EXTENSIONS_REF": "v1.2.3"})


def test_extensions_ref_with_commit_sha():
    """PUBLIC_TRACKS_REF should accept a full commit SHA via EXTENSIONS_REF."""
    sha = "a" * 40
    code = f"""
from handprint.sdk.tracks.track import PUBLIC_TRACKS_REF
assert PUBLIC_TRACKS_REF == "{sha}", (
    f"Expected '{sha}' but got '{{PUBLIC_TRACKS_REF}}'"
)
"""
    _run_in_subprocess(code, {"EXTENSIONS_REF": sha})


def test_extensions_ref_empty_string():
    """Empty EXTENSIONS_REF falls back to an empty string (os.environ.get behaviour)."""
    code = """
from handprint.sdk.tracks.track import PUBLIC_TRACKS_REF
assert PUBLIC_TRACKS_REF == "", (
    f"Expected '' but got '{PUBLIC_TRACKS_REF}'"
)
"""
    _run_in_subprocess(code, {"EXTENSIONS_REF": ""})


# ---------------------------------------------------------------------------
# In-process tests for pinned-ref cache behaviour
# ---------------------------------------------------------------------------


def _seed_cache(
    cache: dict,
    lock: threading.Lock,
    cache_key: tuple,
    tracks: list,
    *,
    timestamp: float,
) -> None:
    """Seed the public-tracks cache with a synthetic entry."""
    with lock:
        cache[cache_key] = (timestamp, tracks)


def test_pinned_cache_entry_never_expires():
    """A pinned entry (timestamp=inf) is returned even after the TTL would have elapsed.

    This verifies that immutable refs (tags, commit SHAs) do not trigger
    remote polling once their tracks have been loaded once.
    """
    from handprint.sdk.tracks.track import (
        _PUBLIC_TRACKS_CACHE,
        _PUBLIC_TRACKS_CACHE_LOCK,
        Track,
        _invalidate_public_tracks_cache,
        load_public_tracks,
    )

    fake_track = Track(name="pinned-track", content="pinned content")
    cache_key = ("https://github.com/HandPrint-AI/extensions", "v1.0.0", None)

    _invalidate_public_tracks_cache()
    _seed_cache(
        _PUBLIC_TRACKS_CACHE,
        _PUBLIC_TRACKS_CACHE_LOCK,
        cache_key,
        [fake_track],
        timestamp=float("inf"),
    )

    with patch("handprint.sdk.tracks.track.update_tracks_repository") as mock_update:
        result = load_public_tracks(ref="v1.0.0", marketplace_path=None)
        mock_update.assert_not_called()

    assert len(result) == 1
    assert result[0].name == "pinned-track"


def test_mutable_cache_entry_expires_after_ttl():
    """A branch entry (finite timestamp) IS re-fetched once the TTL has passed."""
    from handprint.sdk.tracks.track import (
        _PUBLIC_TRACKS_CACHE,
        _PUBLIC_TRACKS_CACHE_LOCK,
        _PUBLIC_TRACKS_CACHE_TTL_SECONDS,
        Track,
        _invalidate_public_tracks_cache,
        load_public_tracks,
    )

    fake_track = Track(name="stale-track", content="stale content")
    cache_key = ("https://github.com/HandPrint-AI/extensions", "main", None)

    _invalidate_public_tracks_cache()
    _seed_cache(
        _PUBLIC_TRACKS_CACHE,
        _PUBLIC_TRACKS_CACHE_LOCK,
        cache_key,
        [fake_track],
        timestamp=time.monotonic() - _PUBLIC_TRACKS_CACHE_TTL_SECONDS - 1,
    )

    with patch("handprint.sdk.tracks.track.update_tracks_repository") as mock_update:
        mock_update.return_value = None  # simulates transient failure
        load_public_tracks(ref="main", marketplace_path=None)
        mock_update.assert_called_once()
