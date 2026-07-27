"""CLAUDE.md rule 9: the raw card number (PAN) is never persisted, logged, or
returned. Only brand + last4 + expiry survive.

The flow under test is ``POST /billing/subscribe``, which is where a full PAN
enters the system. After a successful subscribe the persisted ``payment_methods``
row, the HTTP responses, and the captured logs are all inspected for the full
number.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.models.payment_method import PaymentMethod
from app.models.user import User

_PASSWORD = "supersecret"
_PAN = "4242424242424242"  # a valid-Luhn Visa the mock provider approves
_CARD = {
    "number": _PAN,
    "exp_month": 12,
    "exp_year": 2030,
    "cvc": "123",
    "holder": "A Person",
}


async def _register(client, email: str) -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "Payer"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_subscribe_persists_only_masked_card_never_the_pan(
    client, db_session, caplog
) -> None:
    headers = await _register(client, "payer@card.com")

    with caplog.at_level(logging.DEBUG):
        resp = await client.post(
            "/api/v1/billing/subscribe",
            headers=headers,
            json={"plan": "starter", "card": _CARD},
        )
    assert resp.status_code == 200, f"Subscribe failed: {resp.text}"

    # 1) The persisted row keeps the masked card and nothing more.
    user = await db_session.scalar(select(User).where(User.email == "payer@card.com"))
    row = await db_session.scalar(
        select(PaymentMethod).where(PaymentMethod.user_id == user.id)
    )
    assert row is not None, "subscribe must persist a payment method"
    assert row.last4 == "4242", f"Expected last4 4242, got {row.last4}"
    assert row.brand == "visa", f"Expected brand visa, got {row.brand}"
    assert row.exp_month == 12 and row.exp_year == 2030, "expiry must persist"

    stored_strings = " ".join(
        str(getattr(row, column))
        for column in ("provider", "provider_payment_method_id", "brand", "last4")
    )
    assert _PAN not in stored_strings, (
        f"Full PAN leaked into a persisted column: {stored_strings}"
    )

    # 2) The subscribe response exposes no PAN.
    assert _PAN not in resp.text, "The full PAN must never appear in a response body"

    # 3) The dedicated payment-method view exposes brand+last4 only, no PAN.
    view = await client.get("/api/v1/billing/payment-method", headers=headers)
    assert view.status_code == 200, view.text
    assert view.json()["last4"] == "4242", view.text
    assert _PAN not in view.text, "The payment-method view must never return the PAN"

    # 4) Nothing logged the full number, at any level.
    assert _PAN not in caplog.text, "The full PAN must never be written to logs"
