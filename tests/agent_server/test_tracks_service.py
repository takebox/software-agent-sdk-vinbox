"""Tests for tracks service."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from handprint.agent_server.tracks_service import (
    SANDBOX_WORKER_URL_PREFIX,
    ExposedUrlData,
    TrackLoadResult,
    create_sandbox_track,
    discover_profile_tracks,
    load_all_tracks,
    load_org_tracks_from_url,
    load_registered_marketplace_tracks,
    merge_tracks,
    sync_public_tracks,
)
from handprint.sdk.marketplace.registration import MarketplaceRegistration
from handprint.sdk.tracks import Track


def _create_test_plugin(plugin_dir: Path, name: str, track_name: str) -> Path:
    manifest_dir = plugin_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": name, "version": "1.0.0"})
    )
    tracks_dir = plugin_dir / "tracks"
    tracks_dir.mkdir()
    (tracks_dir / f"{track_name}.md").write_text(
        f"---\nname: {track_name}\n---\n{track_name} content"
    )
    return plugin_dir


def _create_test_marketplace(marketplace_dir: Path) -> Path:
    _create_test_plugin(marketplace_dir / "plugins" / "auto", "auto", "auto-track")
    _create_test_plugin(
        marketplace_dir / "plugins" / "manual", "manual", "manual-track"
    )
    manifest_dir = marketplace_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "test-marketplace",
                "owner": {"name": "Test Team"},
                "plugins": [
                    {"name": "auto", "source": "./plugins/auto"},
                    {"name": "manual", "source": "./plugins/manual"},
                ],
            }
        )
    )
    return marketplace_dir


def _create_standalone_track(track_dir: Path, name: str) -> None:
    track_dir.mkdir(parents=True, exist_ok=True)
    (track_dir / "TRACK.md").write_text(
        f"---\nname: {name}\ndescription: {name} description\n---\n{name} content"
    )


def _create_tracks_only_marketplace(marketplace_dir: Path) -> Path:
    """Marketplace declaring only standalone tracks (no plugins)."""
    _create_standalone_track(marketplace_dir / "tracks" / "greet", "greet")
    _create_standalone_track(marketplace_dir / "tracks" / "commit", "commit")
    manifest_dir = marketplace_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "tracks-marketplace",
                "owner": {"name": "Test Team"},
                "plugins": [],
                "tracks": [
                    {"name": "greet", "source": "./tracks/greet"},
                    {"name": "commit", "source": "./tracks/commit"},
                ],
            }
        )
    )
    return marketplace_dir


class TestExposedUrlData:
    """Tests for ExposedUrlData dataclass."""

    def test_create_exposed_url_data(self):
        """Test creating ExposedUrlData instance."""
        url_data = ExposedUrlData(
            name="WORKER_8080",
            url="http://localhost:9080",
            port=9080,
        )
        assert url_data.name == "WORKER_8080"
        assert url_data.url == "http://localhost:9080"
        assert url_data.port == 8080


class TestCreateSandboxTrack:
    """Tests for create_sandbox_track function."""

    def test_create_sandbox_track_with_worker_urls(self):
        """Test creating sandbox track with WORKER_ prefixed URLs."""
        exposed_urls = [
            ExposedUrlData(name="WORKER_8080", url="http://localhost:9080", port=9080),
            ExposedUrlData(name="WORKER_3000", url="http://localhost:4000", port=4000),
        ]

        track = create_sandbox_track(exposed_urls)

        assert track is not None
        assert track.name == "work_hosts"
        assert "http://localhost:9080" in track.content
        assert "http://localhost:4000" in track.content
        assert "port 8080" in track.content
        assert "port 3000" in track.content
        assert track.trigger is None
        assert track.source is None

    def test_create_sandbox_track_no_worker_urls(self):
        """Test that non-WORKER_ URLs are filtered out."""
        exposed_urls = [
            ExposedUrlData(name="DATABASE", url="http://localhost:5432", port=5432),
            ExposedUrlData(name="REDIS", url="http://localhost:6379", port=6379),
        ]

        track = create_sandbox_track(exposed_urls)

        assert track is None

    def test_create_sandbox_track_mixed_urls(self):
        """Test with mix of WORKER_ and non-WORKER_ URLs."""
        exposed_urls = [
            ExposedUrlData(name="WORKER_8080", url="http://localhost:9080", port=9080),
            ExposedUrlData(name="DATABASE", url="http://localhost:5432", port=5432),
            ExposedUrlData(name="WORKER_3000", url="http://localhost:4000", port=4000),
        ]

        track = create_sandbox_track(exposed_urls)

        assert track is not None
        assert "http://localhost:9080" in track.content
        assert "http://localhost:4000" in track.content
        assert "http://localhost:5432" not in track.content

    def test_create_sandbox_track_empty_list(self):
        """Test with empty URL list."""
        track = create_sandbox_track([])
        assert track is None

    def test_sandbox_worker_url_prefix_constant(self):
        """Test that SANDBOX_WORKER_URL_PREFIX is correctly defined."""
        assert SANDBOX_WORKER_URL_PREFIX == "WORKER_"


class TestMergeTracks:
    """Tests for merge_tracks function."""

    def test_merge_empty_lists(self):
        """Test merging empty track lists."""
        result = merge_tracks([[], [], []])
        assert result == []

    def test_merge_single_list(self):
        """Test merging a single track list."""
        tracks = [
            Track(name="track1", content="content1", trigger=None),
            Track(name="track2", content="content2", trigger=None),
        ]

        result = merge_tracks([tracks])

        assert len(result) == 2
        assert {s.name for s in result} == {"track1", "track2"}

    def test_merge_multiple_lists_no_duplicates(self):
        """Test merging multiple lists without duplicates."""
        list1 = [Track(name="track1", content="content1", trigger=None)]
        list2 = [Track(name="track2", content="content2", trigger=None)]
        list3 = [Track(name="track3", content="content3", trigger=None)]

        result = merge_tracks([list1, list2, list3])

        assert len(result) == 3
        assert {s.name for s in result} == {"track1", "track2", "track3"}

    def test_merge_with_duplicates_later_wins(self):
        """Test that later lists override earlier lists for duplicate names."""
        list1 = [Track(name="track1", content="original", trigger=None)]
        list2 = [Track(name="track1", content="override", trigger=None)]

        result = merge_tracks([list1, list2])

        assert len(result) == 1
        assert result[0].name == "track1"
        assert result[0].content == "override"

    def test_merge_preserves_precedence_order(self):
        """Test that precedence order is maintained (later overrides earlier)."""
        list1 = [Track(name="shared", content="first", trigger=None)]
        list2 = [Track(name="shared", content="second", trigger=None)]
        list3 = [Track(name="shared", content="third", trigger=None)]

        result = merge_tracks([list1, list2, list3])

        assert len(result) == 1
        assert result[0].content == "third"


class TestLoadOrgTracksFromUrl:
    """Tests for load_org_tracks_from_url function."""

    def test_load_org_tracks_git_clone_failure(self):
        """Test handling of git clone failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Git not found")

            result = load_org_tracks_from_url(
                org_repo_url="https://github.com/org/.handprint",
                org_name="test-org",
            )

            assert result == []

    def test_load_org_tracks_repo_not_found(self):
        """Test handling of repository not found."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=128,
                cmd=["git", "clone"],
            )

            result = load_org_tracks_from_url(
                org_repo_url="https://github.com/org/.handprint",
                org_name="test-org",
            )

            assert result == []

    def test_load_org_tracks_timeout(self):
        """Test handling of git clone timeout."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["git", "clone"],
                timeout=120,
            )

            result = load_org_tracks_from_url(
                org_repo_url="https://github.com/org/.handprint",
                org_name="test-org",
            )

            assert result == []

    def test_load_org_tracks_custom_working_dir(self):
        """Test using custom working directory."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    returncode=128,
                    cmd=["git", "clone"],
                )

                result = load_org_tracks_from_url(
                    org_repo_url="https://github.com/org/.handprint",
                    org_name="test-org",
                    working_dir=tmpdir,
                )

                assert result == []


class TestLoadAllTracks:
    """Tests for load_all_tracks function."""

    _PATCH_TARGET = "handprint.agent_server.tracks_service.load_available_tracks"

    def test_load_all_tracks_registered_marketplaces_keep_legacy_public(
        self, tmp_path: Path
    ):
        marketplace_dir = _create_test_marketplace(tmp_path / "marketplace")
        public_track = Track(name="public-track", content="public", trigger=None)
        user_track = Track(name="user-track", content="user", trigger=None)

        with patch(
            self._PATCH_TARGET,
            side_effect=[
                {"public-track": public_track, "user-track": user_track},
                {},
            ],
        ) as mock_avail:
            result = load_all_tracks(
                load_public=True,
                load_user=True,
                load_project=False,
                load_org=False,
                registered_marketplaces=[
                    MarketplaceRegistration(
                        name="test",
                        source=str(marketplace_dir),
                        auto_load=True,
                    )
                ],
            )

        track_names = {track.name for track in result.tracks}
        assert "auto-track" in track_names
        assert "manual-track" in track_names
        assert "public-track" in track_names
        assert "user-track" in track_names
        assert result.sources["registered_marketplaces"] == 2
        assert result.sources["sdk_base"] == 2
        assert mock_avail.call_args_list[0].kwargs["include_public"] is True

    def test_load_all_tracks_non_auto_registered_marketplaces_keep_legacy_public(
        self, tmp_path: Path
    ):
        marketplace_dir = _create_test_marketplace(tmp_path / "marketplace")
        public_track = Track(name="public-track", content="public", trigger=None)

        with patch(
            self._PATCH_TARGET, side_effect=[{"public-track": public_track}, {}]
        ) as mock_avail:
            result = load_all_tracks(
                load_public=True,
                load_user=False,
                load_project=False,
                load_org=False,
                registered_marketplaces=[
                    MarketplaceRegistration(name="manual", source=str(marketplace_dir))
                ],
            )

        assert [track.name for track in result.tracks] == ["public-track"]
        assert result.sources["registered_marketplaces"] == 0
        assert mock_avail.call_args_list[0].kwargs["include_public"] is True

    def test_load_registered_marketplace_tracks_uses_auto_load_registrations(
        self, tmp_path: Path
    ):
        """Only registrations marked auto_load=True contribute plugin tracks."""
        marketplace_dir = _create_test_marketplace(tmp_path / "marketplace")

        tracks = load_registered_marketplace_tracks(
            [
                MarketplaceRegistration(
                    name="test",
                    source=str(marketplace_dir),
                    auto_load=True,
                ),
                MarketplaceRegistration(name="manual", source=str(marketplace_dir)),
            ]
        )

        assert {track.name for track in tracks} == {"auto-track", "manual-track"}

    def test_load_registered_marketplace_tracks_selects_listed_plugins(
        self, tmp_path: Path
    ):
        marketplace_dir = _create_test_marketplace(tmp_path / "marketplace")

        tracks = load_registered_marketplace_tracks(
            [
                MarketplaceRegistration(
                    name="test",
                    source=str(marketplace_dir),
                    auto_load=["manual"],
                )
            ]
        )

        assert [track.name for track in tracks] == ["manual-track"]

    def test_load_registered_marketplace_tracks_loads_standalone_tracks(
        self, tmp_path: Path
    ):
        """auto_load=True loads standalone tracks, not just plugins."""
        marketplace_dir = _create_tracks_only_marketplace(tmp_path / "marketplace")

        tracks = load_registered_marketplace_tracks(
            [
                MarketplaceRegistration(
                    name="tracks-only",
                    source=str(marketplace_dir),
                    auto_load=True,
                )
            ]
        )

        assert {track.name for track in tracks} == {"greet", "commit"}

    def test_load_registered_marketplace_tracks_selects_listed_standalone_tracks(
        self, tmp_path: Path
    ):
        """A name list selects standalone tracks the same way it selects plugins."""
        marketplace_dir = _create_tracks_only_marketplace(tmp_path / "marketplace")

        tracks = load_registered_marketplace_tracks(
            [
                MarketplaceRegistration(
                    name="tracks-only",
                    source=str(marketplace_dir),
                    auto_load=["greet"],
                )
            ]
        )

        assert [track.name for track in tracks] == ["greet"]

    def test_load_registered_marketplace_tracks_skips_standalone_when_not_auto_load(
        self, tmp_path: Path
    ):
        """A tracks-only marketplace without auto_load contributes nothing."""
        marketplace_dir = _create_tracks_only_marketplace(tmp_path / "marketplace")

        tracks = load_registered_marketplace_tracks(
            [MarketplaceRegistration(name="tracks-only", source=str(marketplace_dir))]
        )

        assert tracks == []

    def test_load_registered_marketplace_tracks_loads_plugins_and_standalone(
        self, tmp_path: Path
    ):
        """A marketplace with both plugins and standalone tracks loads both."""
        marketplace_dir = tmp_path / "marketplace"
        _create_test_plugin(marketplace_dir / "plugins" / "auto", "auto", "auto-track")
        _create_standalone_track(marketplace_dir / "tracks" / "greet", "greet")
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "mixed-marketplace",
                    "owner": {"name": "Test Team"},
                    "plugins": [{"name": "auto", "source": "./plugins/auto"}],
                    "tracks": [{"name": "greet", "source": "./tracks/greet"}],
                }
            )
        )

        tracks = load_registered_marketplace_tracks(
            [
                MarketplaceRegistration(
                    name="mixed", source=str(marketplace_dir), auto_load=True
                )
            ]
        )

        assert {track.name for track in tracks} == {"auto-track", "greet"}

    def test_plugin_wins_over_standalone_on_name_collision(self, tmp_path: Path):
        """A plugin track overrides a same-named standalone track (catalog rule)."""
        marketplace_dir = tmp_path / "marketplace"
        # Plugin 'p' bundles a track named 'shared'.
        plugin_dir = marketplace_dir / "plugins" / "p"
        (plugin_dir / ".plugin").mkdir(parents=True)
        (plugin_dir / ".plugin" / "plugin.json").write_text(
            json.dumps({"name": "p", "version": "1.0.0"})
        )
        (plugin_dir / "tracks").mkdir()
        (plugin_dir / "tracks" / "shared.md").write_text(
            "---\nname: shared\n---\nFROM_PLUGIN"
        )
        # Standalone track also named 'shared'.
        standalone = marketplace_dir / "tracks" / "shared"
        standalone.mkdir(parents=True)
        (standalone / "TRACK.md").write_text(
            "---\nname: shared\ndescription: d\n---\nFROM_STANDALONE"
        )
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "collision",
                    "owner": {"name": "Test Team"},
                    "plugins": [{"name": "p", "source": "./plugins/p"}],
                    "tracks": [{"name": "shared", "source": "./tracks/shared"}],
                }
            )
        )

        # Marketplace auto-load is gated on load_public; the patch keeps the
        # public tier empty so only the marketplace contributes 'shared'.
        with patch(self._PATCH_TARGET, return_value={}):
            result = load_all_tracks(
                load_public=True,
                load_user=False,
                load_project=False,
                load_org=False,
                registered_marketplaces=[
                    MarketplaceRegistration(
                        name="collision", source=str(marketplace_dir), auto_load=True
                    )
                ],
            )

        shared = [s for s in result.tracks if s.name == "shared"]
        assert len(shared) == 1
        assert "FROM_PLUGIN" in shared[0].content
        assert "FROM_STANDALONE" not in shared[0].content

    def test_load_registered_marketplace_tracks_uses_registration_fetch_fields(
        self, tmp_path: Path
    ):
        """Marketplace source, ref, and repo_path drive registry fetching."""
        marketplace_dir = _create_test_marketplace(tmp_path / "marketplace")

        with patch(
            "handprint.sdk.marketplace.registry.fetch_plugin_with_resolution",
            return_value=(marketplace_dir, "abc123"),
        ) as mock_fetch:
            tracks = load_registered_marketplace_tracks(
                [
                    MarketplaceRegistration(
                        name="custom",
                        source="github:example/marketplaces",
                        ref="feature-branch",
                        repo_path="catalogs/public",
                        auto_load=True,
                    )
                ]
            )

        assert {track.name for track in tracks} == {"auto-track", "manual-track"}
        mock_fetch.assert_called_once_with(
            source="github:example/marketplaces",
            ref="feature-branch",
            repo_path="catalogs/public",
        )

    def test_load_all_tracks_returns_track_load_result(self):
        """Test that load_all_tracks returns a TrackLoadResult."""
        with patch(self._PATCH_TARGET, return_value={}):
            result = load_all_tracks(
                load_public=True,
                load_user=True,
                load_project=False,
                load_org=False,
            )

            assert isinstance(result, TrackLoadResult)
            assert isinstance(result.tracks, list)
            assert isinstance(result.sources, dict)

    def test_load_all_tracks_sources_tracking(self):
        """Test that source counts are tracked correctly."""
        track1 = Track(name="public1", content="c1", trigger=None)
        track2 = Track(name="user1", content="c2", trigger=None)

        # First call returns sdk_base (public+user), second returns project
        with patch(
            self._PATCH_TARGET,
            side_effect=[
                {"public1": track1, "user1": track2},  # sdk_base
                {},  # project
            ],
        ):
            result = load_all_tracks(
                load_public=True,
                load_user=True,
                load_project=False,
                load_org=False,
            )

            assert result.sources["sdk_base"] == 2
            assert result.sources["sandbox"] == 0
            assert result.sources["org"] == 0
            assert result.sources["project"] == 0
            assert result.sources["registered_marketplaces"] == 0

    def test_load_all_tracks_passes_marketplace_path_to_sdk_base(self):
        """Test that marketplace_path is forwarded to SDK public track loading."""
        with patch(self._PATCH_TARGET, side_effect=[{}, {}]) as mock_avail:
            load_all_tracks(
                load_public=True,
                load_user=True,
                load_project=False,
                load_org=False,
                marketplace_path="marketplaces/custom.json",
            )

        sdk_base_call = mock_avail.call_args_list[0]
        assert sdk_base_call.kwargs["include_public"] is True
        assert sdk_base_call.kwargs["marketplace_path"] == "marketplaces/custom.json"

        project_call = mock_avail.call_args_list[1]
        assert project_call.kwargs["include_public"] is False

    def test_load_all_tracks_disabled_sources(self):
        """Test that disabled sources are not loaded."""
        with patch(self._PATCH_TARGET, return_value={}) as mock_avail:
            result = load_all_tracks(
                load_public=False,
                load_user=False,
                load_project=False,
                load_org=False,
            )

            # Called twice (sdk_base + project), both with disabled flags
            assert mock_avail.call_count == 2
            assert result.sources["sdk_base"] == 0
            assert result.sources["project"] == 0

    def test_load_all_tracks_with_sandbox_urls(self):
        """Test loading tracks with sandbox URLs."""
        sandbox_urls = [
            ExposedUrlData(name="WORKER_8080", url="http://localhost:9080", port=9080),
        ]

        with patch(self._PATCH_TARGET, return_value={}):
            result = load_all_tracks(
                load_public=False,
                load_user=False,
                load_project=False,
                load_org=False,
                sandbox_exposed_urls=sandbox_urls,
            )

            assert result.sources["sandbox"] == 1
            assert len(result.tracks) == 1
            assert result.tracks[0].name == "work_hosts"

    def test_load_all_tracks_handles_exceptions(self):
        """Test that exceptions from track loaders are handled gracefully."""
        user_track = Track(name="user1", content="content", trigger=None)

        # load_available_tracks handles exceptions internally and returns
        # whatever it can. Simulate: first call returns user track only
        # (public failed internally), second call returns empty project.
        with patch(
            self._PATCH_TARGET,
            side_effect=[
                {"user1": user_track},  # sdk_base (public error handled inside)
                {},  # project
            ],
        ):
            result = load_all_tracks(
                load_public=True,
                load_user=True,
                load_project=False,
                load_org=False,
            )

            assert result.sources["sdk_base"] == 1

    def test_load_all_tracks_merge_precedence(self):
        """Test that tracks are merged with correct precedence."""
        base_track = Track(name="shared", content="user", trigger=None)
        project_track = Track(name="shared", content="project", trigger=None)

        # sdk_base returns user version, project returns project version
        with patch(
            self._PATCH_TARGET,
            side_effect=[
                {"shared": base_track},  # sdk_base
                {"shared": project_track},  # project
            ],
        ):
            result = load_all_tracks(
                load_public=True,
                load_user=True,
                load_project=True,
                load_org=False,
                project_dir="/workspace",
            )

            # Project should override user/public
            shared_tracks = [s for s in result.tracks if s.name == "shared"]
            assert len(shared_tracks) == 1
            assert shared_tracks[0].content == "project"

    def test_load_all_tracks_loops_and_merges_multiple_org_repos(self):
        """Every org repo is loaded (in order) and merged into the org source."""
        with patch(self._PATCH_TARGET, return_value={}):
            with patch(
                "handprint.agent_server.tracks_service.load_org_tracks_from_url",
                side_effect=[
                    [Track(name="org_a", content="a", trigger=None)],
                    [Track(name="org_b", content="b", trigger=None)],
                ],
            ) as mock_org:
                result = load_all_tracks(
                    load_public=False,
                    load_user=False,
                    load_project=False,
                    load_org=True,
                    org_repos=[
                        ("https://git/hieptl/.handprint", "hieptl"),
                        ("https://git/hieptl/.agents", "hieptl"),
                    ],
                )

        assert result.sources["org"] == 2
        assert [c.kwargs["org_repo_url"] for c in mock_org.call_args_list] == [
            "https://git/hieptl/.handprint",
            "https://git/hieptl/.agents",
        ]

    def test_load_all_tracks_org_merge_precedence(self):
        """A track in multiple org repos resolves to the later repo's version."""
        with patch(self._PATCH_TARGET, return_value={}):
            with patch(
                "handprint.agent_server.tracks_service.load_org_tracks_from_url",
                side_effect=[
                    [Track(name="shared", content="handprint", trigger=None)],
                    [Track(name="shared", content="agents", trigger=None)],
                ],
            ):
                result = load_all_tracks(
                    load_public=False,
                    load_user=False,
                    load_project=False,
                    load_org=True,
                    org_repos=[
                        ("https://git/hieptl/.handprint", "hieptl"),
                        ("https://git/hieptl/.agents", "hieptl"),
                    ],
                )

        shared = [s for s in result.tracks if s.name == "shared"]
        assert len(shared) == 1
        assert shared[0].content == "agents"


