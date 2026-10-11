"""Tracks router for Handprint Agent Server.

This module defines the HTTP API endpoints for track operations.
Business logic is delegated to tracks_service.py.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, Field

from handprint.agent_server.tracks_service import (
    ExposedUrlData,
    MarketplaceTrackInfo,
    load_all_tracks,
    service_disable_track,
    service_enable_track,
    service_get_installed_track,
    service_get_marketplace_catalog,
    service_install_track,
    service_list_installed_tracks,
    service_uninstall_track,
    service_update_track,
    sync_public_tracks,
)
from handprint.sdk.extensions.fetch import ExtensionFetchError
from handprint.sdk.marketplace.registration import MarketplaceRegistration
from handprint.sdk.tracks import (
    InstalledTrackInfo,
    TrackFetchError,
    TrackInfo,
    TrackValidationError,
)
from handprint.sdk.tracks.track import DEFAULT_MARKETPLACE_PATH
from handprint.sdk.tracks.utils import TRACK_NAME_PATTERN


tracks_router = APIRouter(prefix="/tracks", tags=["Tracks"])

# Validated track name path parameter
# Prevents empty strings, path traversal, and invalid characters
TrackNamePath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=255,
        pattern=TRACK_NAME_PATTERN.pattern,
        description="Track name (lowercase alphanumeric, hyphens)",
    ),
]


class ExposedUrl(BaseModel):
    """Represents an exposed URL from the sandbox."""

    name: str
    url: str
    port: int


class OrgConfig(BaseModel):
    """Configuration for loading organization-level tracks."""

    repository: str = Field(description="Selected repository (e.g., 'owner/repo')")
    provider: str = Field(
        description="Git provider type: github, gitlab, azure, bitbucket"
    )
    org_repo_url: str = Field(
        description="Pre-authenticated Git URL for the organization repository. "
        "Contains sensitive credentials - handle with care and avoid logging."
    )
    org_name: str = Field(description="Organization name")


class SandboxConfig(BaseModel):
    """Configuration for loading sandbox-specific tracks."""

    exposed_urls: list[ExposedUrl] = Field(
        default_factory=list,
        description="List of exposed URLs from the sandbox",
    )


class TracksRequest(BaseModel):
    """Request body for loading tracks."""

    load_public: bool = Field(
        default=True, description="Load public tracks from Handprint/extensions repo"
    )
    load_user: bool = Field(
        default=True, description="Load user tracks from ~/.handprint/tracks/"
    )
    load_project: bool = Field(
        default=True, description="Load project tracks from workspace"
    )
    load_org: bool = Field(default=True, description="Load organization-level tracks")
    marketplace_path: str | None = Field(
        default=DEFAULT_MARKETPLACE_PATH,
        description=(
            "Relative marketplace JSON path for public tracks. "
            "Set to null to load all public tracks."
        ),
    )
    registered_marketplaces: list[MarketplaceRegistration] = Field(
        default_factory=list,
        description=(
            "Marketplace registrations for plugin-based track loading. Registrations "
            "with auto_load=True or a list of plugin names add their tracks to the "
            "public tracks."
        ),
    )

    project_dir: str | None = Field(
        default=None, description="Workspace directory path for project tracks"
    )
    org_configs: list[OrgConfig] | None = Field(
        default=None,
        description="Organization/user track repositories to load concurrently",
    )
    sandbox_config: SandboxConfig | None = Field(
        default=None, description="Sandbox tracks configuration"
    )


class TracksResponse(BaseModel):
    """Response containing all available tracks."""

    tracks: list[TrackInfo]
    sources: dict[str, int] = Field(
        default_factory=dict,
        description="Count of tracks loaded from each source",
    )


class SyncResponse(BaseModel):
    """Response from track sync operation."""

    status: Literal["success", "error"]
    message: str


# ---------------------------------------------------------------------------
# Installed Tracks Management Models
# ---------------------------------------------------------------------------


class InstallTrackRequest(BaseModel):
    """Request body for installing a track."""

    source: str = Field(
        min_length=1,
        description=(
            "Track source - git URL, GitHub shorthand, or local path. "
            "Examples: "
            "'https://github.com/takebox/extensions/tree/main/tracks/github', "
            "'github:Handprint/extensions/tracks/github', "
            "'/path/to/track'"
        ),
    )
    ref: str | None = Field(
        default=None,
        description="Optional branch, tag, or commit to install",
    )
    repo_path: str | None = Field(
        default=None,
        description="Subdirectory path within the repository (for monorepos)",
    )
    force: bool = Field(
        default=False,
        description="If true, overwrite existing installation",
    )


class InstalledTrackResponse(BaseModel):
    """Response containing installed track information."""

    name: str = Field(description="Track name")
    version: str = Field(default="", description="Track version")
    description: str = Field(default="", description="Track description")
    enabled: bool = Field(default=True, description="Whether the track is enabled")
    source: str = Field(description="Original source (e.g., 'github:owner/repo')")
    resolved_ref: str | None = Field(
        default=None, description="Resolved git commit SHA"
    )
    repo_path: str | None = Field(
        default=None, description="Subdirectory path within the repository"
    )
    installed_at: str = Field(description="ISO 8601 timestamp of installation")
    install_path: str = Field(description="Path where the track is installed")

    @classmethod
    def from_track_info(cls, info: InstalledTrackInfo) -> "InstalledTrackResponse":
        return cls(
            name=info.name,
            version=info.version,
            description=info.description,
            enabled=info.enabled,
            source=info.source,
            resolved_ref=info.resolved_ref,
            repo_path=info.repo_path,
            installed_at=info.installed_at,
            install_path=str(info.install_path),
        )


class InstalledTracksListResponse(BaseModel):
    """Response containing list of installed tracks."""

    tracks: list[InstalledTrackResponse]


class UpdateTrackStateRequest(BaseModel):
    """Request body for updating track state (enable/disable)."""

    enabled: bool


class UpdateTrackStateResponse(BaseModel):
    """Response from track state update operation."""

    name: str
    enabled: bool


class UninstallTrackResponse(BaseModel):
    """Response from track uninstall operation."""

    message: str


class UpdateTrackResponse(BaseModel):
    """Response from track update operation."""

    message: str
    track: InstalledTrackResponse


class MarketplaceCatalogResponse(BaseModel):
    """Response containing the marketplace catalog."""

    tracks: list[MarketplaceTrackInfo]


def _merge_registered_marketplaces(
    server_registrations: list[MarketplaceRegistration],
    request_registrations: list[MarketplaceRegistration],
) -> list[MarketplaceRegistration]:
    registrations_by_name = {
        registration.name: registration for registration in server_registrations
    }
    registrations_by_name.update(
        {registration.name: registration for registration in request_registrations}
    )
    return list(registrations_by_name.values())


@tracks_router.post("", response_model=TracksResponse)
def get_tracks(request: TracksRequest, http_request: Request) -> TracksResponse:
    """Load and merge tracks from all configured sources.

    Tracks are loaded from multiple sources and merged with the following
    precedence (later overrides earlier for duplicate names):
    1. Sandbox tracks (lowest) - Exposed URLs from sandbox
    2. Public tracks - From GitHub Handprint/extensions repository
    3. User tracks - From ~/.handprint/tracks/
    4. Organization tracks - From {org}/.handprint or equivalent
    5. Project tracks (highest) - From {workspace}/.handprint/tracks/

    Args:
        request: TracksRequest containing configuration for which sources to load.

    Returns:
        TracksResponse containing merged tracks and source counts.
    """
    # Convert Pydantic models to service data types
    sandbox_urls = None
    if request.sandbox_config and request.sandbox_config.exposed_urls:
        sandbox_urls = [
            ExposedUrlData(name=url.name, url=url.url, port=url.port)
            for url in request.sandbox_config.exposed_urls
        ]

    org_repos: list[tuple[str, str]] = []
    if request.org_configs:
        org_repos = [(c.org_repo_url, c.org_name) for c in request.org_configs]

    config = getattr(http_request.app.state, "config", None)
    server_registrations = config.registered_marketplaces if config is not None else []
    registered_marketplaces = _merge_registered_marketplaces(
        server_registrations,
        request.registered_marketplaces,
    )

    # Call the service
    result = load_all_tracks(
        load_public=request.load_public,
        load_user=request.load_user,
        load_project=request.load_project,
        load_org=request.load_org,
        project_dir=request.project_dir,
        org_repos=org_repos,
        sandbox_exposed_urls=sandbox_urls,
        marketplace_path=request.marketplace_path,
        registered_marketplaces=registered_marketplaces,
    )

    tracks_info = [track.to_track_info() for track in result.tracks]

    return TracksResponse(tracks=tracks_info, sources=result.sources)


@tracks_router.post("/sync", response_model=SyncResponse)
def sync_tracks() -> SyncResponse:
    """Force refresh of public tracks from GitHub repository.

    This triggers a git pull on the cached tracks repository to get
    the latest tracks from the Handprint/extensions repository.

    Returns:
        SyncResponse indicating success or failure.
    """
    success, message = sync_public_tracks()
    return SyncResponse(
        status="success" if success else "error",
        message=message,
    )


# ---------------------------------------------------------------------------
# Installed Tracks Management Endpoints
# ---------------------------------------------------------------------------


@tracks_router.post(
    "/install",
    response_model=InstalledTrackResponse,
    responses={
        400: {"description": "Failed to fetch track source"},
        409: {"description": "Track already installed (use force=true)"},
        422: {"description": "Invalid track (missing TRACK.md, etc.)"},
    },
)
def install_track_endpoint(request: InstallTrackRequest) -> InstalledTrackResponse:
    """Install a track from a source.

    Installs a track from a git URL, GitHub shorthand, or local path into
    the user's installed tracks directory (~/.handprint/tracks/installed/).

    Args:
        request: InstallTrackRequest containing source and options.

    Returns:
        InstalledTrackResponse with details about the installation.

    Raises:
        HTTPException 409: If track is already installed and force=False.
        HTTPException 400: If fetching the track source fails.
        HTTPException 422: If the track is invalid.
    """
    try:
        info = service_install_track(
            source=request.source,
            ref=request.ref,
            repo_path=request.repo_path,
            force=request.force,
        )
        return InstalledTrackResponse.from_track_info(info)
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail="Track already installed. Use force=true to overwrite.",
        )
    except (TrackFetchError, ExtensionFetchError):
        raise HTTPException(
            status_code=400,
            detail="Failed to fetch track source. Check that the source is valid.",
        )
    except TrackValidationError:
        raise HTTPException(
            status_code=422,
            detail="Invalid track. Ensure the source contains a valid TRACK.md.",
        )


@tracks_router.get("/installed", response_model=InstalledTracksListResponse)
def list_installed_tracks_endpoint() -> InstalledTracksListResponse:
    """List all installed tracks.

    Returns a list of all tracks installed in the user's installed tracks
    directory (~/.handprint/tracks/installed/).

    Returns:
        InstalledTracksListResponse containing list of installed tracks.
    """
    tracks = service_list_installed_tracks()
    return InstalledTracksListResponse(
        tracks=[InstalledTrackResponse.from_track_info(info) for info in tracks]
    )


@tracks_router.get(
    "/installed/{track_name}",
    response_model=InstalledTrackResponse,
    responses={404: {"description": "Track not installed"}},
)
def get_installed_track_endpoint(track_name: TrackNamePath) -> InstalledTrackResponse:
    """Get information about a specific installed track.

    Args:
        track_name: Name of the track to get.

    Returns:
        InstalledTrackResponse with track details.

    Raises:
        HTTPException 404: If the track is not installed.
    """
    info = service_get_installed_track(name=track_name)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Track '{track_name}' is not installed",
        )
    return InstalledTrackResponse.from_track_info(info)


@tracks_router.patch(
    "/installed/{track_name}",
    response_model=UpdateTrackStateResponse,
    responses={404: {"description": "Track not installed"}},
)
def set_track_enabled_endpoint(
    track_name: TrackNamePath, request: UpdateTrackStateRequest
) -> UpdateTrackStateResponse:
    """Enable or disable an installed track.

    Args:
        track_name: Name of the track to update.
        request: UpdateTrackStateRequest with enabled state.

    Returns:
        UpdateTrackStateResponse indicating new state.

    Raises:
        HTTPException 404: If the track is not installed.
    """
    fn = service_enable_track if request.enabled else service_disable_track
    if not fn(name=track_name):
        raise HTTPException(
            status_code=404,
            detail=f"Track '{track_name}' is not installed",
        )

    return UpdateTrackStateResponse(
        name=track_name,
        enabled=request.enabled,
    )


@tracks_router.delete(
    "/installed/{track_name}",
    response_model=UninstallTrackResponse,
    responses={404: {"description": "Track not installed"}},
)
def uninstall_track_endpoint(track_name: TrackNamePath) -> UninstallTrackResponse:
    """Uninstall a track by name.

    Removes a track from the user's installed tracks directory.

    Args:
        track_name: Name of the track to uninstall.

    Returns:
        UninstallTrackResponse with uninstall message.

    Raises:
        HTTPException 404: If the track is not installed.
    """
    success = service_uninstall_track(name=track_name)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Track '{track_name}' is not installed",
        )
    return UninstallTrackResponse(
        message=f"Track '{track_name}' uninstalled",
    )


@tracks_router.post(
    "/installed/{track_name}/refresh",
    response_model=UpdateTrackResponse,
    responses={404: {"description": "Track not installed"}},
)
def refresh_track_endpoint(track_name: TrackNamePath) -> UpdateTrackResponse:
    """Refresh an installed track to the latest version.

    Re-fetches the track from its original source and updates the installation.

    Args:
        track_name: Name of the track to refresh.

    Returns:
        UpdateTrackResponse with updated track information.

    Raises:
        HTTPException 404: If the track is not installed.
    """
    info = service_update_track(name=track_name)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Track '{track_name}' is not installed",
        )
    return UpdateTrackResponse(
        message=f"Track '{track_name}' updated",
        track=InstalledTrackResponse.from_track_info(info),
    )


@tracks_router.get("/marketplace", response_model=MarketplaceCatalogResponse)
def get_marketplace_catalog() -> MarketplaceCatalogResponse:
    """Get the marketplace catalog with installation status.

    Returns a list of available tracks from the Handprint extensions
    repository marketplace, along with their installation status.

    This enables frontend applications to display a "Marketplace" tab
    with installable tracks.

    Returns:
        MarketplaceCatalogResponse containing list of available tracks.
    """
    return MarketplaceCatalogResponse(tracks=service_get_marketplace_catalog())
