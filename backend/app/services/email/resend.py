"""Resend email adapter (HTTP API, no SDK dependency).

Retries transient failures (429/5xx/network) with exponential backoff and
gives up on permanent rejections immediately. Never logs or re-raises the API
key or the raw response body.
"""

from __future__ import annotations

import asyncio

import httpx

from app.core.config import settings
from app.core.constants import (
    EMAIL_SEND_BACKOFF_BASE_SECONDS,
    EMAIL_SEND_MAX_ATTEMPTS,
    EMAIL_SEND_TIMEOUT_SECONDS,
    RESEND_API_URL,
)
from app.services.email.base import EmailError, EmailMessage


class ResendProvider:
    """Sends transactional email through the Resend HTTP API."""

    name = "resend"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # Injectable transport so tests exercise the retry logic offline.
        self._transport = transport

    async def send(self, message: EmailMessage) -> None:
        payload = {
            "from": settings.email_from,
            "to": [message.to],
            "subject": message.subject,
            "html": message.html,
            "text": message.text,
        }
        headers = {"Authorization": f"Bearer {settings.resend_api_key}"}
        last_error = EmailError("Email could not be sent.")
        for attempt in range(EMAIL_SEND_MAX_ATTEMPTS):
            if attempt:
                await asyncio.sleep(
                    EMAIL_SEND_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
                )
            try:
                async with httpx.AsyncClient(
                    timeout=EMAIL_SEND_TIMEOUT_SECONDS, transport=self._transport
                ) as client:
                    response = await client.post(
                        RESEND_API_URL, json=payload, headers=headers
                    )
            except httpx.HTTPError as exc:
                last_error = EmailError(f"Resend request failed: {type(exc).__name__}")
                continue
            if response.is_success:
                return
            if response.status_code == 429 or response.status_code >= 500:
                last_error = EmailError(
                    f"Resend transient failure (HTTP {response.status_code})"
                )
                continue
            # Permanent rejection (bad payload, bad key): retrying cannot help.
            raise EmailError(
                f"Resend rejected the message (HTTP {response.status_code})"
            )
        raise last_error
