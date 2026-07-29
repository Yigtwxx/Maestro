"""Webhook alert channel (Slack- and Discord-compatible, no SDK dependency).

One payload satisfies both platforms: Slack reads ``text`` and ignores
``content``, Discord reads ``content`` and ignores ``text``. That is why there
is no per-platform setting to get wrong -- paste an incoming-webhook URL from
either and it works. Anything else that accepts a JSON POST (ntfy, Gotify,
Mattermost, a two-line receiver of your own) sees both fields.

Redirects are not followed. The POST carries the alert to a URL that is itself
the credential, and a 3xx to another origin must never be honoured.
"""

from __future__ import annotations

import asyncio

import httpx

from app.core.config import settings
from app.core.constants import (
    ALERT_SEND_BACKOFF_BASE_SECONDS,
    ALERT_SEND_MAX_ATTEMPTS,
    ALERT_WEBHOOK_TIMEOUT_SECONDS,
)
from app.services.alerts.base import Alert, AlertError


class WebhookAlertChannel:
    """Posts alerts to the operator's incoming webhook."""

    name = "webhook"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # Injectable transport so tests exercise the retry logic offline.
        self._transport = transport

    async def send(self, alert: Alert) -> None:
        """Deliver one alert. Raises AlertError once the retries are spent.

        No error path ever includes the URL or the response body: the URL is a
        bearer credential, and a rejecting endpoint's body is attacker-shaped
        input from the process's point of view.
        """
        body = f"{alert.title}\n\n{alert.summary}"
        if alert.details:
            rendered = "\n".join(
                f"{key}: {value}" for key, value in alert.details.items()
            )
            body = f"{body}\n\n{rendered}"
        payload = {"text": body, "content": body}

        last_error = AlertError("Alert webhook could not be reached.")
        for attempt in range(ALERT_SEND_MAX_ATTEMPTS):
            if attempt:
                await asyncio.sleep(
                    ALERT_SEND_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
                )
            try:
                async with httpx.AsyncClient(
                    timeout=ALERT_WEBHOOK_TIMEOUT_SECONDS,
                    transport=self._transport,
                    follow_redirects=False,
                ) as client:
                    response = await client.post(
                        settings.alert_webhook_url, json=payload
                    )
            except httpx.HTTPError as exc:
                last_error = AlertError(f"Webhook request failed: {type(exc).__name__}")
                continue
            if response.is_success:
                return
            if response.status_code == 429 or response.status_code >= 500:
                last_error = AlertError(
                    f"Webhook transient failure (HTTP {response.status_code})"
                )
                continue
            # Permanent rejection (revoked hook, bad payload): retrying cannot help.
            raise AlertError(
                f"Webhook rejected the alert (HTTP {response.status_code})"
            )
        raise last_error
