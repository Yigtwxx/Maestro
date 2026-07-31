"""Quota enforcement.

Guards the one place a task can begin (``POST /api/v1/tasks``). A task's token
cost is unknowable before it runs, so the rule is simply: you may start a task
if you have not already spent your monthly allowance. A single task can push
you over -- the next one is refused.

It also guards the one place a document can be uploaded, on a different axis:
tokens meter what an account *spends* per period, storage meters what it *keeps*
forever. An upload's cost, unlike a task's, is known before it runs, so that
gate is exact -- nothing is ever allowed to land over the ceiling.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    TASK_TOKEN_BUDGET_DEFAULT,
    SubscriptionPlan,
    UserRole,
)
from app.core.database import SessionLocal
from app.models.user import User
from app.services import billing_service, document_service, usage_service

logger = logging.getLogger(__name__)

# Unreachable for a normal account: registration provisions an active FREE plan
# and /billing/cancel refuses to cancel it. It stays reachable for a lapsed
# *paid* plan, so it must not tell that user to do something they cannot.
INACTIVE_DETAIL = "Your plan is inactive. Contact support to restore access."
QUOTA_EXHAUSTED_DETAIL = (
    "Monthly token quota exhausted. Upgrade your plan or wait for renewal."
)
# Names the ceiling and the two ways out, because unlike the quota message this
# one is transient: the user is not out of allowance, just out of slots.
CONCURRENCY_LIMIT_DETAIL = (
    "Your plan allows {limit} task(s) at a time and you are already running "
    "that many. Wait for one to finish, cancel it, or upgrade your plan."
)
# Storage is recoverable by the user without spending anything, so deleting
# comes first in both messages and upgrading second.
DOCUMENT_COUNT_LIMIT_DETAIL = (
    "Your plan allows {limit} documents and you already have that many. "
    "Delete one to make room, or upgrade your plan."
)
DOCUMENT_BYTES_LIMIT_DETAIL = (
    "This upload would put you over your plan's {limit} MB knowledge-base "
    "allowance ({used} MB used). Delete a document, or upgrade your plan."
)


@dataclass(slots=True, frozen=True)
class QuotaSnapshot:
    """Where a user stands against their allowance this period."""

    used_tokens: int
    quota_tokens: int

    @property
    def unlimited(self) -> bool:
        """Whether the plan has no ceiling (FREE). Guard before any arithmetic."""
        return billing_service.is_unlimited_quota(self.quota_tokens)


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
    # Must come before the comparison: the sentinel is negative, so
    # `used >= quota` would be true for every free user and refuse them all.
    if snapshot.unlimited:
        return
    if snapshot.used_tokens >= snapshot.quota_tokens:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=QUOTA_EXHAUSTED_DETAIL,
        )


async def resolve_task_concurrency_limit(db: AsyncSession, user: User) -> int | None:
    """How many tasks this user may hold in flight; ``None`` means no ceiling.

    Only unmetered (admin) accounts get ``None`` -- the operator has to be able
    to exercise and load-test the platform. A user with no subscription row
    resolves to the FREE ceiling rather than to "unlimited": the caller has
    already refused an inactive plan, so reaching this branch means something
    is wrong, and the strictest cap is the safe reading of it.
    """
    if is_unmetered(user):
        return None
    subscription = await billing_service.get_subscription(db, user.id)
    plan = (
        subscription.plan if subscription is not None else SubscriptionPlan.FREE.value
    )
    return billing_service.plan_concurrency_limit(plan)


@dataclass(slots=True, frozen=True)
class StorageSnapshot:
    """Where a user stands against their knowledge-base allowance.

    ``max_documents``/``max_bytes`` are ``None`` only for an unmetered (admin)
    account -- the same "no ceiling" reading as
    ``resolve_task_concurrency_limit``. Consumers must branch on it before any
    comparison rather than substituting a number of their own.
    """

    documents: int
    bytes: int
    max_documents: int | None
    max_bytes: int | None


async def _resolve_document_limits(
    db: AsyncSession, user: User
) -> tuple[int, int] | None:
    """``(max documents, max bytes)`` for this user; ``None`` if unmetered.

    A user with no subscription row resolves to the FREE ceiling rather than to
    "unlimited", for the same reason as the concurrency cap: reaching that
    branch means something is wrong, and the strictest cap is the safe reading.
    """
    if is_unmetered(user):
        return None
    subscription = await billing_service.get_subscription(db, user.id)
    plan = (
        subscription.plan if subscription is not None else SubscriptionPlan.FREE.value
    )
    return billing_service.plan_document_limits(plan)


async def get_storage_snapshot(db: AsyncSession, user: User) -> StorageSnapshot:
    """The user's current knowledge-base usage alongside their allowance."""
    usage = await document_service.storage_usage(user.id)
    limits = await _resolve_document_limits(db, user)
    max_documents, max_bytes = limits if limits is not None else (None, None)
    return StorageSnapshot(
        documents=usage.documents,
        bytes=usage.bytes,
        max_documents=max_documents,
        max_bytes=max_bytes,
    )


async def enforce_can_upload_document(
    db: AsyncSession, user: User, *, incoming_bytes: int
) -> None:
    """Refuse the upload unless it fits inside the plan's storage allowance.

    Called from the route before the body is chunked or embedded, so a rejected
    upload costs no embedding calls. Two accepted uploads racing each other can
    both observe the pre-insert usage and land, overshooting by at most one
    document: closing that would need a lock this datastore does not offer, and
    unlike the concurrency cap -- where a burst of simultaneous starts is the
    whole attack -- an upload is rate-limited to RATE_LIMIT_UPLOAD and the
    overshoot is one file, permanently correctable by the next check.
    """
    limits = await _resolve_document_limits(db, user)
    if limits is None:
        return
    max_documents, max_bytes = limits
    usage = await document_service.storage_usage(user.id)
    if usage.documents >= max_documents:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=DOCUMENT_COUNT_LIMIT_DETAIL.format(limit=max_documents),
        )
    if usage.bytes + incoming_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=DOCUMENT_BYTES_LIMIT_DETAIL.format(
                limit=max_bytes // 1_000_000, used=usage.bytes // 1_000_000
            ),
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
            # An unlimited plan is never throttled by "remaining". Without this
            # the sentinel makes the subtraction clamp to 0, and a 0 budget
            # makes the Main Agent skip every subagent -- silently, with no
            # error anywhere. This guard is why the sentinel is safe.
            if snapshot.unlimited:
                return TASK_TOKEN_BUDGET_DEFAULT
            remaining = max(0, snapshot.quota_tokens - snapshot.used_tokens)
            return min(TASK_TOKEN_BUDGET_DEFAULT, remaining)
    except Exception:  # noqa: BLE001 - budget resolution is best-effort
        logger.warning("task budget resolution failed; using default", exc_info=True)
        return TASK_TOKEN_BUDGET_DEFAULT
