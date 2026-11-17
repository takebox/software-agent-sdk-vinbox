"""Viczin Extensions router for Handprint Agent Server.

HTTP API endpoints for viczin extension operations. Business logic is
delegated to ``viczin_extensions/installed.py``; this module mirrors
``plugins_router.py`` / ``tracks_router.py`` and stays focused on HTTP
concerns: install / list / get / enable-disable / uninstall, plus serving
an installed extension's entrypoint bundle to the Viczin frontend.
"""

import asyncio
from typing import Annotated, Final

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from handprint.agent_server.viczin_extensions.backend import (
    BackendLogs,
    BackendRevisionRequest,
    BackendStatus,
    ViczinExtensionBackendManager,
)
from handprint.agent_server.viczin_extensions.bridge import AppBackendSessionStore
from handprint.agent_server.viczin_extensions.installed import (
    InstalledViczinExtensionInfo,
    disable_viczin_extension,
    enable_viczin_extension,
    get_viczin_extension_bundle_path,
    get_viczin_extension_icon_path,
    get_installed_viczin_extension,
    get_installed_viczin_extension_manifest,
    install_viczin_extension,
    list_installed_viczin_extensions,
    uninstall_viczin_extension,
)
from handprint.agent_server.viczin_extensions.manifest import (
    MANIFEST_FILENAME,
    ViczinExtensionManifest,
)
from handprint.sdk.extensions.fetch import ExtensionFetchError
from handprint.sdk.utils.redact import redact_url_credentials


viczin_extensions_router = APIRouter(
    prefix="/viczin-extensions", tags=["Viczin Extensions"]
)

# Matches the SDK's validate_extension_name() rule.
VICZIN_EXTENSION_NAME_PATTERN: Final[str] = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

ViczinExtensionNamePath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=255,
        pattern=VICZIN_EXTENSION_NAME_PATTERN,
        description="Viczin extension name (lowercase alphanumeric, hyphens)",
    ),
]


def _backend_manager(request: Request) -> ViczinExtensionBackendManager:
    manager = getattr(request.app.state, "viczin_extension_backend_manager", None)
    if manager is None:
        manager = ViczinExtensionBackendManager()
        request.app.state.viczin_extension_backend_manager = manager
    return manager


async def _revoke_and_stop_backend(
    request: Request, extension_name: str
) -> BackendStatus:
    session_store = getattr(request.app.state, "app_backend_session_store", None)
    if isinstance(session_store, AppBackendSessionStore):
        await session_store.revoke_app(extension_name)
    return await _backend_manager(request).stop(extension_name)


class InstallViczinExtensionRequest(BaseModel):
    """Request body for installing a viczin extension."""

    source: str = Field(
        min_length=1,
        description=(
            "Viczin extension source - git URL, GitHub shorthand, or local "
            "path. Examples: 'github:owner/repo', '/path/to/extension'"
        ),
    )
    ref: str | None = Field(
        default=None, description="Optional branch, tag, or commit to install"
    )
    repo_path: str | None = Field(
        default=None,
        description="Subdirectory path within the repository (for monorepos)",
    )
    force: bool = Field(
        default=False, description="If true, overwrite existing installation"
    )


class InstalledViczinExtensionResponse(BaseModel):
    """Response containing installed viczin extension information."""

    name: str = Field(description="Viczin extension name")
    version: str = Field(default="", description="Viczin extension version")
    description: str = Field(default="", description="Viczin extension description")
    enabled: bool = Field(
        default=False, description="Whether the viczin extension is enabled"
    )
    source: str = Field(description="Original source (e.g., 'github:owner/repo')")
    resolved_ref: str | None = Field(
        default=None, description="Resolved git commit SHA"
    )
    repo_path: str | None = Field(
        default=None, description="Subdirectory path within the repository"
    )
    installed_at: str = Field(description="ISO 8601 timestamp of installation")
    install_path: str = Field(description="Path where the extension is installed")
    manifest: ViczinExtensionManifest | None = Field(
        default=None,
        description=(
            "The extension's validated manifest (display_name, "
            "contributes.pages, ...). None if the installed manifest can "
            "no longer be read."
        ),
    )

    @classmethod
    def from_info(
        cls,
        info: InstalledViczinExtensionInfo,
        manifest: ViczinExtensionManifest | None,
    ) -> "InstalledViczinExtensionResponse":
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
            manifest=manifest,
        )


class InstalledViczinExtensionsListResponse(BaseModel):
    """Response containing the list of installed viczin extensions."""

    viczin_extensions: list[InstalledViczinExtensionResponse]


class UpdateViczinExtensionStateRequest(BaseModel):
    """Request body for updating viczin extension state (enable/disable)."""

    enabled: bool


class UpdateViczinExtensionStateResponse(BaseModel):
    """Response from a viczin extension state update."""

    name: str
    enabled: bool


