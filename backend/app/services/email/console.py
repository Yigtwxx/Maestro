"""Console email adapter: logs messages instead of sending them.

The default for development, tests and self-hosting. Deliberately logs the
full text body -- surfacing the verification/reset link in server logs is the
whole point when no real sender is configured.
"""

from __future__ import annotations

import logging

from app.services.email.base import EmailMessage

logger = logging.getLogger(__name__)


class ConsoleEmailProvider:
    """Logs outbound email to the application logger."""

    name = "console"

    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "email (console provider) to=%s subject=%r\n%s",
            message.to,
            message.subject,
            message.text,
        )
