"""Marketplace service (MongoDB ``marketplace_items``).

Publishing an agent team runs a **mandatory** security scan on the system
prompt — it can never be skipped (CLAUDE.md §9.3). Installing copies the item
into the caller's own custom agents (which re-validates it), so a marketplace
author never gains access to the installer's data or API keys (CLAUDE.md §9.3).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.agents.registry import normalize_domain
from app.core.constants import (
    MARKETPLACE_COMMUNITY_AUTHOR,
    MARKETPLACE_SHOWCASE_LIMIT,
    SECURITY_SCAN_PASSED,
    TOOL_IDS,
    MongoCollection,
)
from app.core.database import get_mongo_db
from app.schemas.agent import AgentConfigCreate
from app.schemas.marketplace import MarketplacePublish
from app.services import agent_service
from app.utils import prompt_guard

# Fields safe to return to clients (never expose author identity or Mongo _id).
_PUBLIC_PROJECTION = {"_id": 0, "author_id": 0}

# The anonymous showcase drops the system prompt at the database level rather
# than relying on the response model alone: a projection cannot be bypassed by
# a future handler that forgets to narrow its response_model.
_PREVIEW_PROJECTION = {"_id": 0, "author_id": 0, "system_prompt": 0}


class MarketplaceSecurityError(ValueError):
    """Raised when a published item fails its mandatory security scan."""


def _collection():
    return get_mongo_db()[MongoCollection.MARKETPLACE_ITEMS.value]


def _security_scan(system_prompt: str) -> dict[str, Any]:
    """Run the mandatory prompt security scan; raise if it does not pass."""
    findings = prompt_guard.scan_prompt(system_prompt)
    if findings:
        raise MarketplaceSecurityError(
            "Publish rejected: system prompt failed the mandatory security scan."
        )
    return {"status": "passed", "findings": [], "scanned_at": datetime.now(UTC)}


def _shape_preview(doc: dict[str, Any]) -> dict[str, Any]:
    """Flatten a raw document into the anonymous preview shape.

    ``featured`` and ``author_label`` post-date the first published items, and
    ``.get`` keeps those older documents renderable.
    """
    return {
        **doc,
        "featured": doc.get("featured", False),
        "author_label": doc.get("author_label", MARKETPLACE_COMMUNITY_AUTHOR),
        "security_scan_status": doc.get("security_scan", {}).get(
            "status", SECURITY_SCAN_PASSED
        ),
    }


async def list_items() -> list[dict[str, Any]]:
    """Return published marketplace items, newest first."""
    cursor = _collection().find({}, _PUBLIC_PROJECTION).sort("created_at", -1)
    return [doc async for doc in cursor]


async def list_showcase(
    limit: int = MARKETPLACE_SHOWCASE_LIMIT,
) -> list[dict[str, Any]]:
    """Return items for the public landing showcase, without system prompts.

    Featured (first-party) teams lead, then the most-installed community teams,
    then the newest. Callers split the two bands on the ``featured`` flag.
    """
    cursor = (
        _collection()
        .find({}, _PREVIEW_PROJECTION)
        .sort([("featured", -1), ("installs", -1), ("created_at", -1)])
        .limit(limit)
    )
    return [_shape_preview(doc) async for doc in cursor]


async def get_item(item_id: str) -> dict[str, Any] | None:
    """Return one published item, or None."""
    return await _collection().find_one({"id": item_id}, _PUBLIC_PROJECTION)


async def publish(user_id: uuid.UUID, payload: MarketplacePublish) -> dict[str, Any]:
    """Publish an agent team after a mandatory security scan.

    ``featured`` is written as a literal ``False`` and is absent from
    ``MarketplacePublish``, so a publisher can never promote their own item onto
    the landing page — only the seed script sets it.
    """
    scan = _security_scan(payload.system_prompt)
    tools = [t for t in payload.tools if t in TOOL_IDS]
    now = datetime.now(UTC)
    document = {
        "id": str(uuid.uuid4()),
        "author_id": str(user_id),
        "name": payload.name,
        "description": payload.description,
        "domain": normalize_domain(payload.domain),
        "system_prompt": payload.system_prompt,
        "tools": tools,
        "installs": 0,
        "featured": False,
        "author_label": MARKETPLACE_COMMUNITY_AUTHOR,
        "security_scan": scan,
        "created_at": now,
    }
    await _collection().insert_one(dict(document))
    document.pop("author_id", None)
    return document


async def install(user_id: uuid.UUID, item_id: str) -> dict[str, Any] | None:
    """Install an item into the caller's custom agents. Returns the new agent."""
    item = await get_item(item_id)
    if item is None:
        return None
    agent = await agent_service.create_agent(
        user_id,
        AgentConfigCreate(
            name=item["name"],
            domain=item["domain"],
            system_prompt=item["system_prompt"],
            tools=item.get("tools", []),
        ),
    )
    await _collection().update_one({"id": item_id}, {"$inc": {"installs": 1}})
    return agent


async def reviews(item_id: str) -> list[dict[str, Any]]:
    """Return reviews for an item (ratings arrive in a later round)."""
    return []