class TestDiscoverProfileTracks:
    """Tests for discover_profile_tracks (the Handprint profile launch catalog)."""

    _LOAD_ALL = "handprint.agent_server.tracks_service.load_all_tracks"

    def test_returns_merged_user_and_public_tracks(self):
        tracks = [Track(name="a", content="x"), Track(name="b", content="y")]
        with patch(self._LOAD_ALL) as mock_load:
            mock_load.return_value = TrackLoadResult(tracks=tracks, sources={})
            result = discover_profile_tracks()

        assert result == tracks
        # Only the deterministic, no-extra-context sources are discovered.
        assert mock_load.call_args.kwargs == {
            "load_public": True,
            "load_user": True,
            "load_org": False,
            "load_project": False,
        }

    def test_propagates_unexpected_failure(self):
        # load_all_tracks absorbs benign per-source failures internally; an
        # unexpected failure propagates rather than silently resolving to a
        # zero-track agent (the caller surfaces it loudly).
        with patch(self._LOAD_ALL, side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                discover_profile_tracks()


class TestSyncPublicTracks:
    """Tests for sync_public_tracks function."""

    def test_sync_public_tracks_success(self):
        """Test successful track sync."""
        with (
            patch(
                "handprint.agent_server.tracks_service.get_tracks_cache_dir"
            ) as mock_cache,
            patch(
                "handprint.agent_server.tracks_service.update_tracks_repository"
            ) as mock_update,
        ):
            mock_cache.return_value = Path("/tmp/cache")
            mock_update.return_value = Path("/tmp/cache/public-tracks")

            success, message = sync_public_tracks()

            assert success is True
            assert "success" in message.lower()

    def test_sync_public_tracks_failure(self):
        """Test failed track sync."""
        with (
            patch(
                "handprint.agent_server.tracks_service.get_tracks_cache_dir"
            ) as mock_cache,
            patch(
                "handprint.agent_server.tracks_service.update_tracks_repository"
            ) as mock_update,
        ):
            mock_cache.return_value = Path("/tmp/cache")
            mock_update.return_value = None

            success, message = sync_public_tracks()

            assert success is False
            assert "failed" in message.lower()

    def test_sync_public_tracks_exception(self):
        """Test track sync with exception."""
        with patch(
            "handprint.agent_server.tracks_service.get_tracks_cache_dir"
        ) as mock_cache:
            mock_cache.side_effect = Exception("Permission denied")

            success, message = sync_public_tracks()

            assert success is False
            assert "failed" in message.lower() or "error" in message.lower()

    def test_sync_public_tracks_invalidates_in_memory_cache(self):
        """Successful sync must drop the in-memory cache so the next call
        re-parses immediately instead of waiting for the TTL."""
        with (
            patch(
                "handprint.agent_server.tracks_service.get_tracks_cache_dir"
            ) as mock_cache,
            patch(
                "handprint.agent_server.tracks_service.update_tracks_repository"
            ) as mock_update,
            patch(
                "handprint.agent_server.tracks_service._invalidate_public_tracks_cache"
            ) as mock_invalidate,
        ):
            mock_cache.return_value = Path("/tmp/cache")
            mock_update.return_value = Path("/tmp/cache/public-tracks")

            success, _ = sync_public_tracks()

            assert success is True
            mock_invalidate.assert_called_once()

    def test_sync_public_tracks_failure_does_not_invalidate_cache(self):
        """A failed sync must not clobber the cache so the previous tracks
        stay available until the next successful refresh."""
        with (
            patch(
                "handprint.agent_server.tracks_service.get_tracks_cache_dir"
            ) as mock_cache,
            patch(
                "handprint.agent_server.tracks_service.update_tracks_repository"
            ) as mock_update,
            patch(
                "handprint.agent_server.tracks_service._invalidate_public_tracks_cache"
            ) as mock_invalidate,
        ):
            mock_cache.return_value = Path("/tmp/cache")
            mock_update.return_value = None

            success, _ = sync_public_tracks()

            assert success is False
            mock_invalidate.assert_not_called()


class TestTrackLoadResult:
    """Tests for TrackLoadResult dataclass."""

    def test_track_load_result_creation(self):
        """Test creating TrackLoadResult instance."""
        tracks = [Track(name="test", content="content", trigger=None)]
        sources = {"public": 1, "user": 0}

        result = TrackLoadResult(tracks=tracks, sources=sources)

        assert result.tracks == tracks
        assert result.sources == sources

    def test_track_load_result_empty(self):
        """Test creating empty TrackLoadResult."""
        result = TrackLoadResult(tracks=[], sources={})

        assert result.tracks == []
        assert result.sources == {}


class TestMarketplaceCatalogCache:
    """Tests for TTL caching in service_get_marketplace_catalog."""

    def setup_method(self):
        """Reset the module-level cache before each test."""
        import handprint.agent_server.tracks_service as svc

        svc._catalog_cache = None

    def test_cache_miss_calls_fetch(self):
        """First call (cold cache) fetches from the repository."""
        entries = [("github", "GitHub track", "github:org/repo")]
        with (
            patch(
                "handprint.agent_server.tracks_service._fetch_catalog_entries",
                return_value=entries,
            ) as mock_fetch,
            patch(
                "handprint.agent_server.tracks_service.service_list_installed_tracks",
                return_value=[],
            ),
        ):
            from handprint.agent_server.tracks_service import (
                service_get_marketplace_catalog,
            )

            result = service_get_marketplace_catalog()

        mock_fetch.assert_called_once()
        assert len(result) == 1
        assert result[0].name == "github"
        assert result[0].installed is False

    def test_cache_hit_skips_fetch(self):
        """Second call within TTL reuses cached entries without another fetch."""
        entries = [("github", "GitHub track", "github:org/repo")]
        with (
            patch(
                "handprint.agent_server.tracks_service._fetch_catalog_entries",
                return_value=entries,
            ) as mock_fetch,
            patch(
                "handprint.agent_server.tracks_service.service_list_installed_tracks",
                return_value=[],
            ),
        ):
            from handprint.agent_server.tracks_service import (
                service_get_marketplace_catalog,
            )

            service_get_marketplace_catalog()
            service_get_marketplace_catalog()

        mock_fetch.assert_called_once()  # only one fetch despite two calls

    def test_installed_status_always_fresh(self):
        """installed flag is derived fresh on every call, not from the cache."""
        from unittest.mock import MagicMock

        from handprint.agent_server.tracks_service import (
            InstalledTrackInfo,
            service_get_marketplace_catalog,
        )

        entries = [("github", "GitHub track", "github:org/repo")]
        installed_track = MagicMock(spec=InstalledTrackInfo)
        installed_track.name = "github"

        with (
            patch(
                "handprint.agent_server.tracks_service._fetch_catalog_entries",
                return_value=entries,
            ),
            patch(
                "handprint.agent_server.tracks_service.service_list_installed_tracks",
            ) as mock_installed,
        ):
            # First call: track not installed
            mock_installed.return_value = []
            result1 = service_get_marketplace_catalog()
            assert result1[0].installed is False

            # Second call (cache hit): track now installed
            mock_installed.return_value = [installed_track]
            result2 = service_get_marketplace_catalog()
            assert result2[0].installed is True

        # service_list_installed_tracks called twice (once per request)
        assert mock_installed.call_count == 2

    def test_cache_expires_after_ttl(self):
        """After TTL expires, the next call fetches from the repository again."""
        import handprint.agent_server.tracks_service as svc

        entries = [("github", "GitHub track", "github:org/repo")]
        with (
            patch(
                "handprint.agent_server.tracks_service._fetch_catalog_entries",
                return_value=entries,
            ) as mock_fetch,
            patch(
                "handprint.agent_server.tracks_service.service_list_installed_tracks",
                return_value=[],
            ),
        ):
            from handprint.agent_server.tracks_service import (
                service_get_marketplace_catalog,
            )

            service_get_marketplace_catalog()
            # Artificially expire the cache
            assert svc._catalog_cache is not None
            svc._catalog_cache = (
                svc._catalog_cache[0] - svc._CATALOG_TTL_SECONDS - 1,
                entries,
            )
            service_get_marketplace_catalog()

        assert mock_fetch.call_count == 2  # fetched again after expiry
