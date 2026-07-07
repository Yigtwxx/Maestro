"""Agent management endpoints.

Exposes the built-in domain agents (read-only) plus full CRUD over the user's
own custom agents (system prompt + declared tools). System prompts are
security-scanned on write inside the service layer (CLAUDE.md §9.3).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.agents.registry import DOMAIN_CATALOG
from app.core.constants import TOOL_CATALOG
from app.core.deps import CurrentUser
from app.schemas.agent import (
    AgentConfigCreate,
    AgentConfigPublic,
    AgentConfigUpdate,
    SystemPromptUpdate,
)
from app.services import agent_service
from app.services.agent_service import AgentValidationError

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
async def list_agents(user: CurrentUser) -> dict:
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


@router.get("/tools")
async def list_tools(user: CurrentUser) -> list[dict]:
    """Return the catalog of tools that can be assigned to a custom agent."""
    return [dict(tool) for tool in TOOL_CATALOG]


@router.post("", response_model=AgentConfigPublic, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentConfigCreate, user: CurrentUser) -> dict:
    """Create a new custom agent."""
    try:
        return await agent_service.create_agent(user.id, payload)
    except AgentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get("/{agent_id}", response_model=AgentConfigPublic)
async def get_agent(agent_id: str, user: CurrentUser) -> dict:
    """Return one of the user's custom agents."""
    agent = await agent_service.get_agent(user.id, agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found."
        )
    return agent


@router.put("/{agent_id}", response_model=AgentConfigPublic)
async def update_agent(
    agent_id: str, payload: AgentConfigUpdate, user: CurrentUser
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


@router.patch("/{agent_id}/system-prompt", response_model=AgentConfigPublic)
async def update_system_prompt(
    agent_id: str, payload: SystemPromptUpdate, user: CurrentUser
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


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, user: CurrentUser) -> None:
    """Delete one of the user's custom agents."""
    deleted = await agent_service.delete_agent(user.id, agent_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found."
        )