class UninstallViczinExtensionResponse(BaseModel):
    """Response from a viczin extension uninstall."""

    message: str


@viczin_extensions_router.post(
    "/install",
    response_model=InstalledViczinExtensionResponse,
    responses={
        400: {"description": "Could not read viczin extension source"},
        409: {"description": "Viczin extension already installed (use force=true)"},
        422: {"description": "Invalid viczin extension (bad manifest, etc.)"},
    },
)
async def install_viczin_extension_endpoint(
    request: InstallViczinExtensionRequest,
    http_request: Request,
) -> InstalledViczinExtensionResponse:
    """Install a viczin extension from a git URL, GitHub shorthand, or local
    path.

    A fresh install always lands disabled, regardless of the request body --
    there is no ``enabled`` field to smuggle a different state through.
    """
    manager = _backend_manager(http_request)
    if request.force and manager.has_running_backends():
        raise HTTPException(
            status_code=409,
            detail="Stop running Viczin App backends before a forced install",
        )
    try:
        info = await asyncio.to_thread(
            install_viczin_extension,
            source=request.source,
            ref=request.ref,
            repo_path=request.repo_path,
            force=request.force,
        )
        manager.invalidate_approval(info.name)
        return InstalledViczinExtensionResponse.from_info(
            info, get_installed_viczin_extension_manifest(info.name)
        )
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail="Viczin extension already installed. Use force=true to overwrite.",
        )
    except ExtensionFetchError as e:
        # Pass the specific reason through -- which of source/ref/repo_path is
        # wrong is the whole diagnostic, and a generic message misattributes a
        # bad repo_path to the source. Redacted in case a URL carried a token.
        # Deliberately not worded "failed to fetch": the viczin client treats
        # that phrase as a network outage and hides the reason behind a
        # "Disconnected, check your network" toast.
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not read viczin extension source: "
                f"{redact_url_credentials(str(e))}"
            ),
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No {MANIFEST_FILENAME} found at the resolved location. "
                "Source plus Path must point at the extension's own "
                "directory, not the repository root."
            ),
        )
    except (ValidationError, ValueError, OSError):
        raise HTTPException(
            status_code=422,
            detail="Invalid viczin extension. Ensure the manifest is well-formed.",
        )


@viczin_extensions_router.get(
    "/installed", response_model=InstalledViczinExtensionsListResponse
)
def list_installed_viczin_extensions_endpoint() -> (
    InstalledViczinExtensionsListResponse
):
    """List all installed viczin extensions (enabled and disabled)."""
    infos = list_installed_viczin_extensions()
    return InstalledViczinExtensionsListResponse(
        viczin_extensions=[
            InstalledViczinExtensionResponse.from_info(
                i, get_installed_viczin_extension_manifest(i.name)
            )
            for i in infos
        ]
    )


@viczin_extensions_router.get(
    "/installed/{extension_name}",
    response_model=InstalledViczinExtensionResponse,
    responses={404: {"description": "Viczin extension not installed"}},
)
def get_installed_viczin_extension_endpoint(
    extension_name: ViczinExtensionNamePath,
) -> InstalledViczinExtensionResponse:
    """Get information about a specific installed viczin extension."""
    info = get_installed_viczin_extension(name=extension_name)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Viczin extension '{extension_name}' is not installed",
        )
    return InstalledViczinExtensionResponse.from_info(
        info, get_installed_viczin_extension_manifest(extension_name)
    )


@viczin_extensions_router.patch(
    "/installed/{extension_name}",
    response_model=UpdateViczinExtensionStateResponse,
    responses={404: {"description": "Viczin extension not installed"}},
)
async def set_viczin_extension_enabled_endpoint(
    extension_name: ViczinExtensionNamePath,
    request: UpdateViczinExtensionStateRequest,
    http_request: Request,
) -> UpdateViczinExtensionStateResponse:
    """Enable or disable an installed viczin extension."""
    if not request.enabled:
        await _revoke_and_stop_backend(http_request, extension_name)
    fn = enable_viczin_extension if request.enabled else disable_viczin_extension
    if not fn(name=extension_name):
        raise HTTPException(
            status_code=404,
            detail=f"Viczin extension '{extension_name}' is not installed",
        )
    return UpdateViczinExtensionStateResponse(
        name=extension_name, enabled=request.enabled
    )


@viczin_extensions_router.delete(
    "/installed/{extension_name}",
    response_model=UninstallViczinExtensionResponse,
    responses={404: {"description": "Viczin extension not installed"}},
)
async def uninstall_viczin_extension_endpoint(
    extension_name: ViczinExtensionNamePath,
    request: Request,
) -> UninstallViczinExtensionResponse:
    """Uninstall a viczin extension by name while retaining backend data."""
    await _revoke_and_stop_backend(request, extension_name)
    if not uninstall_viczin_extension(name=extension_name):
        raise HTTPException(
            status_code=404,
            detail=f"Viczin extension '{extension_name}' is not installed",
        )
    return UninstallViczinExtensionResponse(
        message=f"Viczin extension '{extension_name}' uninstalled"
    )


