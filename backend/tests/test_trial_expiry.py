"""Unit tests for lazy subscription-status resolution.

There is no scheduler, so a subscription cancelled mid-period keeps its stored
status until the period ends. Expiry is resolved at read time -- these tests
pin that behaviour. There is no trial: only an active plan may consume quota.
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
    period_end: datetime | None = None,
) -> Subscription:
    return Subscription(
        user_id=uuid.uuid4(),
        plan=SubscriptionPlan.STARTER.value,
        status=status.value,
        current_period_start=_NOW - timedelta(days=1),
        current_period_end=period_end or (_NOW + timedelta(days=29)),
        trial_end=None,
    )


def test_resolve_effective_status_none_is_inactive() -> None:
    assert billing_service.resolve_effective_status(None) is SubscriptionStatus.INACTIVE


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
        (SubscriptionStatus.ACTIVE, True),
        (SubscriptionStatus.PAST_DUE, False),
        (SubscriptionStatus.INACTIVE, False),
    ],
)
def test_is_active(status: SubscriptionStatus, expected: bool) -> None:
    subscription = _subscription(status)
    assert billing_service.is_active(subscription) is expected, f"Failed for {status}"
