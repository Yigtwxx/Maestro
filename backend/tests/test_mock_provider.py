"""Unit tests for the mock payment provider."""

from __future__ import annotations

from dataclasses import fields

import pytest

from app.core.constants import CardBrand
from app.services.payment.base import CardDetails, PaymentError, PaymentMethodToken
from app.services.payment.mock_provider import DECLINE_TEST_CARD, MockPaymentProvider

_FUTURE_YEAR = 2030


def _card(number: str, *, exp_year: int = _FUTURE_YEAR) -> CardDetails:
    return CardDetails(
        number=number, exp_month=12, exp_year=exp_year, cvc="123", holder="A Person"
    )


@pytest.fixture
def provider() -> MockPaymentProvider:
    return MockPaymentProvider()


def test_payment_method_token_cannot_carry_a_card_number() -> None:
    """The type itself must make leaking the PAN impossible."""
    names = {f.name for f in fields(PaymentMethodToken)}
    assert "number" not in names, f"PaymentMethodToken exposes the PAN: {names}"


async def test_create_payment_method_returns_brand_and_last4(provider) -> None:
    token = await provider.create_payment_method(_card("4242 4242 4242 4242"))
    assert token.brand == CardBrand.VISA.value, f"Got brand {token.brand}"
    assert token.last4 == "4242", f"Got last4 {token.last4}"
    assert token.provider_payment_method_id.startswith("pm_")


async def test_create_payment_method_detects_mastercard(provider) -> None:
    token = await provider.create_payment_method(_card("5555555555554444"))
    assert token.brand == CardBrand.MASTERCARD.value, f"Got brand {token.brand}"


async def test_create_payment_method_rejects_bad_checksum(provider) -> None:
    with pytest.raises(PaymentError, match="invalid"):
        await provider.create_payment_method(_card("4242424242424243"))


async def test_create_payment_method_rejects_unsupported_scheme(provider) -> None:
    with pytest.raises(PaymentError, match="Visa and Mastercard"):
        await provider.create_payment_method(_card("6011111111111117"))


async def test_create_payment_method_rejects_expired_card(provider) -> None:
    with pytest.raises(PaymentError, match="expired"):
        await provider.create_payment_method(_card("4242424242424242", exp_year=2020))


async def test_create_payment_method_declines_the_test_card(provider) -> None:
    with pytest.raises(PaymentError, match="declined"):
        await provider.create_payment_method(_card(DECLINE_TEST_CARD))


async def test_charge_is_idempotent(provider) -> None:
    first = await provider.charge(
        amount_cents=1500,
        currency="usd",
        payment_method_id="pm_x",
        idempotency_key="key-1",
        description="test",
    )
    second = await provider.charge(
        amount_cents=1500,
        currency="usd",
        payment_method_id="pm_x",
        idempotency_key="key-1",
        description="test",
    )
    assert first.charge_id == second.charge_id, "Retry created a second charge"


async def test_create_subscription_is_idempotent(provider) -> None:
    kwargs = {
        "plan": "starter",
        "payment_method_id": "pm_x",
        "first_amount_cents": 750,
        "recurring_amount_cents": 1500,
        "idempotency_key": "sub-key-1",
    }
    first = await provider.create_subscription(**kwargs)
    second = await provider.create_subscription(**kwargs)
    assert first.provider_subscription_id == second.provider_subscription_id, (
        "Retry created a second subscription"
    )


async def test_create_subscription_period_is_thirty_days(provider) -> None:
    result = await provider.create_subscription(
        plan="pro",
        payment_method_id="pm_x",
        first_amount_cents=5000,
        recurring_amount_cents=5000,
        idempotency_key="sub-key-2",
    )
    span = result.current_period_end - result.current_period_start
    assert span.days == 30, f"Expected a 30-day period, got {span.days}"
