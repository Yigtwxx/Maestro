"""Billing service.

Two responsibilities:

1. Subscription lifecycle -- trials, subscribing, cancelling -- backed by
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
    FIRST_MONTH_DISCOUNT_RATE,
    PLAN_MONTHLY_TOKEN_QUOTA,
    PLAN_PRICE_USD_CENTS,
    PROVIDER_COST_PER_1K_TOKENS,
    TRIAL_DURATION_DAYS,
    TRIAL_PLAN,
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

_TERMINAL = {
    TaskStatus.COMPLETED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
    TaskStatus.TIMEOUT.value,
}


def _tokens_of(doc: dict[str, Any]) -> int:
    """Extract the total token count recorded on a task session."""
    metadata = doc.get("metadata") or {}
    return int(metadata.get("total_tokens", 0))


async def _fetch_sessions(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Load all task sessions owned by a user (metadata fields only)."""
    cursor = get_mongo_db()[MongoCollection.TASK_SESSIONS.value].find(
        {"user_id": str(user_id)},
        {"_id": 0, "status": 1, "provider": 1, "metadata": 1},
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
    failed = sum(
        1
        for d in docs
        if d.get("status") in {TaskStatus.FAILED.value, TaskStatus.TIMEOUT.value}
    )
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
    """High-level metrics for the dashboard."""
    docs = await _fetch_sessions(user_id)
    return aggregate_metrics(docs)


async def cost_summary(user_id: uuid.UUID) -> dict[str, Any]:
    """Estimated cost summary for the dashboard."""
    docs = await _fetch_sessions(user_id)
    return aggregate_cost(docs)


# --- Subscription lifecycle -----------------------------------------------


def plan_quota(plan: str) -> int:
    """Monthly token allowance for a plan."""
    return PLAN_MONTHLY_TOKEN_QUOTA[plan]


def first_month_price_cents(plan: str, *, discount_eligible: bool) -> int:
    """Price of the first period, applying the once-per-user discount."""
    base = PLAN_PRICE_USD_CENTS[plan]
    if not discount_eligible:
        return base
    return round(base * (1 - FIRST_MONTH_DISCOUNT_RATE))


def _as_utc(value: datetime) -> datetime:
    """Timestamps are stored in UTC; SQLite hands them back without a tzinfo."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def resolve_effective_status(subscription: Subscription | None) -> SubscriptionStatus:
    """The status the subscription *actually* has right now.

    There is no scheduler in this build, so a lapsed trial or a subscription
    past its cancellation date still carries its old status in the database.
    Expiry is therefore resolved at read time.
    """
    if subscription is None:
        return SubscriptionStatus.INACTIVE

    status = SubscriptionStatus(subscription.status)
    now = datetime.now(UTC)

    if status is SubscriptionStatus.TRIALING:
        trial_end = subscription.trial_end
        if trial_end is not None and now > _as_utc(trial_end):
            return SubscriptionStatus.INACTIVE
    elif status is SubscriptionStatus.CANCELED:
        if now > _as_utc(subscription.current_period_end):
            return SubscriptionStatus.INACTIVE

    return status


def is_active(subscription: Subscription | None) -> bool:
    """Whether the subscription may consume quota."""
    return resolve_effective_status(subscription) in ACTIVE_SUBSCRIPTION_STATUSES


async def get_subscription(db: AsyncSession, user_id: uuid.UUID) -> Subscription | None:
    """The user's single subscription row, if any."""
    return await db.scalar(select(Subscription).where(Subscription.user_id == user_id))


async def get_payment_method(
    db: AsyncSession, user_id: uuid.UUID
) -> PaymentMethod | None:
    """The user's default card, if any."""
    return await db.scalar(
        select(PaymentMethod).where(PaymentMethod.user_id == user_id)
    )


async def start_trial(db: AsyncSession, user: User) -> Subscription:
    """Put a newly registered user on a Starter-quota trial.

    Committed by the caller alongside whatever else it is doing.
    """
    now = datetime.now(UTC)
    trial_end = now + timedelta(days=TRIAL_DURATION_DAYS)
    subscription = Subscription(
        user_id=user.id,
        plan=TRIAL_PLAN.value,
        status=SubscriptionStatus.TRIALING.value,
        current_period_start=now,
        current_period_end=trial_end,
        trial_end=trial_end,
    )
    user.subscription_tier = TRIAL_PLAN.value
    db.add(subscription)
    return subscription


async def subscribe(
    db: AsyncSession,
    user: User,
    *,
    plan: SubscriptionPlan,
    card: CardDetails,
) -> Subscription:
    """Tokenize the card, charge the first period and activate the plan.

    The card number reaches the provider and nothing else. Everything below --
    the payment method, the subscription, the discount flag and the denormalized
    tier on ``users`` -- lands in one transaction, so the 50% first-month
    discount can never be claimed twice even under concurrent requests.

    Raises ``PaymentError`` if the provider refuses the card.
    """
    provider = get_payment_provider()
    token = await provider.create_payment_method(card)

    discount_eligible = not user.first_discount_used
    base_cents = PLAN_PRICE_USD_CENTS[plan.value]
    first_cents = first_month_price_cents(
        plan.value, discount_eligible=discount_eligible
    )

    now = datetime.now(UTC)
    result = await provider.create_subscription(
        plan=plan.value,
        payment_method_id=token.provider_payment_method_id,
        first_amount_cents=first_cents,
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

    if discount_eligible:
        user.first_discount_used = True
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
    await db.commit()
    await db.refresh(subscription)
    return subscription
