"""Quota enforcement.

Guards the one place a task can begin (``POST /api/v1/tasks``). A task's token
cost is unknowable before it runs, so the rule is simply: you may start a task
if you have not already spent your monthly allowance. A single task can push
you over -- the next one is refused.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TASK_TOKEN_BUDGET_DEFAULT, UserRole
from app.core.database import SessionLocal
from app.models.user import User
from app.services import billing_service, usage_service

logger = logging.getLogger(__name__)

INACTIVE_DETAIL = "Your plan is inactive. Subscribe to start tasks."
QUOTA_EXHAUSTED_DETAIL = (
    "Monthly token quota exhausted. Upgrade your plan or wait for renewal."
)


@dataclass(slots=True, frozen=True)
class QuotaSnapshot:
    """Where a user stands against their allowance this period."""

    used_tokens: int
    quota_tokens: int


async def get_quota_snapshot(db: AsyncSession, user: User) -> QuotaSnapshot:
    """Tokens used and allowed in the user's current billing window."""
    subscription = await billing_service.get_subscription(db, user.id)
    if subscription is None:
        return QuotaSnapshot(used_tokens=0, quota_tokens=0)

    # Lazily roll the billing window forward if the period has elapsed, which
    # resets the monthly quota (usage is summed by exact period_start equality).
    subscription = await billing_service.sync_billing_period(db, subscription)

    used = await usage_service.used_tokens_this_period(
        db, user.id, subscription.current_period_start
    )
    return QuotaSnapshot(
        used_tokens=used, quota_tokens=billing_service.plan_quota(subscription.plan)
    )


def is_unmetered(user: User) -> bool:
    """Whether the user bypasses subscription + quota gating entirely.

    Admins run unmetered so the owner/staff can operate and test the platform
    without a metered plan blocking task start.
    """
    return user.role == UserRole.ADMIN.value


async def enforce_can_start_task(db: AsyncSession, user: User) -> None:
    """Refuse the task unless the user has an active plan with quota left."""
    if is_unmetered(user):
        return

    subscription = await billing_service.get_subscription(db, user.id)
    if not billing_service.is_active(subscription):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=INACTIVE_DETAIL
        )

    snapshot = await get_quota_snapshot(db, user)
    if snapshot.used_tokens >= snapshot.quota_tokens:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=QUOTA_EXHAUSTED_DETAIL,
        )


async def resolve_task_token_budget(user_id: uuid.UUID) -> int:
    """Task token cap = ``min(default, remaining monthly quota)`` (D19).

    The engine calls this at the execute-step boundary (outside any request), so
    it opens its own session. Best-effort: any error falls back to the default
    cap — a transient DB blip must never stall a task. A user already at quota
    yields 0, so the Main Agent skips the subagents and finishes with warnings.
    """
    try:
        async with SessionLocal() as db:
            user = await db.get(User, user_id)
            if user is None:
                return TASK_TOKEN_BUDGET_DEFAULT
            # Unmetered users are never throttled by remaining quota.
            if is_unmetered(user):
                return TASK_TOKEN_BUDGET_DEFAULT
            snapshot = await get_quota_snapshot(db, user)
            remaining = max(0, snapshot.quota_tokens - snapshot.used_tokens)
            return min(TASK_TOKEN_BUDGET_DEFAULT, remaining)
    except Exception:  # noqa: BLE001 - budget resolution is best-effort
        logger.warning("task budget resolution failed; using default", exc_info=True)
        return TASK_TOKEN_BUDGET_DEFAULT
