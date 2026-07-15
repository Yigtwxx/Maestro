"""Custom-agent configuration service (MongoDB ``agent_configurations``).

Every configuration is scoped to its owner (``user_id`` filter on all reads and
writes) so one user's agents can never be seen or mutated by another
(CLAUDE.md §15.4). System prompts are scanned for injection patterns on write
(CLAUDE.md §9.3).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.agents.registry import normalize_domain
from app.core.constants import ROUTING_CUSTOM_AGENTS_MAX, TOOL_IDS, MongoCollection
from app.core.database import get_mongo_db
from app.schemas.agent import AgentConfigCreate, AgentConfigUpdate
from app.utils import prompt_guard


class AgentValidationError(ValueError):
    """Raised when a custom agent fails validation or a security scan."""


def _collection():
    return get_mongo_db()[MongoCollection.AGENT_CONFIGURATIONS.value]


def _validate_tools(tools: list[str]) -> list[str]:
    """Keep only known tool ids; reject unknown ones."""
    unknown = [t for t in tools if t not in TOOL_IDS]
    if unknown:
        raise AgentValidationError(f"Unknown tools: {', '.join(unknown)}")
    # De-duplicate while preserving order.
    return list(dict.fromkeys(tools))


def _guard_prompt(system_prompt: str) -> None:
    """Reject a system prompt that trips the injection scanner."""
    findings = prompt_guard.scan_prompt(system_prompt)
    if findings:
        raise AgentValidationError(
            "System prompt failed the security scan (possible prompt injection)."
        )


async def list_agents(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Return the user's custom agents, newest first."""
    cursor = (
        _collection().find({"user_id": str(user_id)}, {"_id": 0}).sort("created_at", -1)
    )
    return [doc async for doc in cursor]


async def get_agent(user_id: uuid.UUID, agent_id: str) -> dict[str, Any] | None:
    """Return one custom agent owned by the user, or None."""
    return await _collection().find_one(
        {"id": agent_id, "user_id": str(user_id)}, {"_id": 0}
    )


async def list_routable_agents(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Return the user's routable custom agents (id + routing_hint + name).

    Feeds the orchestrator's routing-catalog merge; capped so a user with many
    agents cannot blow up the classifier prompt (Backend v2 §4.3).
    """
    cursor = (
        _collection()
        .find(
            {"user_id": str(user_id), "routable": True},
            {"_id": 0, "id": 1, "name": 1, "routing_hint": 1},
        )
        .sort("created_at", -1)
        .limit(ROUTING_CUSTOM_AGENTS_MAX)
    )
    return [doc async for doc in cursor]


async def create_agent(
    user_id: uuid.UUID,
    payload: AgentConfigCreate,
    *,
    source: str = "custom",
    marketplace_item_id: str | None = None,
) -> dict[str, Any]:
    """Create and persist a validated custom agent.

    ``source``/``marketplace_item_id`` record provenance (a marketplace install
    stamps them). The passing security scan is recorded with the scanner version
    so a later scanner bump forces a re-scan at execution time.
    """
    _guard_prompt(payload.system_prompt)
    tools = _validate_tools(payload.tools)
    now = datetime.now(UTC)
    document = {
        "id": str(uuid.uuid4()),
        "user_id": str(user_id),
        "name": payload.name,
        "domain": normalize_domain(payload.domain),
        "system_prompt": payload.system_prompt,
        "tools": tools,
        "description": payload.description,
        "routing_hint": payload.routing_hint,
        "output_format": payload.output_format,
        "routable": payload.routable,
        "source": source,
        "marketplace_item_id": marketplace_item_id,
        "security_scan": {"version": prompt_guard.SCANNER_VERSION, "passed": True},
        "created_at": now,
        "updated_at": now,
    }
    await _collection().insert_one(dict(document))
    return document


async def update_agent(
    user_id: uuid.UUID, agent_id: str, payload: AgentConfigUpdate
) -> dict[str, Any] | None:
    """Apply a partial update to a user-owned agent; returns the new state."""
    changes: dict[str, Any] = {}
    if payload.name is not None:
        changes["name"] = payload.name
    if payload.domain is not None:
        changes["domain"] = normalize_domain(payload.domain)
    if payload.system_prompt is not None:
        _guard_prompt(payload.system_prompt)
        changes["system_prompt"] = payload.system_prompt
        # Re-record the passing scan under the current scanner version.
        changes["security_scan"] = {
            "version": prompt_guard.SCANNER_VERSION,
            "passed": True,
        }
    if payload.tools is not None:
        changes["tools"] = _validate_tools(payload.tools)
    if payload.description is not None:
        changes["description"] = payload.description
    if payload.routing_hint is not None:
        changes["routing_hint"] = payload.routing_hint
    if payload.output_format is not None:
        changes["output_format"] = payload.output_format
    if payload.routable is not None:
        changes["routable"] = payload.routable
    if not changes:
        return await get_agent(user_id, agent_id)

    changes["updated_at"] = datetime.now(UTC)
    result = await _collection().update_one(
        {"id": agent_id, "user_id": str(user_id)}, {"$set": changes}
    )
    if result.matched_count == 0:
        return None
    return await get_agent(user_id, agent_id)


async def delete_agent(user_id: uuid.UUID, agent_id: str) -> bool:
    """Delete a user-owned agent. Returns True if one was removed."""
    result = await _collection().delete_one({"id": agent_id, "user_id": str(user_id)})
    return result.deleted_count > 0
