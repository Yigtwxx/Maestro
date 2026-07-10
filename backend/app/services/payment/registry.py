"""Payment provider lookup.

Registering a real processor is a two-line change here plus one new adapter
module; nothing that calls ``get_payment_provider`` needs to know.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.constants import PAYMENT_PROVIDER_MOCK
from app.services.payment.base import PaymentError, PaymentProvider
from app.services.payment.mock_provider import MockPaymentProvider


@lru_cache
def get_payment_provider() -> PaymentProvider:
    """Return the configured payment provider."""
    if settings.payment_provider == PAYMENT_PROVIDER_MOCK:
        return MockPaymentProvider()
    raise PaymentError(f"Unknown payment provider: {settings.payment_provider}")
