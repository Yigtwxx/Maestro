"""Billing request/response schemas.

``CardInput`` is input-only. No response model here carries a card number, and
nothing downstream of ``billing_service.subscribe`` ever sees one.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import SubscriptionPlan, SubscriptionStatus
from app.services.payment import card as card_utils

_MIN_EXP_YEAR = 2024
_MAX_EXP_YEAR = 2100


class CardInput(BaseModel):
    """A card as typed by the user. Validated here, then handed to the provider."""

    number: str = Field(min_length=12, max_length=25)
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=_MIN_EXP_YEAR, le=_MAX_EXP_YEAR)
    cvc: str = Field(min_length=3, max_length=4)
    holder: str = Field(min_length=1, max_length=120)

    @field_validator("number")
    @classmethod
    def _validate_number(cls, value: str) -> str:
        number = card_utils.sanitize(value)
        if not card_utils.luhn_valid(number):
            raise ValueError("The card number is invalid.")
        if card_utils.detect_brand(number) is None:
            raise ValueError("Only Visa and Mastercard are accepted.")
        return number

    @field_validator("cvc")
    @classmethod
    def _validate_cvc(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("The security code must be numeric.")
        return value

    @model_validator(mode="after")
    def _validate_expiry(self) -> CardInput:
        if not card_utils.card_not_expired(
            self.exp_month, self.exp_year, now=date.today()
        ):
            raise ValueError("The card has expired.")
        return self


class SubscribeRequest(BaseModel):
    plan: SubscriptionPlan
    card: CardInput


class PaymentMethodPublic(BaseModel):
    """The safe-to-display remnants of a card."""

    model_config = ConfigDict(from_attributes=True)

    brand: str
    last4: str
    exp_month: int
    exp_year: int


class PlanPublic(BaseModel):
    """A plan on the pricing page, priced for this particular user."""

    plan: SubscriptionPlan
    price_cents: int
    discounted_price_cents: int
    discount_eligible: bool
    quota_tokens: int
    currency: str


class PlanPublicListing(BaseModel):
    """A plan on the anonymous pricing page: list price, no personal discount.

    First-month eligibility hangs off ``users.first_discount_used``, which has
    no meaning before sign-up, so it is omitted rather than guessed at.
    """

    plan: SubscriptionPlan
    price_cents: int
    quota_tokens: int
    currency: str


class SubscriptionPublic(BaseModel):
    """The user's subscription plus where they stand against their quota."""

    plan: SubscriptionPlan
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    trial_end: datetime | None
    cancel_at_period_end: bool
    used_tokens: int
    quota_tokens: int
    first_discount_available: bool
    payment_method: PaymentMethodPublic | None
