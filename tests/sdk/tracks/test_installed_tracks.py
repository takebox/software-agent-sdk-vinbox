"""Tests for installed tracks management.

These tests verify the public API in ``handprint.sdk.tracks.installed``
delegates correctly to ``InstallationManager``.  Internal metadata and
sync logic is already covered by ``tests/sdk/extensions/installation/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from handprint.sdk.marketplace import Marketplace, MarketplaceRegistration
from handprint.sdk.tracks import (
    Track,
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


def _create_track_dir(
    base_dir: Path,
    dir_name: str,
    *,
    description: str = "A test track",
) -> Path:
    track_dir = base_dir / dir_name
    track_dir.mkdir(parents=True)
    track_md = f"---\nname: {dir_name}\ndescription: {description}\n---\n# {dir_name}\n"
    (track_dir / "TRACK.md").write_text(track_md)
    return track_dir


@pytest.fixture
def installed_dir(tmp_path: Path) -> Path:
    installed = tmp_path / "installed"
    installed.mkdir(parents=True)
    return installed


@pytest.fixture
def sample_track_dir(tmp_path: Path) -> Path:
    return _create_track_dir(tmp_path, "sample-track")


# ============================================================================
# Public API smoke tests
# ============================================================================


def test_get_installed_tracks_dir_returns_default_path() -> None:
    path = get_installed_tracks_dir()
    assert ".handprint" in str(path)
    assert "tracks" in str(path)
    assert "installed" in str(path)


def test_install_from_local_path(sample_track_dir: Path, installed_dir: Path) -> None:
    info = install_track(source=str(sample_track_dir), installed_dir=installed_dir)

    assert info.name == "sample-track"
    assert info.source == str(sample_track_dir)
    assert info.description == "A test track"
    assert (installed_dir / "sample-track" / "TRACK.md").exists()


def test_install_already_exists_raises_error(
    sample_track_dir: Path, installed_dir: Path
) -> None:
    install_track(source=str(sample_track_dir), installed_dir=installed_dir)
    with pytest.raises(FileExistsError, match="already installed"):
        install_track(source=str(sample_track_dir), installed_dir=installed_dir)


def test_install_with_force_overwrites(
    sample_track_dir: Path, installed_dir: Path
) -> None:
    install_track(source=str(sample_track_dir), installed_dir=installed_dir)
    marker = installed_dir / "sample-track" / "marker.txt"
    marker.write_text("original")

    install_track(
        source=str(sample_track_dir),
        installed_dir=installed_dir,
        force=True,
    )
    assert not marker.exists()


def test_uninstall_existing_track(sample_track_dir: Path, installed_dir: Path) -> None:
    install_track(source=str(sample_track_dir), installed_dir=installed_dir)
    assert uninstall_track("sample-track", installed_dir=installed_dir)
    assert not (installed_dir / "sample-track").exists()


def test_list_installed_tracks(sample_track_dir: Path, installed_dir: Path) -> None:
    install_track(source=str(sample_track_dir), installed_dir=installed_dir)
    tracks = list_installed_tracks(installed_dir=installed_dir)
    assert len(tracks) == 1
    assert tracks[0].name == "sample-track"


def test_load_installed_tracks(sample_track_dir: Path, installed_dir: Path) -> None:
    install_track(source=str(sample_track_dir), installed_dir=installed_dir)
    tracks = load_installed_tracks(installed_dir=installed_dir)
    assert len(tracks) == 1
    assert isinstance(tracks[0], Track)
    assert tracks[0].name == "sample-track"


def test_disable_track_filters_load(
    sample_track_dir: Path, installed_dir: Path
) -> None:
    install_track(source=str(sample_track_dir), installed_dir=installed_dir)
    assert disable_track("sample-track", installed_dir=installed_dir)

    assert load_installed_tracks(installed_dir=installed_dir) == []
    info = get_installed_track("sample-track", installed_dir=installed_dir)
    assert info is not None
    assert info.enabled is False


def test_enable_track_restores_load(
    sample_track_dir: Path, installed_dir: Path
) -> None:
    install_track(source=str(sample_track_dir), installed_dir=installed_dir)
    disable_track("sample-track", installed_dir=installed_dir)
    assert enable_track("sample-track", installed_dir=installed_dir)

    tracks = load_installed_tracks(installed_dir=installed_dir)
    assert len(tracks) == 1
    assert tracks[0].name == "sample-track"


def test_get_installed_track(sample_track_dir: Path, installed_dir: Path) -> None:
    install_track(source=str(sample_track_dir), installed_dir=installed_dir)
    info = get_installed_track("sample-track", installed_dir=installed_dir)
    assert info is not None
    assert info.name == "sample-track"


def test_get_nonexistent_track(installed_dir: Path) -> None:
    assert get_installed_track("nonexistent", installed_dir=installed_dir) is None


def test_update_track_reinstalls_from_source(
    sample_track_dir: Path, installed_dir: Path
) -> None:
    install_track(source=str(sample_track_dir), installed_dir=installed_dir)
    disable_track("sample-track", installed_dir=installed_dir)

    (sample_track_dir / "TRACK.md").write_text(
        "---\nname: sample-track\ndescription: Updated description\n"
        "---\n# sample-track\n"
    )

    info = update_track("sample-track", installed_dir=installed_dir)
    assert info is not None
    assert info.description == "Updated description"
    assert info.enabled is False
    content = (installed_dir / "sample-track" / "TRACK.md").read_text()
    assert "Updated description" in content


def test_update_nonexistent_track(installed_dir: Path) -> None:
    assert update_track("nonexistent", installed_dir=installed_dir) is None


# ============================================================================
# Marketplace tests
# ============================================================================


def _create_marketplace(
    base_dir: Path,
    tracks: list[dict[str, str]],
    plugins: list[dict[str, str]] | None = None,
) -> Path:
    marketplace_dir = base_dir / "marketplace"
    marketplace_dir.mkdir(parents=True)
    plugin_dir = marketplace_dir / ".plugin"
    plugin_dir.mkdir()
    manifest = {
        "name": "test-marketplace",
        "owner": {"name": "Test"},
        "tracks": tracks,
        "plugins": plugins or [],
    }
    (plugin_dir / "marketplace.json").write_text(json.dumps(manifest))
    return marketplace_dir


class TestInstallTracksFromMarketplace:
    def test_install_local_tracks(self, tmp_path: Path) -> None:
        marketplace_dir = _create_marketplace(
            tmp_path,
            tracks=[{"name": "my-track", "source": "./tracks/my-track"}],
        )
        track_dir = marketplace_dir / "tracks" / "my-track"
        track_dir.mkdir(parents=True)
        (track_dir / "TRACK.md").write_text(
            "---\nname: my-track\ndescription: Test\n---\n# my-track"
        )
        installed_dir = tmp_path / "installed"
        installed_dir.mkdir()

        installed = install_tracks_from_marketplace(
            marketplace_dir, installed_dir=installed_dir
        )
        assert len(installed) == 1
        assert installed[0].name == "my-track"

    def test_install_tracks_force_overwrite(self, tmp_path: Path) -> None:
        marketplace_dir = _create_marketplace(
            tmp_path,
            tracks=[{"name": "my-track", "source": "./tracks/my-track"}],
        )
        track_dir = marketplace_dir / "tracks" / "my-track"
        track_dir.mkdir(parents=True)
        (track_dir / "TRACK.md").write_text(
            "---\nname: my-track\ndescription: Original\n---\n# my-track"
        )
        installed_dir = tmp_path / "installed"
        installed_dir.mkdir()

        install_tracks_from_marketplace(marketplace_dir, installed_dir=installed_dir)
        (track_dir / "TRACK.md").write_text(
            "---\nname: my-track\ndescription: Updated\n---\n# my-track"
        )

        # Without force — already exists
        installed = install_tracks_from_marketplace(
            marketplace_dir, installed_dir=installed_dir, force=False
        )
        assert len(installed) == 0

        # With force — overwrites
        installed = install_tracks_from_marketplace(
            marketplace_dir, installed_dir=installed_dir, force=True
        )
        assert len(installed) == 1
        content = (installed_dir / "my-track" / "TRACK.md").read_text()
        assert "Updated" in content

    def test_install_handles_missing_track_source(self, tmp_path: Path) -> None:
        marketplace_dir = _create_marketplace(
            tmp_path,
            tracks=[{"name": "missing", "source": "./does-not-exist"}],
        )
        installed_dir = tmp_path / "installed"
        installed_dir.mkdir()

        installed = install_tracks_from_marketplace(
            marketplace_dir, installed_dir=installed_dir
        )
        assert len(installed) == 0

    def test_install_tracks_from_plugin_directories(self, tmp_path: Path) -> None:
        marketplace_dir = _create_marketplace(
            tmp_path,
            tracks=[],
            plugins=[{"name": "my-plugin", "source": "./plugins/my-plugin"}],
        )
        plugin_dir = marketplace_dir / "plugins" / "my-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text('{"name": "my-plugin"}')

        track_dir = plugin_dir / "tracks" / "plugin-track"
        track_dir.mkdir(parents=True)
        (track_dir / "TRACK.md").write_text(
            "---\nname: plugin-track\ndescription: From plugin\n---\n# plugin-track"
        )
        installed_dir = tmp_path / "installed"
        installed_dir.mkdir()

        installed = install_tracks_from_marketplace(
            marketplace_dir, installed_dir=installed_dir
        )
        assert len(installed) == 1
        assert installed[0].name == "plugin-track"

    def test_install_both_standalone_and_plugin_tracks(self, tmp_path: Path) -> None:
        marketplace_dir = _create_marketplace(
            tmp_path,
            tracks=[{"name": "standalone", "source": "./tracks/standalone"}],
            plugins=[{"name": "my-plugin", "source": "./plugins/my-plugin"}],
        )
        standalone_dir = marketplace_dir / "tracks" / "standalone"
        standalone_dir.mkdir(parents=True)
        (standalone_dir / "TRACK.md").write_text(
            "---\nname: standalone\ndescription: Standalone\n---\n# standalone"
        )

        plugin_dir = marketplace_dir / "plugins" / "my-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text('{"name": "my-plugin"}')

        plugin_track_dir = plugin_dir / "tracks" / "from-plugin"
        plugin_track_dir.mkdir(parents=True)
        (plugin_track_dir / "TRACK.md").write_text(
            "---\nname: from-plugin\ndescription: From plugin\n---\n# from-plugin"
        )
        installed_dir = tmp_path / "installed"
        installed_dir.mkdir()

        installed = install_tracks_from_marketplace(
            marketplace_dir, installed_dir=installed_dir
        )
        names = {s.name for s in installed}
        assert names == {"standalone", "from-plugin"}


class TestLoadMarketplaceStandaloneTracks:
    """The shared helper used by both marketplace auto-load paths."""

    @staticmethod
    def _marketplace(tmp_path: Path) -> Path:
        marketplace_dir = _create_marketplace(
            tmp_path,
            tracks=[
                {"name": "greet", "source": "./tracks/greet"},
                {"name": "commit", "source": "./tracks/commit"},
            ],
        )
        for name in ("greet", "commit"):
            track_dir = marketplace_dir / "tracks" / name
            track_dir.mkdir(parents=True)
            (track_dir / "TRACK.md").write_text(
                f"---\nname: {name}\ndescription: {name}\n---\n# {name}"
            )
        return marketplace_dir

    def test_loads_all_when_auto_load_true(self, tmp_path: Path) -> None:
        d = self._marketplace(tmp_path)
        tracks = load_marketplace_standalone_tracks(
            Marketplace.load(d),
            d,
            MarketplaceRegistration(name="m", source=str(d), auto_load=True),
        )
        assert {s.name for s in tracks} == {"greet", "commit"}

    def test_selects_listed_names(self, tmp_path: Path) -> None:
        d = self._marketplace(tmp_path)
        tracks = load_marketplace_standalone_tracks(
            Marketplace.load(d),
            d,
            MarketplaceRegistration(name="m", source=str(d), auto_load=["greet"]),
        )
        assert [s.name for s in tracks] == ["greet"]

    def test_empty_when_not_auto_load(self, tmp_path: Path) -> None:
        d = self._marketplace(tmp_path)
        tracks = load_marketplace_standalone_tracks(
            Marketplace.load(d),
            d,
            MarketplaceRegistration(name="m", source=str(d)),
        )
        assert tracks == []

    def test_missing_track_md_is_skipped_not_raised(self, tmp_path: Path) -> None:
        # Track entry points at a dir with no TRACK.md -> warn-and-skip.
        d = _create_marketplace(
            tmp_path, tracks=[{"name": "broken", "source": "./tracks/broken"}]
        )
        (d / "tracks" / "broken").mkdir(parents=True)
        tracks = load_marketplace_standalone_tracks(
            Marketplace.load(d),
            d,
            MarketplaceRegistration(name="m", source=str(d), auto_load=True),
        )
        assert tracks == []
