"""User account service: cross-store erasure and data export.

Account data lives in three stores. A purge must clear all of them:

* PostgreSQL -- the ``users`` row plus everything cascading off it. Deleted by
  the caller, always LAST: the ``deletion_requested_at`` flag on that row is how
  the sweep re-finds an account, so losing it before Mongo and Qdrant are clean
  would orphan data with no way back.
* MongoDB -- task sessions, agent logs, custom agent configs, documents.
* Qdrant -- conversation memories and document chunks.

Unlike the old best-effort version, ``purge_user_data`` RAISES when a store is
unreachable. It runs inside the purge sweep, which catches per user, leaves the
flag set, and retries on the next run. Every operation here is idempotent, so
at-least-once execution is safe.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    MARKETPLACE_COMMUNITY_AUTHOR,
    QDRANT_CONVERSATION_MEMORIES,
    QDRANT_DOCUMENT_CHUNKS,
    MongoCollection,
)
from app.core.database import get_mongo_db
from app.models.usage_record import UsageRecord
from app.models.user import User
from app.services import billing_service, marketplace_service, memory_service

logger = logging.getLogger(__name__)

# Purged wholesale on account deletion, keyed by `user_id`. `agent_logs` is
# handled separately (see below) and `marketplace_items` is anonymized, not
# deleted: community content outlives the author's account.
# `marketplace_installs` is deliberately absent: install events are anonymous
# ({item_id, created_at} only), so there is nothing to erase.
# `marketplace_reviews` is also handled separately: deleting a review must
# recompute the item's denormalized aggregates, so a plain delete_many won't do.
_USER_SCOPED_COLLECTIONS = (
    MongoCollection.TASK_SESSIONS,
    MongoCollection.AGENT_CONFIGURATIONS,
    MongoCollection.DOCUMENTS,
    # Execution trace spans carry user_id (Backend v2 §4.5); erased wholesale.
    MongoCollection.TRACE_SPANS,
    # Registered endpoints, each holding an encrypted credential of the user's.
    MongoCollection.CUSTOM_API_TOOLS,
)


async def _purge_agent_logs(db: Any, user_id: uuid.UUID) -> None:
    """Delete the user's agent logs, including rows written before `user_id`.

    Early log documents carry only `task_id` (the write path did not stamp the
    owner), so they are matched through the user's task sessions. This MUST run
    before `task_sessions` is deleted or the task-id list is gone.
    """
    task_ids = await db[MongoCollection.TASK_SESSIONS.value].distinct(
        "task_id", {"user_id": str(user_id)}
    )
    criteria: list[dict[str, Any]] = [{"user_id": str(user_id)}]
    if task_ids:
        criteria.append({"task_id": {"$in": task_ids}})
    await db[MongoCollection.AGENT_LOGS.value].delete_many({"$or": criteria})


async def _anonymize_marketplace_items(db: Any, user_id: uuid.UUID) -> None:
    """Sever the author link on published items instead of deleting them.

    Erasure (GDPR Art.17) is satisfied once the content can no longer be tied to
    an identified person (Recital 26). The items themselves stay: other users
    have installed them, and deleting their agent teams to honour someone else's
    erasure request would be disproportionate.
    """
    await db[MongoCollection.MARKETPLACE_ITEMS.value].update_many(
        {"author_id": str(user_id)},
        {
            "$unset": {"author_id": ""},
            "$set": {"author_label": MARKETPLACE_COMMUNITY_AUTHOR},
        },
    )


async def purge_user_data(user_id: uuid.UUID) -> None:
    """Irreversibly erase the user's MongoDB documents and Qdrant vectors.

    Raises on any store failure so the caller can retry. Does NOT touch
    PostgreSQL -- the caller deletes that row last.
    """
    db = get_mongo_db()

    await _purge_agent_logs(db, user_id)
    for collection in _USER_SCOPED_COLLECTIONS:
        await db[collection.value].delete_many({"user_id": str(user_id)})
    await marketplace_service.purge_user_reviews(user_id)
    await _anonymize_marketplace_items(db, user_id)

    await memory_service.purge_user_vectors(user_id)
    logger.info("Purged Mongo + Qdrant data for user %s", user_id)


def _serialize(document: dict[str, Any]) -> dict[str, Any]:
    """Drop Mongo's internal `_id` and make values JSON-encodable."""
    return {key: value for key, value in document.items() if key != "_id"}


