"""Email provider seam.

Mirrors the payment adapter pattern (``services/payment``): adding a real
sender -- Resend, Postmark, SES -- means adding one adapter module, not editing
the code that calls it. The console adapter keeps dev/self-host working with
zero dependencies and zero network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class EmailMessage:
    """One outbound transactional email (both HTML and plain-text bodies)."""

    to: str
    subject: str
    html: str
    text: str


class EmailError(RuntimeError):
    """Raised when an email provider definitively fails to send."""


class EmailProvider(Protocol):
    """Interface every email adapter must implement."""

    name: str

    async def send(self, message: EmailMessage) -> None:
        """Deliver one message. Raises EmailError on failure."""
        ...
