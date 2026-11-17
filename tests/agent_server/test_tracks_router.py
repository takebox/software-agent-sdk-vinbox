"""Tests for tracks router endpoints."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from handprint.agent_server.api import create_app
from handprint.agent_server.config import Config
from handprint.agent_server.tracks_service import MarketplaceTrackInfo, TrackLoadResult
from handprint.sdk.extensions.fetch import ExtensionFetchError
from handprint.sdk.marketplace.registration import MarketplaceRegistration
from handprint.sdk.tracks import (
    InstalledTrackInfo,
    KeywordTrigger,
    Track,
    TrackFetchError,
    TrackValidationError,
)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app without authentication."""
    config = Config(session_api_keys=[])  # Disable authentication
    return TestClient(create_app(config), raise_server_exceptions=False)


@pytest.fixture
def mock_installed_track_info():
    """Create a mock InstalledTrackInfo for testing."""
    return InstalledTrackInfo(
        name="test-track",
        version="1.0.0",
        description="A test track",
        enabled=True,
        source="github:owner/repo/tracks/test-track",
        resolved_ref="abc123",
        repo_path=None,
        installed_at="2024-01-01T00:00:00Z",
        install_path=Path("/home/user/.handprint/tracks/installed/test-track"),
    )


class TestGetTracksEndpoint:
    """Tests for POST /tracks endpoint."""

    def test_get_tracks_default_request(self, client):
        """Test default tracks request with all sources enabled."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(
                tracks=[
                    Track(name="test-track", content="content", trigger=None),
                ],
                sources={"public": 1, "user": 0, "project": 0, "org": 0, "sandbox": 0},
            )

            response = client.post("/api/tracks", json={})

            assert response.status_code == 200
            data = response.json()
            assert "tracks" in data
            assert "sources" in data
            assert len(data["tracks"]) == 1
            assert data["tracks"][0]["name"] == "test-track"

    def test_get_tracks_with_project_dir(self, client):
        """Test tracks request with project directory."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(tracks=[], sources={})

            response = client.post(
                "/api/tracks",
                json={
                    "project_dir": "/workspace/myproject",
                    "load_project": True,
                },
            )

            assert response.status_code == 200
            mock_load.assert_called_once()
            call_kwargs = mock_load.call_args[1]
            assert call_kwargs["project_dir"] == "/workspace/myproject"
            assert call_kwargs["load_project"] is True

    def test_get_tracks_with_org_configs_list(self, client):
        """Multiple org_configs are forwarded as an ordered list of (url, name)."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(tracks=[], sources={})

            response = client.post(
                "/api/tracks",
                json={
                    "load_org": True,
                    "org_configs": [
                        {
                            "repository": "hieptl/.handprint",
                            "provider": "github",
                            "org_repo_url": "https://github.com/hieptl/.handprint",
                            "org_name": "hieptl",
                        },
                        {
                            "repository": "hieptl/.agents",
                            "provider": "github",
                            "org_repo_url": "https://github.com/hieptl/.agents",
                            "org_name": "hieptl",
                        },
                    ],
                },
            )

            assert response.status_code == 200
            mock_load.assert_called_once()
            assert mock_load.call_args[1]["org_repos"] == [
                ("https://github.com/hieptl/.handprint", "hieptl"),
                ("https://github.com/hieptl/.agents", "hieptl"),
            ]

    def test_get_tracks_with_registered_marketplaces(self, client):
        """Registered marketplaces are forwarded to the tracks service."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(tracks=[], sources={})

            response = client.post(
                "/api/tracks",
                json={
                    "registered_marketplaces": [
                        {
                            "name": "team",
                            "source": "https://github.com/org/marketplace",
                            "ref": "main",
                            "repo_path": "marketplace",
                            "auto_load": True,
                        }
                    ]
                },
            )

            assert response.status_code == 200
            registrations = mock_load.call_args[1]["registered_marketplaces"]
            assert len(registrations) == 1
            assert registrations[0].name == "team"
            assert registrations[0].source == "https://github.com/org/marketplace"
            assert registrations[0].ref == "main"
            assert registrations[0].repo_path == "marketplace"
            assert registrations[0].auto_load is True

    def test_get_tracks_with_selective_auto_load_marketplace(self, client):
        """Registered marketplaces accept selective auto_load plugin lists."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(tracks=[], sources={})

            response = client.post(
                "/api/tracks",
                json={
                    "registered_marketplaces": [
                        {
                            "name": "team",
                            "source": "https://github.com/org/marketplace",
                            "auto_load": ["formatter", "linter"],
                        }
                    ]
                },
            )

            assert response.status_code == 200
            registrations = mock_load.call_args[1]["registered_marketplaces"]
            assert len(registrations) == 1
            assert registrations[0].auto_load == ["formatter", "linter"]

    def test_get_tracks_merges_server_registered_marketplaces(self):
        """Server default marketplaces are included with request marketplaces."""
        config = Config(
            session_api_keys=[],
            registered_marketplaces=[
                MarketplaceRegistration(
                    name="default",
                    source="https://github.com/org/default-marketplace",
                    auto_load=True,
                )
            ],
        )
        client = TestClient(create_app(config), raise_server_exceptions=False)
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(tracks=[], sources={})

            response = client.post(
                "/api/tracks",
                json={
                    "registered_marketplaces": [
                        {
                            "name": "team",
                            "source": "https://github.com/org/team-marketplace",
                        }
                    ]
                },
            )

        assert response.status_code == 200
        registrations = mock_load.call_args[1]["registered_marketplaces"]
        assert [registration.name for registration in registrations] == [
            "default",
            "team",
        ]

    def test_get_tracks_server_manual_marketplace_keeps_public_tracks(self):
        config = Config(
            session_api_keys=[],
            registered_marketplaces=[
                MarketplaceRegistration(
                    name="manual",
                    source="https://github.com/org/manual-marketplace",
                )
            ],
        )
        client = TestClient(create_app(config), raise_server_exceptions=False)
        public_track = Track(name="public-track", content="public", trigger=None)

        with patch(
            "handprint.agent_server.tracks_service.load_available_tracks",
            side_effect=[{"public-track": public_track}, {}],
        ) as mock_load_available:
            response = client.post(
                "/api/tracks",
                json={
                    "load_user": False,
                    "load_project": False,
                    "load_org": False,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert [track["name"] for track in data["tracks"]] == ["public-track"]
        assert data["sources"]["registered_marketplaces"] == 0
        assert data["sources"]["sdk_base"] == 1
        assert mock_load_available.call_args_list[0].kwargs["include_public"] is True

    def test_get_tracks_request_marketplace_overrides_server_default(self):
        """Request registrations override same-named server defaults."""
        config = Config(
            session_api_keys=[],
            registered_marketplaces=[
                MarketplaceRegistration(
                    name="team",
                    source="https://github.com/org/default-marketplace",
                )
            ],
        )
        client = TestClient(create_app(config), raise_server_exceptions=False)
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(tracks=[], sources={})

            response = client.post(
                "/api/tracks",
                json={
                    "registered_marketplaces": [
                        {
                            "name": "team",
                            "source": "https://github.com/org/request-marketplace",
                        }
                    ]
                },
            )

        assert response.status_code == 200
        registrations = mock_load.call_args[1]["registered_marketplaces"]
        assert len(registrations) == 1
        assert registrations[0].source == "https://github.com/org/request-marketplace"

    def test_get_tracks_with_sandbox_config(self, client):
        """Test tracks request with sandbox configuration."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(
                tracks=[Track(name="work_hosts", content="host info", trigger=None)],
                sources={"sandbox": 1},
            )

            response = client.post(
                "/api/tracks",
                json={
                    "sandbox_config": {
                        "exposed_urls": [
                            {
                                "name": "WORKER_8080",
                                "url": "http://localhost:9080",
                                "port": 8080,
                            }
                        ]
                    }
                },
            )

            assert response.status_code == 200
            mock_load.assert_called_once()
            call_kwargs = mock_load.call_args[1]
            assert call_kwargs["sandbox_exposed_urls"] is not None
            assert len(call_kwargs["sandbox_exposed_urls"]) == 1
            assert call_kwargs["sandbox_exposed_urls"][0].name == "WORKER_8080"

    def test_get_tracks_disabled_sources(self, client):
        """Test tracks request with sources disabled."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(tracks=[], sources={})

            response = client.post(
                "/api/tracks",
                json={
                    "load_public": False,
                    "load_user": False,
                    "load_project": False,
                    "load_org": False,
                },
            )

            assert response.status_code == 200
            mock_load.assert_called_once()
            call_kwargs = mock_load.call_args[1]
            assert call_kwargs["load_public"] is False
            assert call_kwargs["load_user"] is False
            assert call_kwargs["load_project"] is False
            assert call_kwargs["load_org"] is False

    def test_get_tracks_converts_track_to_track_info(self, client):
        """Test that Track objects are properly converted to TrackInfo format."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(
                tracks=[
                    Track(
                        name="knowledge-track",
                        content="knowledge content",
                        trigger=KeywordTrigger(keywords=["python", "coding"]),
                        source="/path/to/track.md",
                        description="A knowledge track",
                    ),
                ],
                sources={"public": 1},
            )

            response = client.post("/api/tracks", json={})

            assert response.status_code == 200
            data = response.json()
            track_info = data["tracks"][0]
            assert track_info["name"] == "knowledge-track"
            assert track_info["type"] == "knowledge"
            assert track_info["content"] == "knowledge content"
            assert track_info["triggers"] == ["python", "coding"]
            assert track_info["source"] == "/path/to/track.md"
            assert track_info["description"] == "A knowledge track"
            assert track_info["is_agenttracks_format"] is False

    def test_get_tracks_agent_track_format(self, client):
        """Test that AgentTracks format is correctly represented."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(
                tracks=[
                    Track(
                        name="agent-track",
                        content="agent content",
                        trigger=None,
                        is_agenttracks_format=True,
                        disable_model_invocation=True,
                    ),
                ],
                sources={"public": 1},
            )

            response = client.post("/api/tracks", json={})

            assert response.status_code == 200
            data = response.json()
            track_info = data["tracks"][0]
            assert track_info["type"] == "agenttracks"
            assert track_info["is_agenttracks_format"] is True
            assert track_info["disable_model_invocation"] is True

    def test_get_tracks_response_sources(self, client):
        """Test that source counts are included in response."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(
                tracks=[],
                sources={
                    "public": 10,
                    "user": 5,
                    "project": 3,
                    "org": 2,
                    "sandbox": 1,
                },
            )

            response = client.post("/api/tracks", json={})

            assert response.status_code == 200
            data = response.json()
            assert data["sources"]["public"] == 10
            assert data["sources"]["user"] == 5
            assert data["sources"]["project"] == 3
            assert data["sources"]["org"] == 2
            assert data["sources"]["sandbox"] == 1


