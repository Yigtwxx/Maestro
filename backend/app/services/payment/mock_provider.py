"""In-process payment provider for development and tests.

No network, no dependencies, no real money. It validates cards exactly as a
real processor would (Luhn, accepted scheme, expiry) so the surrounding code is
exercised honestly, then returns synthetic identifiers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.core.constants import BILLING_PERIOD_DAYS, PAYMENT_PROVIDER_MOCK
from app.services.payment import card as card_utils
from app.services.payment.base import (
    CardDetails,
    ChargeResult,
    PaymentError,
    PaymentMethodToken,
    SubscriptionResult,
)

# A valid-Luhn Visa that the mock always refuses, so decline paths are testable.
DECLINE_TEST_CARD = "4000000000000002"

_ID_SUFFIX_LENGTH = 8


class MockPaymentProvider:
    """A ``PaymentProvider`` that approves any well-formed Visa or Mastercard."""

    name = PAYMENT_PROVIDER_MOCK

    def __init__(self) -> None:
        # Idempotency is process-local; a real provider keys this server-side.
        self._charges: dict[str, ChargeResult] = {}
        self._subscriptions: dict[str, SubscriptionResult] = {}

    async def create_payment_method(self, card: CardDetails) -> PaymentMethodToken:
        number = card_utils.sanitize(card.number)
        if not card_utils.luhn_valid(number):
            raise PaymentError("The card number is invalid.")

        brand = card_utils.detect_brand(number)
        if brand is None:
            raise PaymentError("Only Visa and Mastercard are accepted.")

        if not card_utils.card_not_expired(
            card.exp_month, card.exp_year, now=date.today()
        ):
            raise PaymentError("The card has expired.")

        if number == DECLINE_TEST_CARD:
            raise PaymentError("The card was declined.")

        suffix = uuid.uuid4().hex[:_ID_SUFFIX_LENGTH]
        return PaymentMethodToken(
            provider_payment_method_id=f"pm_{card_utils.last4(number)}_{suffix}",
            brand=brand.value,
            last4=card_utils.last4(number),
            exp_month=card.exp_month,
            exp_year=card.exp_year,
        )

    async def charge(
        self,
        *,
        amount_cents: int,
        currency: str,
        payment_method_id: str,
        idempotency_key: str,
        description: str,
    ) -> ChargeResult:
        cached = self._charges.get(idempotency_key)
        if cached is not None:
            return cached

        result = ChargeResult(
            charge_id=f"ch_{uuid.uuid4().hex}",
            amount_cents=amount_cents,
            currency=currency,
            approved=True,
        )
        self._charges[idempotency_key] = result
        return result

    async def create_subscription(
        self,
        *,
        plan: str,
        payment_method_id: str,
        first_amount_cents: int,
        recurring_amount_cents: int,
        idempotency_key: str,
    ) -> SubscriptionResult:
        cached = self._subscriptions.get(idempotency_key)
        if cached is not None:
            return cached

        await self.charge(
            amount_cents=first_amount_cents,
            currency="usd",
            payment_method_id=payment_method_id,
            idempotency_key=f"{idempotency_key}:first",
            description=f"First period of the {plan} plan",
        )

        now = datetime.now(UTC)
        result = SubscriptionResult(
            provider_subscription_id=f"sub_{uuid.uuid4().hex}",
            provider_customer_id=f"cus_{uuid.uuid4().hex}",
            current_period_start=now,
            current_period_end=now + timedelta(days=BILLING_PERIOD_DAYS),
        )
        self._subscriptions[idempotency_key] = result
        return result

    async def cancel_subscription(self, provider_subscription_id: str) -> None:
        """Nothing to cancel remotely; the local row carries the state."""
        return None
