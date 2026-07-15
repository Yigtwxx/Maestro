"""Provider-agnostic transactional email layer."""

from app.services.email.base import EmailError, EmailMessage, EmailProvider
from app.services.email.console import ConsoleEmailProvider
from app.services.email.registry import get_email_provider
from app.services.email.resend import ResendProvider

__all__ = [
    "ConsoleEmailProvider",
    "EmailError",
    "EmailMessage",
    "EmailProvider",
    "ResendProvider",
    "get_email_provider",
]
