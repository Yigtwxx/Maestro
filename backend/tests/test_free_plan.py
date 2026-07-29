"""The FREE plan: unlimited quota, provisioned at registration, not cancelable.

The properties that matter here are the ones that fail *silently* if broken --
a zero task budget and a dropped usage record both look like nothing happened.
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.constants import (
    TASK_TOKEN_BUDGET_DEFAULT,
    UNLIMITED_TOKEN_QUOTA,
    SubscriptionPlan,
    SubscriptionStatus,
    UserRole,
)
from app.models import Subscription, User
from app.services import billing_service, quota_service

_EMAIL = "free@example.com"
_PASSWORD = "password123"


async def _register_and_login(client, email=_EMAIL):
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": _PASSWORD}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _user(db_session, email=_EMAIL) -> User:
    return await db_session.scalar(select(User).where(User.email == email))


async def test_registration_provisions_an_active_free_subscription(
    client, db_session
) -> None:
    await _register_and_login(client)

    user = await _user(db_session)
    subscription = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id)
    )

    assert subscription is not None, "registration must leave a row to bill against"
    assert subscription.plan == SubscriptionPlan.FREE.value
    assert subscription.status == SubscriptionStatus.ACTIVE.value
    assert user.subscription_tier == SubscriptionPlan.FREE.value


async def test_free_plan_carries_the_unlimited_sentinel(client, db_session) -> None:
    await _register_and_login(client)
    user = await _user(db_session)

    snapshot = await quota_service.get_quota_snapshot(db_session, user)

    assert snapshot.quota_tokens == UNLIMITED_TOKEN_QUOTA
    assert snapshot.unlimited is True


async def test_free_user_may_start_a_task(client, db_session) -> None:
    """The gate that used to answer 402 for every fresh account."""
    await _register_and_login(client)
    user = await _user(db_session)

    await quota_service.enforce_can_start_task(db_session, user)


async def test_free_user_keeps_the_full_task_token_budget(client, db_session) -> None:
    """The silent trap: `max(0, -1 - used)` is 0, and a 0 budget makes the Main
    Agent skip every subagent without raising anything."""
    await _register_and_login(client)
    user = await _user(db_session)
    await db_session.commit()

    budget = await quota_service.resolve_task_token_budget(user.id)

    assert budget == TASK_TOKEN_BUDGET_DEFAULT, (
        f"an unlimited plan must not be throttled, got {budget}"
    )


async def test_ensure_free_subscription_never_downgrades_an_active_plan(
    client, db_session
) -> None:
    await _register_and_login(client)
    user = await _user(db_session)
    subscription = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    subscription.plan = SubscriptionPlan.PRO.value
    user.subscription_tier = SubscriptionPlan.PRO.value
    await db_session.commit()

    result = await billing_service.ensure_free_subscription(db_session, user)

    assert result.plan == SubscriptionPlan.PRO.value, "a paid plan must survive"
    assert user.subscription_tier == SubscriptionPlan.PRO.value


async def test_ensure_free_subscription_revives_a_lapsed_plan(
    client, db_session
) -> None:
    await _register_and_login(client)
    user = await _user(db_session)
    subscription = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    subscription.plan = SubscriptionPlan.PRO.value
    subscription.status = SubscriptionStatus.CANCELED.value
    await db_session.commit()

    result = await billing_service.ensure_free_subscription(db_session, user)

    assert result.plan == SubscriptionPlan.FREE.value
    assert result.status == SubscriptionStatus.ACTIVE.value


async def test_free_plan_cannot_be_cancelled(client) -> None:
    """Cancelling would set status=canceled, fail is_active, and 402 every task
    start -- a self-inflicted lockout with no way back through the product."""
    headers = await _register_and_login(client)

    resp = await client.post("/api/v1/billing/cancel", headers=headers)

    assert resp.status_code == 403, resp.text
    sub = await client.get("/api/v1/billing/subscription", headers=headers)
    assert sub.json()["status"] == "active", "the plan must survive the attempt"


async def test_subscribe_is_refused_while_billing_is_parked(
    client, billing_off
) -> None:
    headers = await _register_and_login(client)

    resp = await client.post(
        "/api/v1/billing/subscribe",
        headers=headers,
        json={
            "plan": "pro",
            "card": {
                "number": "4242424242424242",
                "exp_month": 12,
                "exp_year": 2035,
                "cvc": "123",
                "holder": "Test User",
            },
        },
    )

    assert resp.status_code == 403, resp.text
    assert "coming soon" in resp.json()["detail"].lower()


async def test_admin_may_still_subscribe_while_billing_is_parked(
    client, db_session, billing_off
) -> None:
    """The owner has to be able to exercise the real flow before it opens."""
    headers = await _register_and_login(client, email="owner@example.com")
    user = await _user(db_session, "owner@example.com")
    user.role = UserRole.ADMIN.value
    await db_session.commit()

    resp = await client.post(
        "/api/v1/billing/subscribe",
        headers=headers,
        json={
            "plan": "pro",
            "card": {
                "number": "4242424242424242",
                "exp_month": 12,
                "exp_year": 2035,
                "cvc": "123",
                "holder": "Owner",
            },
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"] == "pro"


async def test_plans_listing_includes_free_first(client) -> None:
    headers = await _register_and_login(client)

    resp = await client.get("/api/v1/billing/plans", headers=headers)

    plans = [p["plan"] for p in resp.json()]
    assert plans[0] == "free", f"free must lead the listing, got {plans}"
