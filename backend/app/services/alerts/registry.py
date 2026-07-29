"""Alert channel lookup.

An empty tuple means alerting is off: ``alert_service.send_alert`` then returns
without touching the network, exactly like ``init_sentry`` with an empty DSN.
Configuring a channel *is* the enable -- there is no separate switch to forget.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.services.alerts.base import AlertChannel
from app.services.alerts.email import EmailAlertChannel
from app.services.alerts.webhook import WebhookAlertChannel


@lru_cache
def get_alert_channels() -> tuple[AlertChannel, ...]:
    """Return the configured operator-alert channels, webhook first.

    Cached like ``get_email_provider``; tests that change the settings must call
    ``get_alert_channels.cache_clear()``.
    """
    channels: list[AlertChannel] = []
    if settings.alert_webhook_url:
        channels.append(WebhookAlertChannel())
    if settings.alert_email_to:
        channels.append(EmailAlertChannel())
    return tuple(channels)
