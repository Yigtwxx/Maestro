"""Plugin endpoints: browse and publish bundles, install and remove them.

Two switches guard this router, not one. ``PLUGINS_ENABLED`` is the feature;
``PLUGIN_EXTERNAL_IMPORT_ENABLED`` additionally allows ``/import``, because
fetching a manifest from a URL the caller names is a different trust story from
installing something Maestro's publish scan and moderation queue have seen. That
route carries the outbound-probe limit for the same reason MCP discovery does:
it leaves the building.

Uninstalling asks first. ``/uninstall-preview`` lists exactly what will be
deleted and flags anything the user edited after installing — deleting an agent
whose prompt someone rewrote is destructive in a way an "Uninstall" button does
not communicate on its own.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1._outbound import reject_private_host
from app.core.config import settings
from app.core.constants import (
    RATE_LIMIT_OUTBOUND_PROBE,
    RATE_LIMIT_READ,
    RATE_LIMIT_WRITE,
)
from app.core.deps import ActiveUser, VerifiedUser
from app.schemas.plugin import (
    PluginDetail,
    PluginImport,
    PluginInstallPublic,
    PluginPublic,
    PluginPublish,
    PluginUninstallPreview,
)
from app.services import plugin_service
from app.services.agent_service import AgentValidationError
from app.services.plugin_service import PluginSecurityError, PluginValidationError
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/plugins", tags=["plugins"])

_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="plugins")
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="plugins")
# An import fetches a URL the caller supplied. See RATE_LIMIT_OUTBOUND_PROBE.
_probe_rate_limit = rate_limit(RATE_LIMIT_OUTBOUND_PROBE, scope="plugins")


def _require_enabled() -> None:
    if not settings.plugins_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Plugins are disabled on this deployment.",
        )


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=list[PluginPublic], dependencies=[_read_rate_limit])
async def list_plugins(user: ActiveUser) -> list[dict]:
    """Browse published bundles. Never the author, never the manifest."""
    return await plugin_service.list_plugins()


@router.get(
    "/installed",
    response_model=list[PluginInstallPublic],
    dependencies=[_read_rate_limit],
)
async def list_installed(user: ActiveUser) -> list[dict]:
    """The caller's installed bundles, newest first."""
    return await plugin_service.list_installs(user.id)


@router.post(
    "",
    response_model=PluginPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_write_rate_limit],
)
async def publish_plugin(payload: PluginPublish, user: VerifiedUser) -> dict:
    """Publish a bundle. The security scan is never skipped."""
    _require_enabled()
    try:
        return await plugin_service.publish(user.id, payload.manifest)
    except PluginSecurityError as exc:
        raise _bad_request(exc) from exc


@router.get(
    "/{catalog_id}", response_model=PluginDetail, dependencies=[_read_rate_limit]
)
async def get_plugin(catalog_id: str, user: ActiveUser) -> dict:
    """One catalog entry with its manifest, for the install confirmation."""
    item = await plugin_service.get_plugin(catalog_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found."
        )
    return item


@router.post(
    "/{catalog_id}/install",
    response_model=PluginInstallPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_write_rate_limit],
)
async def install_plugin(catalog_id: str, user: VerifiedUser) -> dict:
    """Install a published bundle into the caller's own account."""
    _require_enabled()
    try:
        installed = await plugin_service.install_from_catalog(user.id, catalog_id)
    except (PluginValidationError, PluginSecurityError, AgentValidationError) as exc:
        raise _bad_request(exc) from exc
    if installed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found."
        )
    return installed


@router.post(
    "/import",
    response_model=PluginInstallPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_probe_rate_limit],
)
async def import_plugin(payload: PluginImport, user: VerifiedUser) -> dict:
    """Fetch a manifest from a URL and install it.

    Behind its own switch. This bundle has not passed Maestro's publish scan and
    has seen no moderation, and the URL can serve something different tomorrow —
    which is why the install record keeps the origin host, so an incident can
    enumerate who fetched from where.
    """
    _require_enabled()
    if not settings.plugin_external_import_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Importing a plugin from a URL is disabled on this deployment.",
        )
    await reject_private_host(payload.url)
    try:
        manifest = await plugin_service.fetch_manifest(payload.url)
        return await plugin_service.install(
            user.id, manifest, source="url", origin_url=payload.url
        )
    except (PluginValidationError, PluginSecurityError, AgentValidationError) as exc:
        raise _bad_request(exc) from exc


@router.get(
    "/installed/{install_id}/uninstall-preview",
    response_model=PluginUninstallPreview,
    dependencies=[_read_rate_limit],
)
async def preview_uninstall(
    install_id: str, user: ActiveUser
) -> PluginUninstallPreview:
    """Exactly what a delete would remove, with edited records flagged."""
    preview = await plugin_service.uninstall_preview(user.id, install_id)
    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not installed."
        )
    return preview


@router.delete(
    "/installed/{install_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_write_rate_limit],
)
async def uninstall_plugin(install_id: str, user: ActiveUser) -> None:
    """Remove a bundle and every record it still owns.

    Deliberately *not* gated on ``PLUGINS_ENABLED``: an operator turning the
    feature off must not strand records their users can no longer remove.
    """
    if not await plugin_service.uninstall(user.id, install_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not installed."
        )
