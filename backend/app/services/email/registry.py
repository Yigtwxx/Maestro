"""Email provider lookup.

Registering a real sender is a two-line change here plus one adapter module;
nothing that calls ``get_email_provider`` needs to know.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.constants import EMAIL_PROVIDER_CONSOLE, EMAIL_PROVIDER_RESEND
from app.services.email.base import EmailError, EmailProvider
from app.services.email.console import ConsoleEmailProvider
from app.services.email.resend import ResendProvider


@lru_cache
def get_email_provider() -> EmailProvider:
    """Return the configured email provider."""
    if settings.email_provider == EMAIL_PROVIDER_CONSOLE:
        return ConsoleEmailProvider()
    if settings.email_provider == EMAIL_PROVIDER_RESEND:
        return ResendProvider()
    raise EmailError(f"Unknown email provider: {settings.email_provider}")
