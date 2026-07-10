"""Unit tests for lazy subscription-status resolution.

There is no scheduler, so a lapsed trial keeps its stored status. Expiry is
resolved at read time -- these tests pin that behaviour.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.constants import SubscriptionPlan, SubscriptionStatus
from app.models.subscription import Subscription
from app.services import billing_service

_NOW = datetime.now(UTC)


def _subscription(
    status: SubscriptionStatus,
    *,
    trial_end: datetime | None = None,
    period_end: datetime | None = None,
) -> Subscription:
    return Subscription(
        user_id=uuid.uuid4(),
        plan=SubscriptionPlan.STARTER.value,
        status=status.value,
        current_period_start=_NOW - timedelta(days=1),
        current_period_end=period_end or (_NOW + timedelta(days=29)),
        trial_end=trial_end,
    )


def test_resolve_effective_status_none_is_inactive() -> None:
    assert billing_service.resolve_effective_status(None) is SubscriptionStatus.INACTIVE


def test_resolve_effective_status_live_trial_stays_trialing() -> None:
    subscription = _subscription(
        SubscriptionStatus.TRIALING, trial_end=_NOW + timedelta(days=3)
    )
    result = billing_service.resolve_effective_status(subscription)
    assert result is SubscriptionStatus.TRIALING, f"Got {result}"


def test_resolve_effective_status_lapsed_trial_is_inactive() -> None:
    subscription = _subscription(
        SubscriptionStatus.TRIALING, trial_end=_NOW - timedelta(seconds=1)
    )
    result = billing_service.resolve_effective_status(subscription)
    assert result is SubscriptionStatus.INACTIVE, f"Got {result}"


def test_resolve_effective_status_active_stays_active() -> None:
    subscription = _subscription(SubscriptionStatus.ACTIVE)
    result = billing_service.resolve_effective_status(subscription)
    assert result is SubscriptionStatus.ACTIVE, f"Got {result}"


def test_resolve_effective_status_canceled_before_period_end_still_usable() -> None:
    subscription = _subscription(
        SubscriptionStatus.CANCELED, period_end=_NOW + timedelta(days=5)
    )
    result = billing_service.resolve_effective_status(subscription)
    assert result is SubscriptionStatus.CANCELED, f"Got {result}"


def test_resolve_effective_status_canceled_past_period_end_is_inactive() -> None:
    subscription = _subscription(
        SubscriptionStatus.CANCELED, period_end=_NOW - timedelta(seconds=1)
    )
    result = billing_service.resolve_effective_status(subscription)
    assert result is SubscriptionStatus.INACTIVE, f"Got {result}"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (SubscriptionStatus.TRIALING, True),
        (SubscriptionStatus.ACTIVE, True),
        (SubscriptionStatus.PAST_DUE, False),
        (SubscriptionStatus.INACTIVE, False),
    ],
)
def test_is_active(status: SubscriptionStatus, expected: bool) -> None:
    subscription = _subscription(status, trial_end=_NOW + timedelta(days=3))
    assert billing_service.is_active(subscription) is expected, f"Failed for {status}"


@pytest.mark.parametrize(
    ("plan", "eligible", "expected"),
    [
        (SubscriptionPlan.STARTER, True, 750),
        (SubscriptionPlan.STARTER, False, 1500),
        (SubscriptionPlan.PRO, True, 2500),
        (SubscriptionPlan.PRO, False, 5000),
        (SubscriptionPlan.SCALE, True, 5000),
        (SubscriptionPlan.SCALE, False, 10000),
    ],
)
def test_first_month_price_cents(
    plan: SubscriptionPlan, eligible: bool, expected: int
) -> None:
    result = billing_service.first_month_price_cents(
        plan.value, discount_eligible=eligible
    )
    assert result == expected, f"Expected {expected} cents, got {result}"
