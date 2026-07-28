"""Agent management endpoints.

Exposes the built-in domain agents (read-only) plus full CRUD over the user's
own custom agents (system prompt + declared tools). System prompts are
security-scanned on write inside the service layer (CLAUDE.md §9.3).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.agents.registry import DOMAIN_CATALOG
from app.core.constants import RATE_LIMIT_READ, RATE_LIMIT_WRITE
from app.core.deps import ActiveUser
from app.schemas.agent import (
    AgentConfigCreate,
    AgentConfigPublic,
    AgentConfigUpdate,
    SystemPromptUpdate,
    ToolCatalogEntry,
)
from app.services import agent_service
from app.services.agent_service import AgentValidationError
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/agents", tags=["agents"])

_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="agents")
# Writes run the system prompt through the security scanner.
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="agents")


@router.get("", dependencies=[_read_rate_limit])
async def list_agents(user: ActiveUser) -> dict:
    """List built-in domain agents and the user's custom agents."""
    builtin = [
        {
            "id": entry.id,
            "name": entry.name,
            "domain": entry.id,
            "type": "builtin",
            "description": entry.description,
            "capabilities": list(entry.capabilities),
            "tools": list(entry.tools),
            "team": [
                {
                    "id": member.id,
                    "name": member.name,
                    "description": member.description,
                }
                for member in entry.team
            ],
        }
        for entry in DOMAIN_CATALOG
    ]
    custom = await agent_service.list_agents(user.id)
    return {"builtin": builtin, "custom": custom}


@router.get(
    "/tools",
    response_model=list[ToolCatalogEntry],
    dependencies=[_read_rate_limit],
)
async def list_tools(user: ActiveUser) -> list[ToolCatalogEntry]:
    """Return the catalog of tools that can be assigned to a custom agent.

    Annotated per caller: which tools have a real runtime, which need a BYOK
    key, and whether this user already holds it. Presence is read from the
    provider column alone — no key is ever decrypted to build this response.
    """
    return await agent_service.tool_catalog_for(user.id)


@router.post(
    "",
    response_model=AgentConfigPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_write_rate_limit],
)
async def create_agent(payload: AgentConfigCreate, user: ActiveUser) -> dict:
    """Create a new custom agent."""
    try:
        return await agent_service.create_agent(user.id, payload)
    except AgentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get(
    "/{agent_id}", response_model=AgentConfigPublic, dependencies=[_read_rate_limit]
)
async def get_agent(agent_id: str, user: ActiveUser) -> dict:
    """Return one of the user's custom agents."""
    agent = await agent_service.get_agent(user.id, agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found."
        )
    return agent


@router.put(
    "/{agent_id}", response_model=AgentConfigPublic, dependencies=[_write_rate_limit]
)
async def update_agent(
    agent_id: str, payload: AgentConfigUpdate, user: ActiveUser
) -> dict:
    """Update one of the user's custom agents."""
    try:
        agent = await agent_service.update_agent(user.id, agent_id, payload)
    except AgentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found."
        )
    return agent


@router.patch(
    "/{agent_id}/system-prompt",
    response_model=AgentConfigPublic,
    dependencies=[_write_rate_limit],
)
async def update_system_prompt(
    agent_id: str, payload: SystemPromptUpdate, user: ActiveUser
) -> dict:
    """Update just the system prompt of a custom agent (CLAUDE.md §7)."""
    try:
        agent = await agent_service.update_agent(
            user.id, agent_id, AgentConfigUpdate(system_prompt=payload.system_prompt)
        )
    except AgentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found."
        )
    return agent


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_write_rate_limit],
)
async def delete_agent(agent_id: str, user: ActiveUser) -> None:
    """Delete one of the user's custom agents."""
    deleted = await agent_service.delete_agent(user.id, agent_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found."
        )
