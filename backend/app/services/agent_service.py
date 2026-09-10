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
from app.core.config import settings
from app.core.constants import (
    COMMUNITY_PLATFORMS,
    COMMUNITY_READ_ACTION,
    CONNECTED_TOOL_PROVIDERS,
    CUSTOM_AGENTS_MAX,
    EXECUTABLE_TOOL_IDS,
    KEYLESS_CONNECTED_TOOL_IDS,
    MCP_TOOLS_PER_AGENT_MAX,
    ROUTING_CUSTOM_AGENTS_MAX,
    TOOL_CATALOG,
    TOOL_DESCRIPTIONS,
    TOOL_IDS,
    MongoCollection,
)
from app.core.database import get_mongo_db
from app.schemas.agent import AgentConfigCreate, AgentConfigUpdate, ToolCatalogEntry
from app.services import (
    custom_api_service,
    mcp_service,
    service_key_service,
    skill_service,
)
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


async def _validate_custom_api_tool_ids(
    user_id: uuid.UUID, tool_ids: list[str]
) -> list[str]:
    """Keep only endpoint ids this user owns; reject the rest.

    The ownership gate for attaching a registered endpoint to an agent. Refusing
    with a 400 rather than silently dropping matters: a marketplace item or a
    hand-written payload naming someone else's id should be told no, not quietly
    given an agent that is missing the tool it claims to have. The runtime is
    still scoped independently — ``custom_api_service.load_tools`` filters by
    ``user_id`` — so this is the readable layer, not the only one.
    """
    if not tool_ids:
        return []
    deduped = list(dict.fromkeys(tool_ids))
    owned = await custom_api_service.get_tool_ids(user_id, deduped)
    unknown = [t for t in deduped if t not in owned]
    if unknown:
        raise AgentValidationError(f"Unknown API tools: {', '.join(unknown)}")
    return deduped


async def _validate_skill_ids(user_id: uuid.UUID, skill_ids: list[str]) -> list[str]:
    """Keep only skill ids this user owns; reject the rest.

    The ownership gate for attaching a skill, and the exact twin of
    :func:`_validate_custom_api_tool_ids` — including its choice to refuse
    rather than silently drop, so a payload naming someone else's id is told no
    instead of yielding an agent that is quietly missing what it claims.
    """
    if not skill_ids:
        return []
    deduped = list(dict.fromkeys(skill_ids))
    owned = await skill_service.get_skill_ids(user_id, deduped)
    unknown = [s for s in deduped if s not in owned]
    if unknown:
        raise AgentValidationError(f"Unknown skills: {', '.join(unknown)}")
    return deduped


async def _validate_mcp_server_ids(
    user_id: uuid.UUID, server_ids: list[str]
) -> list[str]:
    """Keep only server ids this user owns, and refuse an oversized tool total.

    Two checks, not one. Ownership is the twin of the other two validators. The
    second is the per-agent *tool* cap: three servers advertising forty tools
    each would put 120 schemas and 120 rule lines into one member's system
    prompt, crowding out the role that prompt exists to state. The server count
    alone does not bound that, so it is counted here — and truncated again at
    composition time, because a server can add tools after this ran.
    """
    if not server_ids:
        return []
    deduped = list(dict.fromkeys(server_ids))
    owned = await mcp_service.get_server_ids(user_id, deduped)
    unknown = [s for s in deduped if s not in owned]
    if unknown:
        raise AgentValidationError(f"Unknown MCP servers: {', '.join(unknown)}")

    servers = await mcp_service.load_servers(user_id, deduped)
    total = sum(len(server.tools) for server in servers)
    if total > MCP_TOOLS_PER_AGENT_MAX:
        raise AgentValidationError(
            f"Those servers offer {total} tools together, above the "
            f"{MCP_TOOLS_PER_AGENT_MAX} an agent may hold. Disable some tools "
            "on a server, or attach fewer servers."
        )
    return deduped


