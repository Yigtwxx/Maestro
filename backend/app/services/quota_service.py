"""Quota enforcement.

Guards the one place a task can begin (``POST /api/v1/tasks``). A task's token
cost is unknowable before it runs, so the rule is simply: you may start a task
if you have not already spent your monthly allowance. A single task can push
you over -- the next one is refused.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import billing_service, usage_service

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

    used = await usage_service.used_tokens_this_period(
        db, user.id, subscription.current_period_start
    )
    return QuotaSnapshot(
        used_tokens=used, quota_tokens=billing_service.plan_quota(subscription.plan)
    )


async def enforce_can_start_task(db: AsyncSession, user: User) -> None:
    """Refuse the task unless the user has an active plan with quota left."""
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
