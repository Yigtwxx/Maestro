"""Tests for quota enforcement against the usage ledger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.core.constants import (
    PLAN_MONTHLY_TOKEN_QUOTA,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.subscription import Subscription
from app.models.usage_record import UsageRecord
from app.models.user import User
from app.services import billing_service, quota_service, usage_service
from app.utils.timeseries import as_utc

_STARTER_QUOTA = PLAN_MONTHLY_TOKEN_QUOTA[SubscriptionPlan.STARTER.value]


async def _make_user(
    db_session,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> User:
    now = datetime.now(UTC)
    start = period_start if period_start is not None else now
    end = period_end if period_end is not None else now + timedelta(days=30)
    email = f"{status.value}-{start.isoformat()}@quota.test"
    user = User(email=email, hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        Subscription(
            user_id=user.id,
            plan=SubscriptionPlan.STARTER.value,
            status=status.value,
            current_period_start=start,
            current_period_end=end,
            trial_end=None,
        )
    )
    await db_session.commit()
    return user


async def _add_usage(db_session, user: User, tokens: int, task_id: str) -> None:
    subscription = await billing_service.get_subscription(db_session, user.id)
    db_session.add(
        UsageRecord(
            user_id=user.id,
            task_id=task_id,
            tokens=tokens,
            provider="ollama",
            status="completed",
            period_start=subscription.current_period_start,
        )
    )
    await db_session.commit()


async def test_used_tokens_sums_the_period(db_session) -> None:
    user = await _make_user(db_session)
    await _add_usage(db_session, user, 1000, "task-1")
    await _add_usage(db_session, user, 2500, "task-2")

    subscription = await billing_service.get_subscription(db_session, user.id)
    used = await usage_service.used_tokens_this_period(
        db_session, user.id, subscription.current_period_start
    )
    assert used == 3500, f"Expected 3500 tokens, got {used}"


async def test_used_tokens_ignores_other_periods(db_session) -> None:
    user = await _make_user(db_session)
    await _add_usage(db_session, user, 1000, "task-1")

    stale_period = datetime.now(UTC) - timedelta(days=60)
    used = await usage_service.used_tokens_this_period(
        db_session, user.id, stale_period
    )
    assert used == 0, f"Expected 0 tokens for an old period, got {used}"


async def test_enforce_allows_an_active_user_under_quota(db_session) -> None:
    user = await _make_user(db_session)
    await _add_usage(db_session, user, 100, "task-1")
    await quota_service.enforce_can_start_task(db_session, user)


async def test_enforce_rejects_an_inactive_user(db_session) -> None:
    user = await _make_user(db_session, SubscriptionStatus.INACTIVE)
    with pytest.raises(HTTPException) as exc:
        await quota_service.enforce_can_start_task(db_session, user)
    assert exc.value.status_code == 402, f"Got {exc.value.status_code}"
    assert exc.value.detail == quota_service.INACTIVE_DETAIL


async def test_enforce_rejects_a_user_at_quota(db_session) -> None:
    user = await _make_user(db_session)
    await _add_usage(db_session, user, _STARTER_QUOTA, "task-1")

    with pytest.raises(HTTPException) as exc:
        await quota_service.enforce_can_start_task(db_session, user)
    assert exc.value.status_code == 402, f"Got {exc.value.status_code}"
    assert exc.value.detail == quota_service.QUOTA_EXHAUSTED_DETAIL


async def test_enforce_rejects_a_user_with_no_subscription(db_session) -> None:
    user = User(email="nosub@quota.test", hashed_password="x")
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await quota_service.enforce_can_start_task(db_session, user)
    assert exc.value.status_code == 402, f"Got {exc.value.status_code}"


async def test_quota_snapshot_reports_plan_allowance(db_session) -> None:
    user = await _make_user(db_session)
    await _add_usage(db_session, user, 4242, "task-1")

    snapshot = await quota_service.get_quota_snapshot(db_session, user)
    assert snapshot.used_tokens == 4242, f"Got {snapshot.used_tokens}"
    assert snapshot.quota_tokens == _STARTER_QUOTA, f"Got {snapshot.quota_tokens}"


async def test_expired_period_advances_and_resets_quota(db_session) -> None:
    now = datetime.now(UTC)
    # An ACTIVE plan whose window ended yesterday, with the previous period
    # exhausted to the quota cap.
    user = await _make_user(
        db_session,
        period_start=now - timedelta(days=31),
        period_end=now - timedelta(days=1),
    )
    await _add_usage(db_session, user, _STARTER_QUOTA, "task-old")

    # The elapsed period must renew: enforcement passes and usage reads zero.
    await quota_service.enforce_can_start_task(db_session, user)
    snapshot = await quota_service.get_quota_snapshot(db_session, user)
    assert snapshot.used_tokens == 0, f"Expected reset, got {snapshot.used_tokens}"

    subscription = await billing_service.get_subscription(db_session, user.id)
    start = as_utc(subscription.current_period_start)
    end = as_utc(subscription.current_period_end)
    assert start > now - timedelta(days=31), f"Window did not advance: {start}"
    assert start <= now < end, f"now not inside renewed window [{start}, {end})"


async def test_multiple_elapsed_periods_roll_forward(db_session) -> None:
    now = datetime.now(UTC)
    # Gone for ~75 days: several whole periods have elapsed.
    user = await _make_user(
        db_session,
        period_start=now - timedelta(days=105),
        period_end=now - timedelta(days=75),
    )

    subscription = await billing_service.get_subscription(db_session, user.id)
    subscription = await billing_service.sync_billing_period(db_session, subscription)
    start = as_utc(subscription.current_period_start)
    end = as_utc(subscription.current_period_end)
    assert start <= now < end, f"now not inside window [{start}, {end})"


async def test_active_within_period_is_unchanged(db_session) -> None:
    user = await _make_user(db_session)
    subscription = await billing_service.get_subscription(db_session, user.id)
    original_start = subscription.current_period_start

    subscription = await billing_service.sync_billing_period(db_session, subscription)
    assert subscription.current_period_start == original_start, (
        f"Fresh window should not move: {subscription.current_period_start}"
    )


async def test_canceled_expired_does_not_renew(db_session) -> None:
    now = datetime.now(UTC)
    user = await _make_user(
        db_session,
        SubscriptionStatus.CANCELED,
        period_start=now - timedelta(days=31),
        period_end=now - timedelta(days=1),
    )
    subscription = await billing_service.get_subscription(db_session, user.id)
    original_end = subscription.current_period_end

    subscription = await billing_service.sync_billing_period(db_session, subscription)
    assert subscription.current_period_end == original_end, (
        "Canceled plan past its end must not roll forward"
    )
    # And it resolves to inactive, so a task is still refused.
    with pytest.raises(HTTPException) as exc:
        await quota_service.enforce_can_start_task(db_session, user)
    assert exc.value.status_code == 402, f"Got {exc.value.status_code}"
