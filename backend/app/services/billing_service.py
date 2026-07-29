"""Billing service.

Two responsibilities:

1. Subscription lifecycle -- subscribing, cancelling -- backed by
   PostgreSQL and a pluggable ``PaymentProvider``.
2. Dashboard analytics -- token usage, success rates, estimated cost -- read
   from the MongoDB ``task_sessions`` collection (CLAUDE.md §8).

Aggregation is split into pure helper functions (no I/O) so it is unit-testable
without a live database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    BILLING_PERIOD_DAYS,
    PLAN_MONTHLY_TOKEN_QUOTA,
    PLAN_PRICE_USD_CENTS,
    PROVIDER_COST_PER_1K_TOKENS,
    TREND_WINDOW_DAYS,
    LLMProvider,
    MongoCollection,
    SubscriptionPlan,
    SubscriptionStatus,
    TaskStatus,
)
from app.core.database import get_mongo_db
from app.models.payment_method import PaymentMethod
from app.models.subscription import Subscription
from app.models.user import User
from app.services.payment import CardDetails, get_payment_provider
from app.utils.timeseries import as_utc, day_index, utc_day_window

_TERMINAL = {
    TaskStatus.COMPLETED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
    TaskStatus.TIMEOUT.value,
}

# The dashboard's "failed" bucket: a timeout is a failure the user experienced.
_FAILED = {TaskStatus.FAILED.value, TaskStatus.TIMEOUT.value}


def _tokens_of(doc: dict[str, Any]) -> int:
    """Extract the total token count recorded on a task session."""
    metadata = doc.get("metadata") or {}
    return int(metadata.get("total_tokens", 0))


async def _fetch_sessions(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Load all task sessions owned by a user (metadata fields only)."""
    cursor = get_mongo_db()[MongoCollection.TASK_SESSIONS.value].find(
        {"user_id": str(user_id)},
        {"_id": 0, "status": 1, "provider": 1, "metadata": 1, "created_at": 1},
    )
    return [doc async for doc in cursor]


