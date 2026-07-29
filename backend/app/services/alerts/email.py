"""Email alert channel, riding the existing transactional email seam.

Nothing new is registered in ``services/email/registry.py``: whatever
``EMAIL_PROVIDER`` is set to delivers operator alerts too. With the default
``console`` provider that means the alert is written to the server log rather
than delivered -- consistent with every other mail path in this codebase, and
the right default for a self-host that has not configured a sender yet.
"""

from __future__ import annotations

from app.core.config import settings
from app.services.alerts.base import Alert, AlertError
from app.services.alerts.templates import render
from app.services.email.base import EmailError, EmailMessage
from app.services.email.registry import get_email_provider


class EmailAlertChannel:
    """Sends operator alerts to ``ALERT_EMAIL_TO``."""

    name = "email"

    async def send(self, alert: Alert) -> None:
        """Deliver one alert as mail. Raises AlertError on provider failure."""
        html, text = render(alert.summary, alert.details)
        message = EmailMessage(
            to=settings.alert_email_to,
            subject=alert.title,
            html=html,
            text=text,
        )
        try:
            await get_email_provider().send(message)
        except EmailError as exc:
            # The provider's message is already credential-free, but the class
            # name is all a caller needs and all that gets logged upstream.
            raise AlertError(f"Email channel failed: {type(exc).__name__}") from exc