async def export_user_data(db: AsyncSession, user: User) -> dict[str, Any]:
    """Assemble everything the platform holds about a user (GDPR Art.20).

    Secrets never appear: BYOK keys stay encrypted at rest and are not included,
    and the card record carries only brand/last4/expiry -- never a PAN.
    """
    mongo = get_mongo_db()
    subscription = await billing_service.get_subscription(db, user.id)
    payment_method = await billing_service.get_payment_method(db, user.id)
    usage = (
        await db.scalars(select(UsageRecord).where(UsageRecord.user_id == user.id))
    ).all()

    async def _find(
        collection: MongoCollection, exclude: tuple[str, ...] = ()
    ) -> list[dict[str, Any]]:
        projection = {name: 0 for name in exclude} or None
        cursor = mongo[collection.value].find({"user_id": str(user.id)}, projection)
        return [_serialize(doc) async for doc in cursor]

    return {
        "profile": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "bio": user.bio,
            "avatar_color": user.avatar_color,
            "avatar_emoji": user.avatar_emoji,
            "timezone": user.timezone,
            "default_reviewer_enabled": user.default_reviewer_enabled,
            "default_tracing_enabled": user.default_tracing_enabled,
            # Status only. The TOTP secret and recovery-code hashes are never
            # exported (they are credentials, not personal data to hand back).
            "two_factor_enabled": user.totp_enabled,
            "subscription_tier": user.subscription_tier,
            "default_provider": user.default_provider,
            "model_preferences": user.model_preferences,
            "created_at": user.created_at.isoformat(),
            "deletion_requested_at": (
                user.deletion_requested_at.isoformat()
                if user.deletion_requested_at is not None
                else None
            ),
        },
        "subscription": (
            {
                "plan": subscription.plan,
                "status": subscription.status,
                "current_period_start": subscription.current_period_start.isoformat(),
                "current_period_end": subscription.current_period_end.isoformat(),
                "cancel_at_period_end": subscription.cancel_at_period_end,
            }
            if subscription is not None
            else None
        ),
        "payment_method": (
            {
                "brand": payment_method.brand,
                "last4": payment_method.last4,
                "exp_month": payment_method.exp_month,
                "exp_year": payment_method.exp_year,
            }
            if payment_method is not None
            else None
        ),
        "usage_records": [
            {
                "task_id": record.task_id,
                "tokens": record.tokens,
                "provider": record.provider,
                "status": record.status,
                "period_start": record.period_start.isoformat(),
            }
            for record in usage
        ],
        "tasks": await _find(MongoCollection.TASK_SESSIONS),
        "agents": await _find(MongoCollection.AGENT_CONFIGURATIONS),
        "documents": await _find(MongoCollection.DOCUMENTS),
        "marketplace_reviews": await _find(MongoCollection.MARKETPLACE_REVIEWS),
        # The endpoint definitions, never the stored credential: an export is a
        # file the user downloads and forwards, and ciphertext has no business
        # in it. `secret_hint` still travels, so a key is identifiable.
        "custom_api_tools": await _find(
            MongoCollection.CUSTOM_API_TOOLS, exclude=("encrypted_secret",)
        ),
        "conversation_memories": await memory_service.export_user_texts(
            user.id, QDRANT_CONVERSATION_MEMORIES
        ),
        "document_chunks": await memory_service.export_user_texts(
            user.id, QDRANT_DOCUMENT_CHUNKS
        ),
    }
