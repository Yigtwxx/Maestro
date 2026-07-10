"""Integration tests for /billing endpoints (SQLite-backed)."""

from __future__ import annotations

from app.core.constants import PLAN_MONTHLY_TOKEN_QUOTA, SubscriptionPlan

_EMAIL = "billing@user.com"
_PASSWORD = "supersecret"

_VISA = "4242 4242 4242 4242"
_MASTERCARD = "5555555555554444"
_DECLINED = "4000000000000002"

_STARTER_PRICE = 1500
_STARTER_DISCOUNTED = 750


def _card(number: str = _VISA) -> dict[str, object]:
    return {
        "number": number,
        "exp_month": 12,
        "exp_year": 2030,
        "cvc": "123",
        "holder": "A Person",
    }


async def _register_and_login(client, email: str = _EMAIL) -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "Billing"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _subscribe(client, headers, plan: str = "starter", number: str = _VISA):  # noqa: ANN001
    return await client.post(
        "/api/v1/billing/subscribe",
        headers=headers,
        json={"plan": plan, "card": _card(number)},
    )


async def test_register_starts_a_starter_trial(client) -> None:
    headers = await _register_and_login(client)
    resp = await client.get("/api/v1/billing/subscription", headers=headers)

    assert resp.status_code == 200, f"Got {resp.text}"
    body = resp.json()
    assert body["status"] == "trialing", f"Got status {body['status']}"
    assert body["plan"] == SubscriptionPlan.STARTER.value, f"Got plan {body['plan']}"
    assert body["quota_tokens"] == PLAN_MONTHLY_TOKEN_QUOTA["starter"]
    assert body["used_tokens"] == 0
    assert body["trial_end"] is not None, "A trial must have an end date"
    assert body["payment_method"] is None


async def test_billing_endpoints_require_auth(client) -> None:
    assert (await client.get("/api/v1/billing/subscription")).status_code == 401


async def test_plans_are_discounted_before_the_first_purchase(client) -> None:
    headers = await _register_and_login(client)
    resp = await client.get("/api/v1/billing/plans", headers=headers)

    assert resp.status_code == 200, f"Got {resp.text}"
    plans = {p["plan"]: p for p in resp.json()}
    assert len(plans) == 3, f"Expected 3 plans, got {list(plans)}"
    starter = plans["starter"]
    assert starter["price_cents"] == _STARTER_PRICE
    assert starter["discounted_price_cents"] == _STARTER_DISCOUNTED
    assert starter["discount_eligible"] is True


async def test_subscribe_activates_the_plan_and_stores_only_safe_card_data(
    client,
) -> None:
    headers = await _register_and_login(client)
    resp = await _subscribe(client, headers)

    assert resp.status_code == 200, f"Got {resp.text}"
    body = resp.json()
    assert body["status"] == "active", f"Got status {body['status']}"
    assert body["plan"] == "starter"
    assert body["trial_end"] is None, "Subscribing must end the trial"
    assert body["payment_method"] == {
        "brand": "visa",
        "last4": "4242",
        "exp_month": 12,
        "exp_year": 2030,
    }
    assert "number" not in resp.text, "The card number leaked into the response"
    assert "4242424242424242" not in resp.text, "The PAN leaked into the response"


async def test_subscribe_accepts_mastercard(client) -> None:
    headers = await _register_and_login(client)
    resp = await _subscribe(client, headers, number=_MASTERCARD)

    assert resp.status_code == 200, f"Got {resp.text}"
    assert resp.json()["payment_method"]["brand"] == "mastercard"


async def test_first_discount_is_consumed_once(client) -> None:
    headers = await _register_and_login(client)

    first = await _subscribe(client, headers)
    assert first.status_code == 200, f"Got {first.text}"
    assert first.json()["first_discount_available"] is False, (
        "The discount was not consumed"
    )

    plans = await client.get("/api/v1/billing/plans", headers=headers)
    starter = next(p for p in plans.json() if p["plan"] == "starter")
    assert starter["discount_eligible"] is False
    assert starter["discounted_price_cents"] == _STARTER_PRICE, (
        "The discount was offered a second time"
    )


async def test_discount_is_not_reclaimed_by_resubscribing(client) -> None:
    headers = await _register_and_login(client)
    await _subscribe(client, headers)
    await client.post("/api/v1/billing/cancel", headers=headers)

    resp = await _subscribe(client, headers, plan="pro")
    assert resp.status_code == 200, f"Got {resp.text}"
    assert resp.json()["first_discount_available"] is False, (
        "Cancelling and resubscribing reclaimed the first-month discount"
    )


async def test_subscribe_rejects_a_declined_card(client) -> None:
    headers = await _register_and_login(client)
    resp = await _subscribe(client, headers, number=_DECLINED)
    assert resp.status_code == 402, f"Expected 402, got {resp.status_code}: {resp.text}"


async def test_subscribe_rejects_an_unsupported_scheme(client) -> None:
    headers = await _register_and_login(client)
    resp = await _subscribe(client, headers, number="6011111111111117")
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


async def test_subscribe_rejects_a_bad_checksum(client) -> None:
    headers = await _register_and_login(client)
    resp = await _subscribe(client, headers, number="4242424242424243")
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


async def test_subscribe_upgrades_the_plan(client) -> None:
    headers = await _register_and_login(client)
    await _subscribe(client, headers)
    resp = await _subscribe(client, headers, plan="scale")

    assert resp.status_code == 200, f"Got {resp.text}"
    body = resp.json()
    assert body["plan"] == "scale", f"Got plan {body['plan']}"
    assert body["quota_tokens"] == PLAN_MONTHLY_TOKEN_QUOTA["scale"]

    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.json()["subscription_tier"] == "scale", "The cached tier drifted"


async def test_cancel_marks_the_subscription_for_non_renewal(client) -> None:
    headers = await _register_and_login(client)
    await _subscribe(client, headers)

    resp = await client.post("/api/v1/billing/cancel", headers=headers)
    assert resp.status_code == 200, f"Got {resp.text}"
    body = resp.json()
    assert body["cancel_at_period_end"] is True
    assert body["status"] == "canceled", f"Got status {body['status']}"


async def test_payment_method_is_absent_before_subscribing(client) -> None:
    headers = await _register_and_login(client)
    resp = await client.get("/api/v1/billing/payment-method", headers=headers)
    assert resp.status_code == 200, f"Got {resp.text}"
    assert resp.json() is None


async def test_payment_method_exposes_no_card_number(client) -> None:
    headers = await _register_and_login(client)
    await _subscribe(client, headers)

    resp = await client.get("/api/v1/billing/payment-method", headers=headers)
    assert resp.status_code == 200, f"Got {resp.text}"
    assert set(resp.json()) == {"brand", "last4", "exp_month", "exp_year"}, (
        f"Unexpected fields: {list(resp.json())}"
    )
