"""Moderation service: reports, take-downs, user actions and an audit trail.

The business logic behind the admin surface. Marketplace content mutations are
delegated to ``marketplace_service`` (which owns the ``marketplace_items`` /
``marketplace_reviews`` collections); this module owns the moderation-only
collections (``moderation_reports``, ``moderation_actions``), cross-user custom
agent take-downs, and PostgreSQL user actions (suspend / role change).

Every state-changing moderator action is written to ``moderation_actions`` — an
append-only audit trail of who did what, to whom, and why.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    ADMIN_RECENT_LIMIT,
    MarketplaceStatus,
    MongoCollection,
    ReportReason,
    ReportStatus,
    ReportTarget,
    UserRole,
)
from app.core.database import get_mongo_db
from app.models.user import User
from app.services import marketplace_service

_STRIP_ID = {"_id": 0}


def _now() -> datetime:
    return datetime.now(UTC)


def _reports():
    return get_mongo_db()[MongoCollection.MODERATION_REPORTS.value]


def _actions():
    return get_mongo_db()[MongoCollection.MODERATION_ACTIONS.value]


def _items():
    return get_mongo_db()[MongoCollection.MARKETPLACE_ITEMS.value]


def _reviews():
    return get_mongo_db()[MongoCollection.MARKETPLACE_REVIEWS.value]


def _agents():
    return get_mongo_db()[MongoCollection.AGENT_CONFIGURATIONS.value]


# --- Audit trail ---


async def record_action(
    actor_id: uuid.UUID,
    action: str,
    *,
    target_type: str,
    target_id: str,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> None:
    """Append one moderator action to the audit trail (best-effort ordering)."""
    await _actions().insert_one(
        {
            "id": str(uuid.uuid4()),
            "actor_id": str(actor_id),
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "reason": reason,
            "metadata": metadata or {},
            "created_at": at or _now(),
        }
    )


async def list_actions(*, limit: int, offset: int) -> list[dict[str, Any]]:
    """The audit trail, most recent first."""
    cursor = (
        _actions().find({}, _STRIP_ID).sort("created_at", -1).skip(offset).limit(limit)
    )
    return [doc async for doc in cursor]


# --- Reports (user-submitted flags) ---


async def submit_report(
    reporter_id: uuid.UUID,
    target_type: ReportTarget,
    target_id: str,
    reason: ReportReason,
    note: str | None,
) -> dict[str, Any]:
    """Flag an item/review for moderation. One open report per user per target.

    Upserting on (reporter, target) bounds spam to a single row per reporter per
    target: re-flagging refreshes the reason/note instead of stacking rows.
    """
    now = _now()
    key = {
        "reporter_id": str(reporter_id),
        "target_type": target_type.value,
        "target_id": target_id,
    }
    await _reports().update_one(
        key,
        {
            "$set": {
                "reason": reason.value,
                "note": note,
                "status": ReportStatus.OPEN.value,
                "updated_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )
    stored = await _reports().find_one(key, _STRIP_ID)
    return stored or {**key, "reason": reason.value, "status": ReportStatus.OPEN.value}


async def list_reports(
    *, report_status: str | None, limit: int, offset: int
) -> list[dict[str, Any]]:
    """Reports for the moderation queue, newest first (optionally by status)."""
    query: dict[str, Any] = {}
    if report_status is not None:
        query["status"] = report_status
    cursor = (
        _reports()
        .find(query, _STRIP_ID)
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def _close_reports_for(
    target_type: ReportTarget,
    target_id: str,
    *,
    moderator_id: uuid.UUID,
    at: datetime,
) -> None:
    """Auto-resolve any open reports pointing at a target a moderator acted on."""
    await _reports().update_many(
        {
            "target_type": target_type.value,
            "target_id": target_id,
            "status": ReportStatus.OPEN.value,
        },
        {
            "$set": {
                "status": ReportStatus.RESOLVED.value,
                "resolved_by": str(moderator_id),
                "resolved_at": at,
            }
        },
    )


async def resolve_report(
    report_id: str,
    *,
    moderator_id: uuid.UUID,
    resolution: ReportStatus,
) -> dict[str, Any] | None:
    """Mark a report resolved or dismissed. Returns the updated report or None."""
    now = _now()
    result = await _reports().find_one_and_update(
        {"id": report_id, "status": ReportStatus.OPEN.value},
        {
            "$set": {
                "status": resolution.value,
                "resolved_by": str(moderator_id),
                "resolved_at": now,
            }
        },
    )
    if result is None:
        return None
    await record_action(
        moderator_id,
        f"report_{resolution.value}",
        target_type=result["target_type"],
        target_id=result["target_id"],
        metadata={"report_id": report_id},
        at=now,
    )
    return await _reports().find_one({"id": report_id}, _STRIP_ID)


# --- Marketplace content take-downs ---


async def set_item_status(
    item_id: str,
    status_value: MarketplaceStatus,
    *,
    moderator_id: uuid.UUID,
    reason: str | None,
) -> dict[str, Any] | None:
    """Hide/remove/reinstate an item, audit it, and close its open reports."""
    now = _now()
    item = await marketplace_service.admin_set_item_status(
        item_id, status_value, moderator_id=moderator_id, reason=reason, at=now
    )
    if item is None:
        return None
    await record_action(
        moderator_id,
        f"item_{status_value.value}",
        target_type=ReportTarget.ITEM.value,
        target_id=item_id,
        reason=reason,
        at=now,
    )
    if status_value != MarketplaceStatus.PUBLISHED:
        await _close_reports_for(
            ReportTarget.ITEM, item_id, moderator_id=moderator_id, at=now
        )
    return item


async def set_review_hidden(
    review_id: str,
    hidden: bool,
    *,
    moderator_id: uuid.UUID,
    reason: str | None,
) -> dict[str, Any] | None:
    """Hide/unhide a review, audit it, and close its open reports."""
    now = _now()
    review = await marketplace_service.admin_set_review_hidden(
        review_id, hidden, moderator_id=moderator_id, reason=reason, at=now
    )
    if review is None:
        return None
    await record_action(
        moderator_id,
        "review_hidden" if hidden else "review_unhidden",
        target_type=ReportTarget.REVIEW.value,
        target_id=review_id,
        reason=reason,
        at=now,
    )
    if hidden:
        await _close_reports_for(
            ReportTarget.REVIEW, review_id, moderator_id=moderator_id, at=now
        )
    return review


async def delete_agent(
    agent_id: str, *, moderator_id: uuid.UUID, reason: str | None
) -> bool:
    """Take down an abusive custom agent (cross-user). Returns whether it existed.

    ``agent_service`` is strictly owner-scoped, so a moderator deletes straight
    from the collection by id. Routable agents feed the orchestrator's routing
    catalog, so a malicious one can be auto-invoked — this is the lever to stop
    that.
    """
    now = _now()
    doc = await _agents().find_one_and_delete({"id": agent_id})
    if doc is None:
        return False
    await record_action(
        moderator_id,
        "agent_deleted",
        target_type="agent",
        target_id=agent_id,
        reason=reason,
        metadata={"owner_id": doc.get("user_id"), "name": doc.get("name")},
        at=now,
    )
    return True


# --- User actions (PostgreSQL) ---


async def _load_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def suspend_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    moderator: User,
    reason: str | None,
) -> User | None:
    """Lock an account out of the product surface. Returns None if not found.

    A moderator cannot suspend themselves — that would be a foot-gun that could
    lock the last admin out of the surface.
    """
    if user_id == moderator.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot suspend your own account.",
        )
    user = await _load_user(db, user_id)
    if user is None:
        return None
    if user.suspended_at is None:
        user.suspended_at = _now()
        await db.commit()
    await record_action(
        moderator.id,
        "user_suspended",
        target_type="user",
        target_id=str(user_id),
        reason=reason,
    )
    return user


async def unsuspend_user(
    db: AsyncSession, user_id: uuid.UUID, *, moderator: User
) -> User | None:
    """Lift a suspension. Returns None if the account does not exist."""
    user = await _load_user(db, user_id)
    if user is None:
        return None
    if user.suspended_at is not None:
        user.suspended_at = None
        await db.commit()
    await record_action(
        moderator.id,
        "user_unsuspended",
        target_type="user",
        target_id=str(user_id),
    )
    return user


async def set_user_role(
    db: AsyncSession,
    user_id: uuid.UUID,
    role: UserRole,
    *,
    moderator: User,
) -> User | None:
    """Promote/demote a user. Returns None if not found.

    A moderator cannot demote themselves, so an admin can never accidentally
    strip their own access (and potentially leave the platform with no admin).
    """
    if user_id == moderator.id and role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin role.",
        )
    user = await _load_user(db, user_id)
    if user is None:
        return None
    if user.role != role.value:
        user.role = role.value
        await db.commit()
    await record_action(
        moderator.id,
        "role_set",
        target_type="user",
        target_id=str(user_id),
        metadata={"role": role.value},
    )
    return user


async def list_users(
    db: AsyncSession, *, query: str | None, limit: int, offset: int
) -> list[User]:
    """List users (optionally filtered by an email substring), newest first."""
    stmt = sa.select(User)
    if query:
        stmt = stmt.where(User.email.ilike(f"%{query}%"))
    stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
    return list((await db.scalars(stmt)).all())


async def get_user_detail(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[str, Any] | None:
    """A user plus their moderation-relevant content counts, or None."""
    user = await _load_user(db, user_id)
    if user is None:
        return None
    uid = str(user_id)
    items = await _items().count_documents({"author_id": uid})
    agents = await _agents().count_documents({"user_id": uid})
    reviews = await _reviews().count_documents({"user_id": uid})
    return {
        "user": user,
        "counts": {"items": items, "agents": agents, "reviews": reviews},
    }


# --- Overview ---


async def overview(db: AsyncSession) -> dict[str, Any]:
    """Platform-wide moderation stats for the admin dashboard."""
    users_total = await db.scalar(sa.select(sa.func.count()).select_from(User)) or 0
    admins_total = (
        await db.scalar(
            sa.select(sa.func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN.value)
        )
        or 0
    )
    suspended_total = (
        await db.scalar(
            sa.select(sa.func.count())
            .select_from(User)
            .where(User.suspended_at.is_not(None))
        )
        or 0
    )

    items = _items()
    items_total = await items.count_documents({})
    items_hidden = await items.count_documents(
        {"status": MarketplaceStatus.HIDDEN.value}
    )
    items_removed = await items.count_documents(
        {"status": MarketplaceStatus.REMOVED.value}
    )
    reviews_total = await _reviews().count_documents({})
    open_reports = await _reports().count_documents({"status": ReportStatus.OPEN.value})

    recent_cursor = (
        items.find(_STRIP_ID).sort("created_at", -1).limit(ADMIN_RECENT_LIMIT)
    )
    recent_items = [
        {
            "id": doc["id"],
            "name": doc.get("name", ""),
            "domain": doc.get("domain", ""),
            "author_id": doc.get("author_id"),
            "status": doc.get("status", MarketplaceStatus.PUBLISHED.value),
            "created_at": doc.get("created_at"),
        }
        async for doc in recent_cursor
    ]
    return {
        "users_total": users_total,
        "admins_total": admins_total,
        "suspended_total": suspended_total,
        "items_total": items_total,
        "items_hidden": items_hidden,
        "items_removed": items_removed,
        "reviews_total": reviews_total,
        "open_reports": open_reports,
        "recent_items": recent_items,
    }