async def annotate_missing_tools(
    user_id: uuid.UUID, docs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Add ``missing_tools`` to each agent document, in one round trip.

    A skill's ``required_tools`` is advisory: nothing at run time reads it,
    because letting attached text widen an agent's tool set would break the
    one-way narrowing ``resolve_enabled_tools`` relies on. The requirement is
    only useful if the wizard can *show* it, which is what this computes.

    Deliberately not folded into :func:`get_agent`: that is on the task-execution
    path (``registry.resolve_domain_info``), and a run has no use for advice
    aimed at the editor.
    """
    wanted = sorted({sid for doc in docs for sid in doc.get("skill_ids") or []})
    requirements = await skill_service.get_required_tools(user_id, wanted)
    for doc in docs:
        declared = set(doc.get("tools") or [])
        needed: list[str] = []
        for skill_id in doc.get("skill_ids") or []:
            needed.extend(requirements.get(skill_id, ()))
        doc["missing_tools"] = sorted({t for t in needed if t not in declared})
    return docs


def _guard_prompt(system_prompt: str) -> None:
    """Reject a system prompt that trips the injection scanner."""
    findings = prompt_guard.scan_prompt(system_prompt)
    if findings:
        raise AgentValidationError(
            "System prompt failed the security scan (possible prompt injection)."
        )


async def tool_catalog_for(user_id: uuid.UUID) -> list[ToolCatalogEntry]:
    """The declarable tool catalog, annotated for one user.

    Composed from the existing single sources of truth rather than a second
    hand-maintained table: ids/labels from ``TOOL_CATALOG``, the executable
    split from ``EXECUTABLE_TOOL_IDS``, credential requirements from
    ``CONNECTED_TOOL_PROVIDERS``, and prose from ``TOOL_DESCRIPTIONS`` — the
    same text the model is given for native function calling.

    ``available`` reads the operator switch with the same expression
    ``resolve_enabled_tools`` uses. It deliberately does *not* run the Docker
    probe that gates ``code_execution`` at runtime: this is a read endpoint, and
    the switch (off by default, CLAUDE.md §11) already answers the question for
    every deployment that has not deliberately turned it on.
    """
    connected = await service_key_service.connected_providers(user_id)
    entries: list[ToolCatalogEntry] = []
    for tool in TOOL_CATALOG:
        tool_id = tool["id"]
        if tool_id == COMMUNITY_READ_ACTION:
            # No single provider: the call's ``platform`` argument picks one, so
            # any one connected community key makes the tool usable.
            providers = sorted(COMMUNITY_PLATFORMS)
        elif tool_id in CONNECTED_TOOL_PROVIDERS:
            providers = [CONNECTED_TOOL_PROVIDERS[tool_id].value]
        else:
            providers = []
        entries.append(
            ToolCatalogEntry(
                id=tool_id,
                label=tool["label"],
                description=TOOL_DESCRIPTIONS.get(tool_id, ""),
                kind=(
                    "executable" if tool_id in EXECUTABLE_TOOL_IDS else "declarative"
                ),
                providers=providers,
                keyless=tool_id in KEYLESS_CONNECTED_TOOL_IDS,
                # Nothing to connect for a keyless or non-connected tool, so it
                # reports connected rather than misleadingly "missing a key".
                connected=(not providers) or bool(connected & set(providers)),
                available=getattr(settings, f"{tool_id}_enabled", True),
            )
        )
    return entries


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
    plugin_id: str | None = None,
) -> dict[str, Any]:
    """Create and persist a validated custom agent.

    ``source``/``marketplace_item_id`` record provenance (a marketplace install
    stamps them). The passing security scan is recorded with the scanner version
    so a later scanner bump forces a re-scan at execution time.

    This is the single insert point for a custom agent, marketplace installs
    included, so it is where ``CUSTOM_AGENTS_MAX`` is enforced -- a one-click
    install must not be the way around a cap the wizard respects.
    """
    owned = await _collection().count_documents({"user_id": str(user_id)})
    if owned >= CUSTOM_AGENTS_MAX:
        raise AgentValidationError(
            f"You can own at most {CUSTOM_AGENTS_MAX} custom agents. "
            "Delete one to make room."
        )
    _guard_prompt(payload.system_prompt)
    tools = _validate_tools(payload.tools)
    custom_api_tool_ids = await _validate_custom_api_tool_ids(
        user_id, payload.custom_api_tool_ids
    )
    skill_ids = await _validate_skill_ids(user_id, payload.skill_ids)
    mcp_server_ids = await _validate_mcp_server_ids(user_id, payload.mcp_server_ids)
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
        "custom_api_tool_ids": custom_api_tool_ids,
        "skill_ids": skill_ids,
        "mcp_server_ids": mcp_server_ids,
        "source": source,
        "marketplace_item_id": marketplace_item_id,
        # Which installed plugin owns this record, if any. An uninstall only
        # deletes what still carries its own id, so a record the user detached
        # survives.
        "plugin_id": plugin_id,
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
    if payload.custom_api_tool_ids is not None:
        changes["custom_api_tool_ids"] = await _validate_custom_api_tool_ids(
            user_id, payload.custom_api_tool_ids
        )
    if payload.skill_ids is not None:
        changes["skill_ids"] = await _validate_skill_ids(user_id, payload.skill_ids)
    if payload.mcp_server_ids is not None:
        changes["mcp_server_ids"] = await _validate_mcp_server_ids(
            user_id, payload.mcp_server_ids
        )
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