class TestSyncTracksEndpoint:
    """Tests for POST /tracks/sync endpoint."""

    def test_sync_tracks_success(self, client):
        """Test successful tracks sync."""
        with patch(
            "handprint.agent_server.tracks_router.sync_public_tracks"
        ) as mock_sync:
            mock_sync.return_value = (True, "Tracks synced successfully")

            response = client.post("/api/tracks/sync")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "synced" in data["message"].lower()

    def test_sync_tracks_failure(self, client):
        """Test failed tracks sync."""
        with patch(
            "handprint.agent_server.tracks_router.sync_public_tracks"
        ) as mock_sync:
            mock_sync.return_value = (False, "Network error occurred")

            response = client.post("/api/tracks/sync")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            msg_lower = data["message"].lower()
            assert "error" in msg_lower or "network" in msg_lower


class TestPydanticModels:
    """Tests for Pydantic model validation."""

    def test_exposed_url_validation(self, client):
        """Test ExposedUrl model validation."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(tracks=[], sources={})

            # Valid exposed URL
            response = client.post(
                "/api/tracks",
                json={
                    "sandbox_config": {
                        "exposed_urls": [
                            {
                                "name": "WORKER_8080",
                                "url": "http://localhost:9080",
                                "port": 8080,
                            }
                        ]
                    }
                },
            )
            assert response.status_code == 200

    def test_org_configs_validation(self, client):
        """Test OrgConfig model validation via the org_configs list."""
        with patch("handprint.agent_server.tracks_router.load_all_tracks") as mock_load:
            mock_load.return_value = TrackLoadResult(tracks=[], sources={})

            # Valid org config
            response = client.post(
                "/api/tracks",
                json={
                    "org_configs": [
                        {
                            "repository": "org/repo",
                            "provider": "github",
                            "org_repo_url": "https://github.com/org/.handprint",
                            "org_name": "org",
                        }
                    ]
                },
            )
            assert response.status_code == 200

    def test_invalid_request_body(self, client):
        """Test handling of invalid request body."""
        # Send invalid JSON structure
        response = client.post(
            "/api/tracks",
            json={"load_public": "not_a_boolean"},
        )
        # FastAPI returns 422 for validation errors
        assert response.status_code == 422

    def test_missing_required_org_configs_fields(self, client):
        """Test validation when an org_configs entry is missing required fields."""
        response = client.post(
            "/api/tracks",
            json={
                "org_configs": [
                    {
                        "repository": "org/repo",
                        # Missing provider, org_repo_url, org_name
                    }
                ]
            },
        )
        assert response.status_code == 422


class TestInstallTrackEndpoint:
    """Tests for POST /tracks/install endpoint."""

    def test_install_track_success(self, client, mock_installed_track_info):
        """Test successful track installation."""
        with patch(
            "handprint.agent_server.tracks_router.service_install_track"
        ) as mock_install:
            mock_install.return_value = mock_installed_track_info

            response = client.post(
                "/api/tracks/install",
                json={"source": "github:owner/repo/tracks/test-track"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test-track"
            assert data["source"] == "github:owner/repo/tracks/test-track"
            assert data["enabled"] is True

    def test_install_track_with_force(self, client, mock_installed_track_info):
        """Test track installation with force option."""
        with patch(
            "handprint.agent_server.tracks_router.service_install_track"
        ) as mock_install:
            mock_install.return_value = mock_installed_track_info

            response = client.post(
                "/api/tracks/install",
                json={
                    "source": "github:owner/repo/tracks/test-track",
                    "force": True,
                },
            )

            assert response.status_code == 200
            mock_install.assert_called_once()
            call_kwargs = mock_install.call_args[1]
            assert call_kwargs["force"] is True

    def test_install_track_with_ref(self, client, mock_installed_track_info):
        """Test track installation with specific ref."""
        with patch(
            "handprint.agent_server.tracks_router.service_install_track"
        ) as mock_install:
            mock_install.return_value = mock_installed_track_info

            response = client.post(
                "/api/tracks/install",
                json={
                    "source": "github:owner/repo",
                    "ref": "v1.0.0",
                    "repo_path": "tracks/test-track",
                },
            )

            assert response.status_code == 200
            mock_install.assert_called_once()
            call_kwargs = mock_install.call_args[1]
            assert call_kwargs["ref"] == "v1.0.0"
            assert call_kwargs["repo_path"] == "tracks/test-track"

    def test_install_track_already_exists(self, client):
        """Test track installation when track already exists."""
        with patch(
            "handprint.agent_server.tracks_router.service_install_track"
        ) as mock_install:
            mock_install.side_effect = FileExistsError("Track already exists")

            response = client.post(
                "/api/tracks/install",
                json={"source": "github:owner/repo/tracks/test-track"},
            )

            assert response.status_code == 409
            assert "already installed" in response.json()["detail"].lower()

    def test_install_track_fetch_error(self, client):
        """Test track installation with fetch error."""
        with patch(
            "handprint.agent_server.tracks_router.service_install_track"
        ) as mock_install:
            mock_install.side_effect = TrackFetchError("Network error")

            response = client.post(
                "/api/tracks/install",
                json={"source": "github:owner/repo/tracks/test-track"},
            )

            assert response.status_code == 400
            assert "fetch" in response.json()["detail"].lower()

    def test_install_track_extension_fetch_error(self, client):
        """ExtensionFetchError (raised by the SDK for GitHub URL/shorthand failures)
        must map to 400, not 500."""
        with patch(
            "handprint.agent_server.tracks_router.service_install_track"
        ) as mock_install:
            mock_install.side_effect = ExtensionFetchError(
                "Could not fetch from GitHub"
            )

            response = client.post(
                "/api/tracks/install",
                json={"source": "https://github.com/Owner/repo/tree/main/path"},
            )

            assert response.status_code == 400
            assert "fetch" in response.json()["detail"].lower()

    def test_install_track_validation_error(self, client):
        """Test track installation with validation error."""
        with patch(
            "handprint.agent_server.tracks_router.service_install_track"
        ) as mock_install:
            mock_install.side_effect = TrackValidationError("Missing TRACK.md")

            response = client.post(
                "/api/tracks/install",
                json={"source": "/path/to/invalid-track"},
            )

            assert response.status_code == 422
            assert "invalid" in response.json()["detail"].lower()


class TestListInstalledTracksEndpoint:
    """Tests for GET /tracks/installed endpoint."""

    def test_list_installed_tracks_empty(self, client):
        """Test listing when no tracks are installed."""
        with patch(
            "handprint.agent_server.tracks_router.service_list_installed_tracks"
        ) as mock_list:
            mock_list.return_value = []

            response = client.get("/api/tracks/installed")

            assert response.status_code == 200
            data = response.json()
            assert data["tracks"] == []

    def test_list_installed_tracks_with_tracks(self, client, mock_installed_track_info):
        """Test listing installed tracks."""
        with patch(
            "handprint.agent_server.tracks_router.service_list_installed_tracks"
        ) as mock_list:
            mock_list.return_value = [mock_installed_track_info]

            response = client.get("/api/tracks/installed")

            assert response.status_code == 200
            data = response.json()
            assert len(data["tracks"]) == 1
            assert data["tracks"][0]["name"] == "test-track"


class TestGetInstalledTrackEndpoint:
    """Tests for GET /tracks/installed/{track_name} endpoint."""

    def test_get_installed_track_found(self, client, mock_installed_track_info):
        """Test getting an installed track that exists."""
        with patch(
            "handprint.agent_server.tracks_router.service_get_installed_track"
        ) as mock_get:
            mock_get.return_value = mock_installed_track_info

            response = client.get("/api/tracks/installed/test-track")

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test-track"

    def test_get_installed_track_not_found(self, client):
        """Test getting a track that is not installed."""
        with patch(
            "handprint.agent_server.tracks_router.service_get_installed_track"
        ) as mock_get:
            mock_get.return_value = None

            response = client.get("/api/tracks/installed/nonexistent")

            assert response.status_code == 404
            assert "not installed" in response.json()["detail"].lower()


class TestUpdateTrackStateEndpoint:
    """Tests for PATCH /tracks/installed/{track_name} endpoint."""

    def test_enable_track_success(self, client):
        """Test enabling a track."""
        with patch(
            "handprint.agent_server.tracks_router.service_enable_track"
        ) as mock_enable:
            mock_enable.return_value = True

            response = client.patch(
                "/api/tracks/installed/test-track",
                json={"enabled": True},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test-track"
            assert data["enabled"] is True

    def test_disable_track_success(self, client):
        """Test disabling a track."""
        with patch(
            "handprint.agent_server.tracks_router.service_disable_track"
        ) as mock_disable:
            mock_disable.return_value = True

            response = client.patch(
                "/api/tracks/installed/test-track",
                json={"enabled": False},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["enabled"] is False

    def test_update_track_state_not_found(self, client):
        """Test updating state of non-existent track."""
        with patch(
            "handprint.agent_server.tracks_router.service_enable_track"
        ) as mock_enable:
            mock_enable.return_value = False

            response = client.patch(
                "/api/tracks/installed/nonexistent",
                json={"enabled": True},
            )

            assert response.status_code == 404


class TestUninstallTrackEndpoint:
    """Tests for DELETE /tracks/installed/{track_name} endpoint."""

    def test_uninstall_track_success(self, client):
        """Test successful track uninstallation."""
        with patch(
            "handprint.agent_server.tracks_router.service_uninstall_track"
        ) as mock_uninstall:
            mock_uninstall.return_value = True

            response = client.delete("/api/tracks/installed/test-track")

            assert response.status_code == 200
            data = response.json()
            assert "uninstalled" in data["message"].lower()

    def test_uninstall_track_not_found(self, client):
        """Test uninstalling a non-existent track."""
        with patch(
            "handprint.agent_server.tracks_router.service_uninstall_track"
        ) as mock_uninstall:
            mock_uninstall.return_value = False

            response = client.delete("/api/tracks/installed/nonexistent")

            assert response.status_code == 404


class TestRefreshTrackEndpoint:
    """Tests for POST /tracks/installed/{track_name}/refresh endpoint."""

    def test_refresh_track_success(self, client, mock_installed_track_info):
        """Test successful track refresh."""
        with patch(
            "handprint.agent_server.tracks_router.service_update_track"
        ) as mock_update:
            mock_update.return_value = mock_installed_track_info

            response = client.post("/api/tracks/installed/test-track/refresh")

            assert response.status_code == 200
            data = response.json()
            assert data["track"]["name"] == "test-track"

    def test_refresh_track_not_found(self, client):
        """Test refreshing a non-existent track."""
        with patch(
            "handprint.agent_server.tracks_router.service_update_track"
        ) as mock_update:
            mock_update.return_value = None

            response = client.post("/api/tracks/installed/nonexistent/refresh")

            assert response.status_code == 404


class TestMarketplaceCatalogEndpoint:
    """Tests for GET /tracks/marketplace endpoint."""

    def test_get_marketplace_catalog_empty(self, client):
        """Test getting marketplace when no tracks are available."""
        with patch(
            "handprint.agent_server.tracks_router.service_get_marketplace_catalog"
        ) as mock_catalog:
            mock_catalog.return_value = []

            response = client.get("/api/tracks/marketplace")

            assert response.status_code == 200
            data = response.json()
            assert data["tracks"] == []

    def test_get_marketplace_catalog_with_tracks(self, client):
        """Test getting marketplace with available tracks."""
        with patch(
            "handprint.agent_server.tracks_router.service_get_marketplace_catalog"
        ) as mock_catalog:
            mock_catalog.return_value = [
                MarketplaceTrackInfo(
                    name="github",
                    description="GitHub integration track",
                    source="github:HandPrint-AI/extensions/tracks/github",
                    installed=True,
                ),
                MarketplaceTrackInfo(
                    name="docker",
                    description="Docker management track",
                    source="github:HandPrint-AI/extensions/tracks/docker",
                    installed=False,
                ),
            ]

            response = client.get("/api/tracks/marketplace")

            assert response.status_code == 200
            data = response.json()
            assert len(data["tracks"]) == 2

            # Check first track
            assert data["tracks"][0]["name"] == "github"
            assert data["tracks"][0]["description"] == "GitHub integration track"
            assert data["tracks"][0]["installed"] is True

            # Check second track
            assert data["tracks"][1]["name"] == "docker"
            assert data["tracks"][1]["installed"] is False

    def test_get_marketplace_catalog_track_without_description(self, client):
        """Test marketplace track with no description."""
        with patch(
            "handprint.agent_server.tracks_router.service_get_marketplace_catalog"
        ) as mock_catalog:
            mock_catalog.return_value = [
                MarketplaceTrackInfo(
                    name="minimal-track",
                    description=None,
                    source="github:owner/repo",
                    installed=False,
                ),
            ]

            response = client.get("/api/tracks/marketplace")

            assert response.status_code == 200
            data = response.json()
            assert len(data["tracks"]) == 1
            assert data["tracks"][0]["description"] is None
