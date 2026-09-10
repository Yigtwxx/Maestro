"""Remote MCP server endpoints: register a server, discover its tools.

Responses never carry secret material — only ``secret_hint`` (CLAUDE.md §9.1).
The write paths require a verified account, mirroring ``custom_api_tools`` and
``api_keys``: all three store a credential and point the backend at a host the
user chose.

Discovery is a *separate, explicit* call rather than something registration or a
task start does implicitly. Two reasons, both load-bearing: it leaves the
building, so it carries the outbound-probe rate limit; and the tool descriptions
it caches are third-party text that lands in a system prompt, so the moment they
are scanned should be one a person triggered.
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
from app.schemas.mcp_server import (
    McpDiscoverResult,
    McpServerCreate,
    McpServerPublic,
    McpServerUpdate,
)
from app.services import mcp_service
from app.services.mcp_service import McpValidationError
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])

_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="mcp-servers")
# Writes encrypt a credential and validate a user-supplied host.
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="mcp-servers")
# Discovery actually leaves the building. See RATE_LIMIT_OUTBOUND_PROBE.
_probe_rate_limit = rate_limit(RATE_LIMIT_OUTBOUND_PROBE, scope="mcp-servers")


def _require_enabled() -> None:
    """Refuse every write while the feature is switched off.

    The executor refuses again (``mcp_service._call``), so this is the readable
    layer rather than the only one — but registering a server that can never be
    called is a worse experience than being told the deployment does not allow
    it.
    """
    if not settings.mcp_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MCP servers are disabled on this deployment.",
        )


@router.get("", response_model=list[McpServerPublic], dependencies=[_read_rate_limit])
async def list_mcp_servers(user: ActiveUser) -> list[dict]:
    """List the current user's registered servers (never their secrets)."""
    return await mcp_service.list_servers(user.id)


@router.post(
    "",
    response_model=McpServerPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_write_rate_limit],
)
async def create_mcp_server(payload: McpServerCreate, user: VerifiedUser) -> dict:
    """Register a server. Its tools are discovered by a separate call."""
    _require_enabled()
    await reject_private_host(payload.url)
    try:
        return await mcp_service.create_server(user.id, payload)
    except McpValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get(
    "/{server_id}", response_model=McpServerPublic, dependencies=[_read_rate_limit]
)
async def get_mcp_server(server_id: str, user: ActiveUser) -> dict:
    """Return one of the user's servers, including its cached tool catalog."""
    server = await mcp_service.get_server(user.id, server_id)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found."
        )
    return server


@router.patch(
    "/{server_id}", response_model=McpServerPublic, dependencies=[_write_rate_limit]
)
async def update_mcp_server(
    server_id: str, payload: McpServerUpdate, user: VerifiedUser
) -> dict:
    """Update one server. Omitting ``secret`` leaves the stored one in place.

    Changing ``url`` clears the cached catalog: those tool descriptions describe
    whatever used to answer at the old address, and keeping them would let an
    edit silently repoint every prompt line the agent already carries.
    """
    _require_enabled()
    if payload.url is not None:
        await reject_private_host(payload.url)
    try:
        server = await mcp_service.update_server(user.id, server_id, payload)
    except McpValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found."
        )
    return server


@router.delete(
    "/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_write_rate_limit],
)
async def delete_mcp_server(server_id: str, user: ActiveUser) -> None:
    """Delete one of the user's servers.

    Agents that attached it keep the id; the runtime intersects against what
    actually loaded, so a deleted server stops offering tools rather than
    breaking the agent.
    """
    if not await mcp_service.delete_server(user.id, server_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found."
        )


@router.post(
    "/{server_id}/discover",
    response_model=McpDiscoverResult,
    dependencies=[_probe_rate_limit],
)
async def discover_mcp_server(server_id: str, user: ActiveUser) -> McpDiscoverResult:
    """Handshake with the server and refresh its cached tool catalog.

    Reports a failure in the body rather than raising: pointing at a server that
    is down, or that refuses the handshake, is an ordinary thing to do and the
    user needs to be told which of the two happened.
    """
    _require_enabled()
    server = await mcp_service.get_server(user.id, server_id)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found."
        )
    return await mcp_service.discover(user.id, server_id)
