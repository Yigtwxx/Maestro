"""Payment provider seam.

Mirrors the LLM adapter pattern (``llm_service.LLMAdapter`` + ``get_adapter``):
adding a real processor -- iyzico, PayTR, Adyen, Stripe -- means adding one
adapter module, not editing the code that calls it.

Visa and Mastercard are card schemes, not processors. Real money always moves
through an acquirer, and accepting a raw PAN on our own servers would pull the
whole backend into PCI-DSS SAQ-D scope. So ``CardDetails`` is the only place a
PAN ever exists, it lives in memory for one call, and nothing downstream of a
provider sees more than ``PaymentMethodToken``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(slots=True, frozen=True)
class CardDetails:
    """Raw card input. Never persisted, never logged, never serialized."""

    number: str
    exp_month: int
    exp_year: int
    cvc: str
    holder: str


@dataclass(slots=True, frozen=True)
class PaymentMethodToken:
    """What a provider hands back once it has taken custody of the card."""

    provider_payment_method_id: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int


@dataclass(slots=True, frozen=True)
class ChargeResult:
    charge_id: str
    amount_cents: int
    currency: str
    approved: bool


@dataclass(slots=True, frozen=True)
class SubscriptionResult:
    provider_subscription_id: str
    provider_customer_id: str
    current_period_start: datetime
    current_period_end: datetime


class PaymentError(RuntimeError):
    """Raised when a payment provider rejects a request."""


class PaymentProvider(Protocol):
    """Interface every payment adapter must implement."""

    name: str

    async def create_payment_method(self, card: CardDetails) -> PaymentMethodToken:
        """Tokenize a card. Raises PaymentError on an invalid or refused card."""
        ...

    async def charge(
        self,
        *,
        amount_cents: int,
        currency: str,
        payment_method_id: str,
        idempotency_key: str,
        description: str,
    ) -> ChargeResult:
        """Take a one-off payment. Retrying with the same key must not double-charge."""
        ...

    async def create_subscription(
        self,
        *,
        plan: str,
        payment_method_id: str,
        first_amount_cents: int,
        recurring_amount_cents: int,
        idempotency_key: str,
    ) -> SubscriptionResult:
        """Start a recurring subscription, billing the first period separately.

        ``first_amount_cents`` and ``recurring_amount_cents`` are equal today;
        the split is kept so a future adapter could price the first period
        differently without an interface change.
        """
        ...

    async def cancel_subscription(self, provider_subscription_id: str) -> None:
        """Stop the subscription from renewing."""
        ...
