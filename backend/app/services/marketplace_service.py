"""Marketplace service (MongoDB ``marketplace_items``).

Publishing an agent team runs a **mandatory** security scan on the system
prompt — it can never be skipped (CLAUDE.md §9.3). Installing copies the item
into the caller's own custom agents (which re-validates it), so a marketplace
author never gains access to the installer's data or API keys (CLAUDE.md §9.3).

Every install also appends an event to ``marketplace_installs`` shaped
``{item_id, created_at}`` — deliberately **without** a ``user_id``: the events
feed only the anonymous install-trend sparkline, which keeps the collection
outside the account-purge contract (the per-user install already lives in
``agent_configurations``, which *is* purged).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.agents.registry import normalize_domain
from app.core.constants import (
    MARKETPLACE_COMMUNITY_AUTHOR,
    MARKETPLACE_HIDDEN_STATUSES,
    MARKETPLACE_SHOWCASE_LIMIT,
    SECURITY_SCAN_PASSED,
    TOOL_IDS,
    TREND_WINDOW_DAYS,
    MarketplaceStatus,
    MongoCollection,
)
from app.core.database import get_mongo_db
from app.schemas.agent import AgentConfigCreate
from app.schemas.marketplace import MarketplacePublish, MarketplaceReviewSubmit
from app.services import agent_service
from app.utils import prompt_guard
from app.utils.timeseries import day_index, utc_day_window

# Fields safe to return to clients (never expose author identity or Mongo _id).
_PUBLIC_PROJECTION = {"_id": 0, "author_id": 0}

# The anonymous showcase drops the system prompt at the database level rather
# than relying on the response model alone: a projection cannot be bypassed by
# a future handler that forgets to narrow its response_model.
_PREVIEW_PROJECTION = {"_id": 0, "author_id": 0, "system_prompt": 0}

# Moderator-facing projection: keeps ``author_id`` (needed to attribute abuse)
# but still drops Mongo's ``_id``. Only ever used behind the admin guard.
_ADMIN_PROJECTION = {"_id": 0}

# Excludes moderator-hidden/removed items from every end-user query. ``$nin``
# also matches documents with no ``status`` field, so items published before
# the field existed stay visible (treated as published).
_VISIBLE_FILTER: dict[str, Any] = {
    "status": {"$nin": list(MARKETPLACE_HIDDEN_STATUSES)}
}

# Excludes moderator-hidden reviews from rating aggregates and review listings.
_VISIBLE_REVIEW_FILTER: dict[str, Any] = {"hidden": {"$ne": True}}


class MarketplaceSecurityError(ValueError):
    """Raised when a published item fails its mandatory security scan."""


class MarketplaceReviewForbiddenError(ValueError):
    """Raised when a user tries to review their own published item."""


def _collection():
    return get_mongo_db()[MongoCollection.MARKETPLACE_ITEMS.value]


def _installs_collection():
    return get_mongo_db()[MongoCollection.MARKETPLACE_INSTALLS.value]


def _reviews_collection():
    return get_mongo_db()[MongoCollection.MARKETPLACE_REVIEWS.value]


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


def bucket_install_history(
    events: list[dict[str, Any]],
    item_ids: list[str],
    *,
    now: datetime,
    days: int = TREND_WINDOW_DAYS,
) -> dict[str, list[int] | None]:
    """Per-item daily install counts over the window (pure, no I/O).

    Items with no events in the window map to ``None`` — the UI hides their
    sparkline instead of drawing a fabricated flat line. Events are the
    ``{item_id, created_at}`` documents from ``marketplace_installs``.
    """
    window = utc_day_window(now, days)
    counts: dict[str, list[int]] = {item_id: [0] * days for item_id in item_ids}
    for event in events:
        series = counts.get(event.get("item_id", ""))
        created_at = event.get("created_at")
        if series is None or not isinstance(created_at, datetime):
            continue
        index = day_index(created_at, window)
        if index is not None:
            series[index] += 1
    return {
        item_id: series if any(series) else None for item_id, series in counts.items()
    }


async def list_items() -> list[dict[str, Any]]:
    """Return published marketplace items, newest first, with install trends."""
    cursor = (
        _collection().find(_VISIBLE_FILTER, _PUBLIC_PROJECTION).sort("created_at", -1)
    )
    items = [doc async for doc in cursor]
    if not items:
        return items

    now = datetime.now(UTC)
    # One query covers every card: fetch the window's events and bucket locally.
    window_start = now - timedelta(days=TREND_WINDOW_DAYS)
    events_cursor = _installs_collection().find(
        {"created_at": {"$gte": window_start}},
        {"_id": 0, "item_id": 1, "created_at": 1},
    )
    events = [doc async for doc in events_cursor]
    history = bucket_install_history(events, [item["id"] for item in items], now=now)
    for item in items:
        item["install_history"] = history[item["id"]]
    return items


async def list_showcase(
    limit: int = MARKETPLACE_SHOWCASE_LIMIT,
) -> list[dict[str, Any]]:
    """Return items for the public landing showcase, without system prompts.

    Featured (first-party) teams lead, then the most-installed community teams,
    then the newest. Callers split the two bands on the ``featured`` flag.
    """
    cursor = (
        _collection()
        .find(_VISIBLE_FILTER, _PREVIEW_PROJECTION)
        .sort([("featured", -1), ("installs", -1), ("created_at", -1)])
        .limit(limit)
    )
    return [_shape_preview(doc) async for doc in cursor]


async def get_item(item_id: str) -> dict[str, Any] | None:
    """Return one visible (non-hidden) published item, or None."""
    return await _collection().find_one(
        {"id": item_id, **_VISIBLE_FILTER}, _PUBLIC_PROJECTION
    )


async def review_exists(review_id: str) -> bool:
    """Whether a visible review with this id exists (for report validation)."""
    doc = await _reviews_collection().find_one(
        {"id": review_id, **_VISIBLE_REVIEW_FILTER}, {"_id": 0, "id": 1}
    )
    return doc is not None


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
        "status": MarketplaceStatus.PUBLISHED.value,
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
            description=item.get("description", ""),
            # A literal, never ``item.get(...)``. A registered endpoint belongs
            # to the account that created it — its URL and its encrypted
            # credential both — so installing someone's agent must never attach
            # theirs. Written explicitly rather than left to the default so the
            # invariant is visible at the point it matters (CLAUDE.md §8).
            custom_api_tool_ids=[],
        ),
        source="marketplace",
        marketplace_item_id=item_id,
    )
    await _installs_collection().insert_one(
        {"item_id": item_id, "created_at": datetime.now(UTC)}
    )
    await _collection().update_one({"id": item_id}, {"$inc": {"installs": 1}})
    return agent


def _shape_review(doc: dict[str, Any], user_id: uuid.UUID) -> dict[str, Any]:
    """Strip internal fields (``user_id``, ``_id``) and mark the caller's own.

    Reviewer identity never leaves the service: there is no opt-in for making
    display names public (same policy as ``MARKETPLACE_COMMUNITY_AUTHOR``). The
    review's own ``id`` is exposed (a random uuid, not identity) so a reader can
    report a specific abusive review.
    """
    return {
        "id": doc["id"],
        "rating": doc["rating"],
        "comment": doc.get("comment"),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
        "is_own": doc.get("user_id") == str(user_id),
    }


async def recompute_rating(item_id: str) -> None:
    """Recompute the item's denormalized rating aggregates from source.

    Recomputing over all reviews (instead of applying deltas) keeps the write
    idempotent, so review upserts and account purges can safely re-run it.
    """
    pipeline = [
        {"$match": {"item_id": item_id, **_VISIBLE_REVIEW_FILTER}},
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "count": {"$sum": 1}}},
    ]
    rows = [row async for row in _reviews_collection().aggregate(pipeline)]
    if rows:
        update = {
            "rating_avg": round(rows[0]["avg"], 2),
            "rating_count": rows[0]["count"],
        }
    else:
        update = {"rating_avg": None, "rating_count": 0}
    await _collection().update_one({"id": item_id}, {"$set": update})


async def submit_review(
    user_id: uuid.UUID, item_id: str, payload: MarketplaceReviewSubmit
) -> dict[str, Any] | None:
    """Create or replace the caller's review of an item (one per user).

    Returns None when the item does not exist. Raises
    ``MarketplaceReviewForbiddenError`` when the caller authored the item.
    """
    item = await _collection().find_one(
        {"id": item_id, **_VISIBLE_FILTER}, {"_id": 0, "id": 1, "author_id": 1}
    )
    if item is None:
        return None
    if item.get("author_id") == str(user_id):
        raise MarketplaceReviewForbiddenError(
            "Authors cannot review their own published items."
        )
    now = datetime.now(UTC)
    key = {"item_id": item_id, "user_id": str(user_id)}
    await _reviews_collection().update_one(
        key,
        {
            "$set": {
                "rating": payload.rating,
                "comment": payload.comment,
                "updated_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )
    await recompute_rating(item_id)
    stored = await _reviews_collection().find_one(key)
    if stored is None:  # deleted concurrently (e.g. a purge race)
        return None
    return _shape_review(stored, user_id)


async def list_reviews(
    item_id: str, user_id: uuid.UUID, *, limit: int, offset: int
) -> dict[str, Any] | None:
    """One page of an item's reviews (newest first) plus the caller's own.

    Returns None when the item does not exist. ``my_review`` is fetched
    separately so the edit form can prefill regardless of pagination.
    """
    if (
        await _collection().find_one(
            {"id": item_id, **_VISIBLE_FILTER}, {"_id": 0, "id": 1}
        )
        is None
    ):
        return None
    reviews = _reviews_collection()
    query = {"item_id": item_id, **_VISIBLE_REVIEW_FILTER}
    cursor = reviews.find(query).sort("updated_at", -1).skip(offset).limit(limit)
    items = [_shape_review(doc, user_id) async for doc in cursor]
    total = await reviews.count_documents(query)
    mine = await reviews.find_one(
        {"item_id": item_id, "user_id": str(user_id), **_VISIBLE_REVIEW_FILTER}
    )
    return {
        "items": items,
        "total": total,
        "my_review": _shape_review(mine, user_id) if mine else None,
    }


async def purge_user_reviews(user_id: uuid.UUID) -> None:
    """Erase every review the user wrote and heal the affected aggregates.

    Part of the account-purge contract (CLAUDE.md §15.10): idempotent, and any
    store failure propagates so the purge sweep can retry.
    """
    reviews = _reviews_collection()
    item_ids = await reviews.distinct("item_id", {"user_id": str(user_id)})
    await reviews.delete_many({"user_id": str(user_id)})
    for item_id in item_ids:
        await recompute_rating(item_id)


# --- Moderation (admin-only; author/reviewer identity retained) ---


async def admin_list_items(
    *, status: str | None = None, limit: int, offset: int
) -> list[dict[str, Any]]:
    """Every item (any status), newest first, WITH author attribution.

    Unlike the public listing this keeps ``author_id`` and returns hidden and
    removed items so a moderator can review and reinstate them. Behind the admin
    guard only.
    """
    query: dict[str, Any] = {} if status is None else {"status": status}
    cursor = (
        _collection()
        .find(query, _ADMIN_PROJECTION)
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def admin_get_item(item_id: str) -> dict[str, Any] | None:
    """One item of any status, with author attribution (moderator view)."""
    return await _collection().find_one({"id": item_id}, _ADMIN_PROJECTION)


async def admin_set_item_status(
    item_id: str,
    status: MarketplaceStatus,
    *,
    moderator_id: uuid.UUID,
    reason: str | None,
    at: datetime,
) -> dict[str, Any] | None:
    """Apply a moderation status (hide/remove/reinstate) to an item.

    Records who acted and why on the document itself; returns the updated item
    (moderator projection) or None when the item does not exist.
    """
    result = await _collection().update_one(
        {"id": item_id},
        {
            "$set": {
                "status": status.value,
                "moderation": {
                    "actor_id": str(moderator_id),
                    "reason": reason,
                    "at": at,
                },
            }
        },
    )
    if result.matched_count == 0:
        return None
    return await admin_get_item(item_id)


async def admin_list_reviews(item_id: str) -> list[dict[str, Any]]:
    """All reviews of an item (including hidden), with reviewer attribution."""
    cursor = (
        _reviews_collection()
        .find({"item_id": item_id}, _ADMIN_PROJECTION)
        .sort("updated_at", -1)
    )
    return [doc async for doc in cursor]


async def admin_set_review_hidden(
    review_id: str,
    hidden: bool,
    *,
    moderator_id: uuid.UUID,
    reason: str | None,
    at: datetime,
) -> dict[str, Any] | None:
    """Hide or unhide a review and heal the item's rating aggregates.

    Returns the updated review (moderator projection) or None when it does not
    exist. Recompute runs after the flag flips so a hidden review stops counting
    toward the average.
    """
    result = await _reviews_collection().find_one_and_update(
        {"id": review_id},
        {
            "$set": {
                "hidden": hidden,
                "moderation": {
                    "actor_id": str(moderator_id),
                    "reason": reason,
                    "at": at,
                },
            }
        },
    )
    if result is None:
        return None
    await recompute_rating(result["item_id"])
    return await _reviews_collection().find_one({"id": review_id}, _ADMIN_PROJECTION)
