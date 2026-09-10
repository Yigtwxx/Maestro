"""Custom API tool endpoints: register your own HTTP endpoint as an agent tool.

Responses never carry secret material — only ``secret_hint`` (CLAUDE.md §9.1).
The write paths require a verified account, mirroring ``api_keys``: both store a
credential, and both point the backend at a host the user chose.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1._outbound import reject_private_host
from app.core.constants import (
    RATE_LIMIT_OUTBOUND_PROBE,
    RATE_LIMIT_READ,
    RATE_LIMIT_WRITE,
)
from app.core.deps import ActiveUser, VerifiedUser
from app.schemas.custom_api_tool import (
    CustomApiToolCreate,
    CustomApiToolPublic,
    CustomApiToolTestRequest,
    CustomApiToolTestResult,
    CustomApiToolUpdate,
)
from app.services import custom_api_service
from app.services.custom_api_service import CustomApiValidationError
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/custom-api-tools", tags=["custom-api-tools"])

_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="custom-api-tools")
# Writes encrypt a credential and validate a user-supplied host.
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="custom-api-tools")
# The dry run actually leaves the building. See RATE_LIMIT_OUTBOUND_PROBE.
_probe_rate_limit = rate_limit(RATE_LIMIT_OUTBOUND_PROBE, scope="custom-api-tools")


@router.get(
    "", response_model=list[CustomApiToolPublic], dependencies=[_read_rate_limit]
)
async def list_custom_api_tools(user: ActiveUser) -> list[dict]:
    """List the current user's registered endpoints (never their secrets)."""
    return await custom_api_service.list_tools(user.id)


@router.post(
    "",
    response_model=CustomApiToolPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_write_rate_limit],
)
async def create_custom_api_tool(
    payload: CustomApiToolCreate, user: VerifiedUser
) -> dict:
    """Register an endpoint this user's agents may call."""
    await reject_private_host(payload.base_url)
    try:
        return await custom_api_service.create_tool(user.id, payload)
    except CustomApiValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get(
    "/{tool_id}", response_model=CustomApiToolPublic, dependencies=[_read_rate_limit]
)
async def get_custom_api_tool(tool_id: str, user: ActiveUser) -> dict:
    """Return one of the user's registered endpoints."""
    tool = await custom_api_service.get_tool(user.id, tool_id)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API tool not found."
        )
    return tool


@router.patch(
    "/{tool_id}", response_model=CustomApiToolPublic, dependencies=[_write_rate_limit]
)
async def update_custom_api_tool(
    tool_id: str, payload: CustomApiToolUpdate, user: VerifiedUser
) -> dict:
    """Update one endpoint. Omitting ``secret`` leaves the stored one in place."""
    if payload.base_url is not None:
        await reject_private_host(payload.base_url)
    try:
        tool = await custom_api_service.update_tool(user.id, tool_id, payload)
    except CustomApiValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API tool not found."
        )
    return tool


@router.delete(
    "/{tool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_write_rate_limit],
)
async def delete_custom_api_tool(tool_id: str, user: ActiveUser) -> None:
    """Delete one of the user's registered endpoints."""
    if not await custom_api_service.delete_tool(user.id, tool_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API tool not found."
        )


@router.post(
    "/{tool_id}/test",
    response_model=CustomApiToolTestResult,
    dependencies=[_probe_rate_limit],
)
async def test_custom_api_tool(
    tool_id: str, payload: CustomApiToolTestRequest, user: ActiveUser
) -> CustomApiToolTestResult:
    """Call the endpoint once and report a short preview.

    Runs the same path an agent would, so what it reports is what the agent
    would see. The preview is capped and injection-scanned; request headers are
    never echoed back.
    """
    tools = await custom_api_service.load_tools(user.id, [tool_id])
    if not tools:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API tool not found, or it is disabled.",
        )
    return await custom_api_service.dry_run(tools[0], payload.args)