@viczin_extensions_router.get(
    "/installed/{extension_name}/backend",
    response_model=BackendStatus,
)
async def get_viczin_extension_backend_status_endpoint(
    extension_name: ViczinExtensionNamePath,
    request: Request,
) -> BackendStatus:
    """Probe the optional backend lifecycle state."""
    return await _backend_manager(request).status(extension_name)


@viczin_extensions_router.post(
    "/installed/{extension_name}/backend/prepare",
    response_model=BackendStatus,
    responses={409: {"description": "Revision or checksum approval conflict"}},
)
async def prepare_viczin_extension_backend_endpoint(
    extension_name: ViczinExtensionNamePath,
    body: BackendRevisionRequest,
    request: Request,
) -> BackendStatus:
    """Verify and prepare the immutable artifact for an exact revision."""
    try:
        return await _backend_manager(request).prepare(extension_name, body.revision)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@viczin_extensions_router.post(
    "/installed/{extension_name}/backend/start",
    response_model=BackendStatus,
    responses={409: {"description": "Revision is not prepared or cannot start"}},
)
async def start_viczin_extension_backend_endpoint(
    extension_name: ViczinExtensionNamePath,
    body: BackendRevisionRequest,
    request: Request,
) -> BackendStatus:
    """Start only a previously prepared exact backend revision."""
    try:
        return await _backend_manager(request).start(extension_name, body.revision)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@viczin_extensions_router.post(
    "/installed/{extension_name}/backend/stop",
    response_model=BackendStatus,
)
async def stop_viczin_extension_backend_endpoint(
    extension_name: ViczinExtensionNamePath,
    request: Request,
) -> BackendStatus:
    """Stop the backend's owned process group idempotently."""
    # Revoke app-scoped sessions too: a stopped backend must not stay reachable
    # through a cookie that outlives it.
    return await _revoke_and_stop_backend(request, extension_name)


@viczin_extensions_router.get(
    "/installed/{extension_name}/backend/logs",
    response_model=BackendLogs,
)
async def get_viczin_extension_backend_logs_endpoint(
    extension_name: ViczinExtensionNamePath,
    request: Request,
    limit_bytes: Annotated[int, Query(ge=1, le=256 * 1024)] = 64 * 1024,
) -> BackendLogs:
    """Return bounded combined stdout and stderr from the owned process."""
    return await _backend_manager(request).logs(extension_name, limit_bytes)


@viczin_extensions_router.delete(
    "/installed/{extension_name}/backend/data",
    response_model=BackendStatus,
    responses={409: {"description": "Backend must be stopped first"}},
)
async def delete_viczin_extension_backend_data_endpoint(
    extension_name: ViczinExtensionNamePath,
    request: Request,
) -> BackendStatus:
    """Delete mutable backend data separately from app uninstall."""
    try:
        return await _backend_manager(request).delete_data(extension_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@viczin_extensions_router.get(
    "/installed/{extension_name}/bundle",
    responses={404: {"description": "Viczin extension or bundle not found"}},
)
def get_viczin_extension_bundle_endpoint(
    extension_name: ViczinExtensionNamePath,
) -> FileResponse:
    """Serve an installed viczin extension's entrypoint bundle file.

    Entrypoint containment is re-validated against the live install path on
    every request, not just at install time -- see
    ``get_viczin_extension_bundle_path``. ``Cache-Control: no-cache`` forces
    revalidation on each request, so a client never keeps serving a bundle
    from before the extension's last refresh: the actual bytes are re-read
    from disk, and Starlette's file-stat-based ``ETag``/``Last-Modified``
    change the moment the on-disk revision does.
    """
    bundle_path = get_viczin_extension_bundle_path(name=extension_name)
    if bundle_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Viczin extension '{extension_name}' bundle not found",
        )
    return FileResponse(bundle_path, headers={"Cache-Control": "no-cache"})


@viczin_extensions_router.get(
    "/installed/{extension_name}/icon",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "image/svg+xml": {"schema": {"type": "string", "format": "binary"}}
            }
        },
        404: {"description": "Viczin extension or icon not found"},
    },
)
def get_viczin_extension_icon_endpoint(
    extension_name: ViczinExtensionNamePath,
) -> FileResponse:
    """Serve the SVG icon declared by an installed viczin extension's manifest.

    The path comes from the manifest, never the request. The CSP sandbox keeps
    a directly opened SVG from running scripts on the agent-server origin.
    """
    icon_path = get_viczin_extension_icon_path(name=extension_name)
    if icon_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Viczin extension '{extension_name}' icon not found",
        )
    return FileResponse(
        icon_path,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "no-cache",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; sandbox"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
