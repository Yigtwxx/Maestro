"""Token-usage ledger.

``usage_records`` in PostgreSQL is the authoritative source for quota. MongoDB
``task_sessions`` keeps the same numbers for dashboard analytics, but it is not
what enforcement reads.

Recording happens from the background task runner, outside any request scope,
so these helpers open their own session rather than depending on ``get_db``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models.subscription import Subscription
from app.models.usage_record import UsageRecord

logger = logging.getLogger(__name__)


async def used_tokens_this_period(
    db: AsyncSession, user_id: uuid.UUID, period_start: datetime
) -> int:
    """Total tokens the user has burned in the current billing window."""
    total = await db.scalar(
        select(func.coalesce(func.sum(UsageRecord.tokens), 0)).where(
            UsageRecord.user_id == user_id,
            UsageRecord.period_start == period_start,
        )
    )
    return int(total or 0)


async def record_task_usage(
    *,
    user_id: uuid.UUID,
    task_id: str,
    tokens: int,
    provider: str,
    status: str,
) -> None:
    """Charge a finished task's tokens to the user's current billing period.

    Called on every terminal path -- success, failure, timeout, cancellation --
    so tokens a doomed task already spent are still paid for. Idempotent on
    ``task_id``.
    """
    async with SessionLocal() as db:
        subscription = await db.scalar(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        if subscription is None:
            # No subscription row means nothing to charge against; the task
            # should not have started, but losing the token count is worse than
            # a stray log line.
            logger.warning("No subscription for user %s; usage not recorded", user_id)
            return

        db.add(
            UsageRecord(
                user_id=user_id,
                task_id=task_id,
                tokens=tokens,
                provider=provider,
                status=status,
                period_start=subscription.current_period_start,
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            # The unique task_id already recorded this task.
            await db.rollback()