def aggregate_usage(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize token usage and success rate across task sessions."""
    total_tokens = sum(_tokens_of(d) for d in docs)
    terminal = [d for d in docs if d.get("status") in _TERMINAL]
    completed = [d for d in docs if d.get("status") == TaskStatus.COMPLETED.value]
    by_provider: dict[str, dict[str, int]] = {}
    for doc in docs:
        provider = doc.get("provider", LLMProvider.OLLAMA.value)
        bucket = by_provider.setdefault(provider, {"tasks": 0, "tokens": 0})
        bucket["tasks"] += 1
        bucket["tokens"] += _tokens_of(doc)
    success_rate = round(len(completed) / len(terminal), 4) if terminal else 0.0
    return {
        "total_tokens": total_tokens,
        "total_tasks": len(docs),
        "success_rate": success_rate,
        "by_provider": by_provider,
    }


def aggregate_metrics(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """High-level dashboard counters."""
    usage = aggregate_usage(docs)
    running = sum(1 for d in docs if d.get("status") == TaskStatus.RUNNING.value)
    completed = sum(1 for d in docs if d.get("status") == TaskStatus.COMPLETED.value)
    failed = sum(1 for d in docs if d.get("status") in _FAILED)
    avg_tokens = round(usage["total_tokens"] / usage["total_tasks"]) if docs else 0
    return {
        "total_tasks": usage["total_tasks"],
        "running_tasks": running,
        "completed_tasks": completed,
        "failed_tasks": failed,
        "success_rate": usage["success_rate"],
        "total_tokens": usage["total_tokens"],
        "avg_tokens_per_task": avg_tokens,
    }


def aggregate_trends(
    docs: list[dict[str, Any]],
    *,
    now: datetime,
    days: int = TREND_WINDOW_DAYS,
) -> dict[str, Any]:
    """Per-UTC-day series feeding the dashboard sparklines (last ``days`` days).

    Tasks are attributed to the day they were created. Days with no terminal
    tasks report ``success_rate = None`` and days with no tasks at all report
    ``avg_tokens_per_task = None`` — an honest gap, never a fabricated zero.
    Documents without a ``created_at`` (legacy) or outside the window are
    skipped.
    """
    window = utc_day_window(now, days)
    size = len(window)
    tasks = [0] * size
    completed = [0] * size
    failed = [0] * size
    terminal = [0] * size
    tokens = [0] * size

    for doc in docs:
        created_at = doc.get("created_at")
        if not isinstance(created_at, datetime):
            continue
        index = day_index(created_at, window)
        if index is None:
            continue
        status = doc.get("status")
        tasks[index] += 1
        tokens[index] += _tokens_of(doc)
        if status == TaskStatus.COMPLETED.value:
            completed[index] += 1
        if status in _FAILED:
            failed[index] += 1
        if status in _TERMINAL:
            terminal[index] += 1

    success_rate = [
        round(completed[i] / terminal[i], 4) if terminal[i] else None
        for i in range(size)
    ]
    avg_tokens_per_task = [
        round(tokens[i] / tasks[i]) if tasks[i] else None for i in range(size)
    ]
    return {
        "window_days": days,
        "days": [day.isoformat() for day in window],
        "tasks": tasks,
        "completed": completed,
        "failed": failed,
        "tokens": tokens,
        "success_rate": success_rate,
        "avg_tokens_per_task": avg_tokens_per_task,
    }


def aggregate_cost(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate USD cost per provider from token usage."""
    by_provider: dict[str, float] = {}
    for doc in docs:
        provider = doc.get("provider", LLMProvider.OLLAMA.value)
        rate = PROVIDER_COST_PER_1K_TOKENS.get(provider, 0.0)
        cost = (_tokens_of(doc) / 1000) * rate
        by_provider[provider] = round(by_provider.get(provider, 0.0) + cost, 6)
    return {
        "currency": "USD",
        "total_cost": round(sum(by_provider.values()), 6),
        "by_provider": by_provider,
    }


async def usage_summary(user_id: uuid.UUID) -> dict[str, Any]:
    """Token usage summary for the dashboard."""
    docs = await _fetch_sessions(user_id)
    return {"user_id": str(user_id), **aggregate_usage(docs)}


async def metrics_summary(user_id: uuid.UUID) -> dict[str, Any]:
    """High-level metrics plus the daily trend series for the dashboard."""
    docs = await _fetch_sessions(user_id)
    return {
        **aggregate_metrics(docs),
        "trends": aggregate_trends(docs, now=datetime.now(UTC)),
    }


async def cost_summary(user_id: uuid.UUID) -> dict[str, Any]:
    """Estimated cost summary for the dashboard."""
    docs = await _fetch_sessions(user_id)
    return aggregate_cost(docs)


# --- Subscription lifecycle -----------------------------------------------


def plan_quota(plan: str) -> int:
    """Monthly token allowance for a plan (UNLIMITED_TOKEN_QUOTA = no ceiling)."""
    return PLAN_MONTHLY_TOKEN_QUOTA[plan]


def is_unlimited_quota(quota_tokens: int) -> bool:
    """Whether an allowance is the unlimited sentinel rather than a real cap.

    One definition, shared by the quota checks and the API response, so a new
    caller cannot invent its own idea of what a negative allowance means.
    """
    return quota_tokens < 0


def resolve_effective_status(subscription: Subscription | None) -> SubscriptionStatus:
    """The status the subscription *actually* has right now.

    There is no scheduler in this build, so a subscription past its cancellation
    date still carries its old status in the database. Expiry is therefore
    resolved at read time.
    """
    if subscription is None:
        return SubscriptionStatus.INACTIVE

    status = SubscriptionStatus(subscription.status)
    now = datetime.now(UTC)

    if status is SubscriptionStatus.CANCELED:
        if now > as_utc(subscription.current_period_end):
            return SubscriptionStatus.INACTIVE

    return status


def is_active(subscription: Subscription | None) -> bool:
    """Whether the subscription may consume quota."""
    return resolve_effective_status(subscription) in ACTIVE_SUBSCRIPTION_STATUSES


async def sync_billing_period(
    db: AsyncSession, subscription: Subscription | None
) -> Subscription | None:
    """Roll an ACTIVE subscription's window forward to cover ``now``.

    There is no billing scheduler in this build, so period renewal is resolved
    lazily at read time -- the same pattern as ``resolve_effective_status``.
    Because usage is summed by exact ``period_start`` equality
    (``usage_service.used_tokens_this_period``), advancing the window alone
    resets the monthly quota; no ledger rewrite is needed.

    Only ACTIVE subscriptions renew. A canceled plan past its end resolves to
    INACTIVE and must NOT roll forward. With a real payment processor this is
    where a successful recurring charge would gate the advance; the mock
    provider charges nothing, so the window advances unconditionally.
    """
    if subscription is None:
        return None
    if resolve_effective_status(subscription) is not SubscriptionStatus.ACTIVE:
        return subscription

    now = datetime.now(UTC)
    end = as_utc(subscription.current_period_end)
    if now <= end:
        return subscription

    start = as_utc(subscription.current_period_start)
    period = timedelta(days=BILLING_PERIOD_DAYS)
    # Roll whole periods forward, keeping windows contiguous and aligned to the
    # original anchor, until ``now`` lands inside the current window. Bounded and
    # deterministic, so concurrent callers compute the identical target window.
    while now > end:
        start = end
        end = end + period

    subscription.current_period_start = start
    subscription.current_period_end = end
    await db.commit()
    await db.refresh(subscription)
    return subscription


async def get_subscription(db: AsyncSession, user_id: uuid.UUID) -> Subscription | None:
    """The user's single subscription row, if any."""
    return await db.scalar(select(Subscription).where(Subscription.user_id == user_id))


async def ensure_free_subscription(
    db: AsyncSession, user: User, *, now: datetime | None = None
) -> Subscription:
    """Put the user on the active FREE plan unless they already hold an active one.

    Two callers: registration and ``scripts.grant_admin``. Registration is the
    load-bearing one -- ``usage_service.record_task_usage`` drops the record
    when there is no subscription row to anchor ``period_start`` to, so without
    this the dashboard's token and cost views would stay empty for everyone.

    Idempotent, and never downgrades an account that already holds an active
    plan. Does **not** commit: the caller owns the transaction, so the row lands
    with the user row it belongs to and the two can never diverge.
    """
    moment = now or datetime.now(UTC)
    subscription = await get_subscription(db, user.id)
    if subscription is not None and is_active(subscription):
        # Keep the display cache honest, but leave a paid plan alone.
        user.subscription_tier = subscription.plan
        return subscription

    plan = SubscriptionPlan.FREE.value
    if subscription is None:
        subscription = Subscription(user_id=user.id)
        db.add(subscription)
    subscription.plan = plan
    subscription.status = SubscriptionStatus.ACTIVE.value
    subscription.provider = PAYMENT_PROVIDER_MOCK
    subscription.provider_subscription_id = None
    subscription.provider_customer_id = None
    subscription.current_period_start = moment
    subscription.current_period_end = moment + timedelta(days=BILLING_PERIOD_DAYS)
    subscription.trial_end = None
    subscription.cancel_at_period_end = False
    user.subscription_tier = plan
    return subscription


async def get_payment_method(
    db: AsyncSession, user_id: uuid.UUID
) -> PaymentMethod | None:
    """The user's default card, if any."""
    return await db.scalar(
        select(PaymentMethod).where(PaymentMethod.user_id == user_id)
    )


async def subscribe(
    db: AsyncSession,
    user: User,
    *,
    plan: SubscriptionPlan,
    card: CardDetails,
) -> Subscription:
    """Tokenize the card, charge the first period and activate the plan.

    The card number reaches the provider and nothing else. Everything below --
    the payment method, the subscription and the denormalized tier on ``users``
    -- lands in one transaction. Every period is charged at the plan's full
    price; there is no trial and no first-month discount.

    Raises ``PaymentError`` if the provider refuses the card.
    """
    provider = get_payment_provider()
    token = await provider.create_payment_method(card)

    base_cents = PLAN_PRICE_USD_CENTS[plan.value]

    now = datetime.now(UTC)
    result = await provider.create_subscription(
        plan=plan.value,
        payment_method_id=token.provider_payment_method_id,
        first_amount_cents=base_cents,
        recurring_amount_cents=base_cents,
        idempotency_key=f"sub:{user.id}:{plan.value}:{int(now.timestamp())}",
    )

    payment_method = await get_payment_method(db, user.id)
    if payment_method is None:
        payment_method = PaymentMethod(user_id=user.id)
        db.add(payment_method)
    payment_method.provider = provider.name
    payment_method.provider_payment_method_id = token.provider_payment_method_id
    payment_method.brand = token.brand
    payment_method.last4 = token.last4
    payment_method.exp_month = token.exp_month
    payment_method.exp_year = token.exp_year
    payment_method.is_default = True

    subscription = await get_subscription(db, user.id)
    if subscription is None:
        subscription = Subscription(user_id=user.id)
        db.add(subscription)
    subscription.plan = plan.value
    subscription.status = SubscriptionStatus.ACTIVE.value
    subscription.provider = provider.name
    subscription.provider_subscription_id = result.provider_subscription_id
    subscription.provider_customer_id = result.provider_customer_id
    subscription.current_period_start = result.current_period_start
    subscription.current_period_end = result.current_period_end
    subscription.trial_end = None
    subscription.cancel_at_period_end = False

    user.subscription_tier = plan.value

    await db.commit()
    await db.refresh(subscription)
    return subscription


async def cancel(db: AsyncSession, user: User) -> Subscription | None:
    """Stop the subscription renewing; access lasts until the period ends."""
    subscription = await get_subscription(db, user.id)
    if subscription is None:
        return None

    provider = get_payment_provider()
    if subscription.provider_subscription_id is not None:
        await provider.cancel_subscription(subscription.provider_subscription_id)

    subscription.cancel_at_period_end = True
    subscription.status = SubscriptionStatus.CANCELED.value
    # user.subscription_tier is deliberately left set: the plan stays visible
    # until the period ends. Post-expiry sync is future scheduler work.
    await db.commit()
    await db.refresh(subscription)
    return subscription
