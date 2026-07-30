"""Operator alerting: delivery, deduplication, and the redaction invariant."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import settings
from app.core.constants import ALERT_REDACTED_PLACEHOLDER, AlertKind, AlertSeverity
from app.services import alert_service
from app.services.alerts import get_alert_channels
from app.services.alerts.base import Alert, AlertError
from app.services.alerts.email import EmailAlertChannel
from app.services.alerts.webhook import WebhookAlertChannel
from app.services.email.base import EmailError
from tests.conftest import RecordingEmailProvider

_WEBHOOK_URL = "https://hooks.example.com/services/T000/B000/xxxxxxxxxxxxxxxx"


def _alert(**overrides) -> Alert:
    """A minimal alert; override any field a test cares about."""
    fields = {
        "kind": AlertKind.READINESS.value,
        "severity": AlertSeverity.CRITICAL.value,
        "title": "Maestro is degraded: mongo",
        "summary": "The readiness probe failed twice.",
        "fired_at": datetime.now(UTC),
        "details": {"failing": "mongo"},
    }
    fields.update(overrides)
    return Alert(**fields)


class _RecordingChannel:
    """Captures the alerts a channel was handed, after redaction."""

    def __init__(self, name: str = "recording", fail: bool = False) -> None:
        self.name = name
        self.alerts: list[Alert] = []
        self._fail = fail

    async def send(self, alert: Alert) -> None:
        self.alerts.append(alert)
        if self._fail:
            raise AlertError("channel is down")


@pytest.fixture
def channels(monkeypatch):
    """Install recording channels and return the list they capture into."""

    def _install(*installed):
        monkeypatch.setattr(alert_service, "get_alert_channels", lambda: installed)
        return installed

    return _install


# --- The zero-egress default ----------------------------------------------


async def test_send_alert_without_a_channel_is_a_noop() -> None:
    """Mirrors init_sentry: unconfigured means no work and no network call."""
    delivered = await alert_service.send_alert(_alert(), dedupe_key="k")

    assert delivered is False


def test_registry_is_empty_when_nothing_is_configured() -> None:
    get_alert_channels.cache_clear()

    assert get_alert_channels() == ()


def test_registry_builds_only_the_configured_channels(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alert_webhook_url", _WEBHOOK_URL)
    monkeypatch.setattr(settings, "alert_email_to", "")
    get_alert_channels.cache_clear()

    names = [channel.name for channel in get_alert_channels()]

    assert names == ["webhook"], names


def test_registry_builds_both_channels_when_both_are_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alert_webhook_url", _WEBHOOK_URL)
    monkeypatch.setattr(settings, "alert_email_to", "ops@example.com")
    get_alert_channels.cache_clear()

    names = [channel.name for channel in get_alert_channels()]

    assert names == ["webhook", "email"], names


# --- Webhook channel ------------------------------------------------------


async def test_webhook_payload_carries_both_slack_and_discord_keys(
    monkeypatch,
) -> None:
    """One body serves both platforms, so there is no per-platform setting."""
    monkeypatch.setattr(settings, "alert_webhook_url", _WEBHOOK_URL)
    captured: list[dict] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200)

    await WebhookAlertChannel(httpx.MockTransport(_handler)).send(_alert())

    assert captured[0]["text"] == captured[0]["content"]
    assert "Maestro is degraded: mongo" in captured[0]["text"]
    assert "failing: mongo" in captured[0]["text"]


async def test_webhook_retries_a_transient_failure_then_succeeds(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "alert_webhook_url", _WEBHOOK_URL)
    monkeypatch.setattr(
        "app.services.alerts.webhook.ALERT_SEND_BACKOFF_BASE_SECONDS", 0
    )
    attempts = {"n": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(200 if attempts["n"] > 1 else 503)

    await WebhookAlertChannel(httpx.MockTransport(_handler)).send(_alert())

    assert attempts["n"] == 2, attempts


async def test_webhook_does_not_retry_a_permanent_rejection(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alert_webhook_url", _WEBHOOK_URL)
    attempts = {"n": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(403)

    with pytest.raises(AlertError):
        await WebhookAlertChannel(httpx.MockTransport(_handler)).send(_alert())

    assert attempts["n"] == 1, "A 403 will not become a 200 on retry"


async def test_webhook_does_not_follow_redirects(monkeypatch) -> None:
    """The URL is itself a credential; a 3xx must never move the POST."""
    monkeypatch.setattr(settings, "alert_webhook_url", _WEBHOOK_URL)
    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://evil.example.com/x"})

    with pytest.raises(AlertError):
        await WebhookAlertChannel(httpx.MockTransport(_handler)).send(_alert())

    assert all("evil.example.com" not in url for url in seen), seen


async def test_webhook_error_never_exposes_the_url(monkeypatch) -> None:
    """A Slack/Discord webhook URL is a bearer credential (CLAUDE.md §9.1)."""
    monkeypatch.setattr(settings, "alert_webhook_url", _WEBHOOK_URL)

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="secret-body-content")

    with pytest.raises(AlertError) as excinfo:
        await WebhookAlertChannel(httpx.MockTransport(_handler)).send(_alert())

    message = str(excinfo.value)
    assert _WEBHOOK_URL not in message, message
    assert "secret-body-content" not in message, message


async def test_webhook_failure_never_logs_the_url(
    monkeypatch, caplog, channels
) -> None:
    monkeypatch.setattr(settings, "alert_webhook_url", _WEBHOOK_URL)

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    channels(WebhookAlertChannel(httpx.MockTransport(_handler)))
    with caplog.at_level(logging.ERROR):
        delivered = await alert_service.send_alert(_alert(), dedupe_key="k")

    assert delivered is False
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert _WEBHOOK_URL not in logged, logged


# --- Email channel --------------------------------------------------------


async def test_email_channel_uses_the_configured_provider(monkeypatch) -> None:
    """Alerts ride the existing email seam; no second provider is registered."""
    monkeypatch.setattr(settings, "alert_email_to", "ops@example.com")
    provider = RecordingEmailProvider()
    monkeypatch.setattr(
        "app.services.alerts.email.get_email_provider", lambda: provider
    )

    await EmailAlertChannel().send(_alert())

    assert provider.messages, "The alert never reached the email provider"
    message = provider.messages[0]
    assert message.to == "ops@example.com"
    assert message.subject == "Maestro is degraded: mongo"
    assert "mongo" in message.text, message.text


async def test_email_channel_translates_a_provider_failure(monkeypatch) -> None:
    class _Broken:
        name = "broken"

        async def send(self, message) -> None:  # noqa: ANN001 - EmailMessage
            raise EmailError("smtp refused")

    monkeypatch.setattr(settings, "alert_email_to", "ops@example.com")
    monkeypatch.setattr(
        "app.services.alerts.email.get_email_provider", lambda: _Broken()
    )

    with pytest.raises(AlertError):
        await EmailAlertChannel().send(_alert())


# --- Redaction (the invariant that replaces a Semgrep rule) ----------------


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql+asyncpg://maestro:hunter2@db:5432/maestro",
        "redis://:sup3rs3cret@redis:6379/0",
        "mongodb://admin:letmein@mongo:27017",
    ],
)
def test_redact_strips_url_credentials(raw: str) -> None:
    result = alert_service.redact(f"connection failed: {raw}")

    assert "hunter2" not in result
    assert "sup3rs3cret" not in result
    assert "letmein" not in result
    assert "***@" in result, result


def test_redact_leaves_ordinary_text_alone() -> None:
    text = "mongo is unreachable after 2 consecutive readiness failures"

    assert alert_service.redact(text) == text


@pytest.mark.parametrize(
    "attribute",
    [
        "jwt_secret",
        "api_key_master_key",
        "health_detail_token",
        "metrics_token",
        "alert_webhook_url",
        "postgres_url",
    ],
)
async def test_alert_body_never_contains_a_configured_secret(
    attribute: str, monkeypatch, channels
) -> None:
    """The positive control: a call site cannot leak a config value by accident.

    Even if someone later interpolates a raw setting into an alert body, it is
    masked before any channel sees it.
    """
    secret = f"super-secret-value-for-{attribute}"
    monkeypatch.setattr(settings, attribute, secret)
    recorder = _RecordingChannel()
    channels(recorder)

    await alert_service.send_alert(
        _alert(summary=f"leaked {secret}", details={"config": secret}),
        dedupe_key="k",
    )

    delivered = recorder.alerts[0]
    assert secret not in delivered.summary, delivered.summary
    assert secret not in delivered.details["config"], delivered.details
    assert ALERT_REDACTED_PLACEHOLDER in delivered.details["config"]


def test_redact_ignores_values_below_the_length_floor(monkeypatch) -> None:
    """A short placeholder config value must not blank ordinary words."""
    monkeypatch.setattr(settings, "metrics_token", "ok")

    assert alert_service.redact("mongo is ok") == "mongo is ok"


# --- Deduplication --------------------------------------------------------


async def test_a_second_alert_inside_the_cooldown_is_suppressed(channels) -> None:
    recorder = _RecordingChannel()
    channels(recorder)

    first = await alert_service.send_alert(
        _alert(), dedupe_key="k", cooldown_seconds=60
    )
    second = await alert_service.send_alert(
        _alert(), dedupe_key="k", cooldown_seconds=60
    )

    assert first is True
    assert second is False
    assert len(recorder.alerts) == 1, recorder.alerts


async def test_a_different_dedupe_key_is_not_suppressed(channels) -> None:
    """Recovery must not be swallowed by the degraded alert's cooldown."""
    recorder = _RecordingChannel()
    channels(recorder)

    await alert_service.send_alert(
        _alert(), dedupe_key="readiness:degraded", cooldown_seconds=60
    )
    recovered = await alert_service.send_alert(
        _alert(), dedupe_key="readiness:recovered", cooldown_seconds=60
    )

    assert recovered is True
    assert len(recorder.alerts) == 2, recorder.alerts


async def test_a_zero_cooldown_never_suppresses(channels) -> None:
    recorder = _RecordingChannel()
    channels(recorder)

    await alert_service.send_alert(_alert(), dedupe_key="k", cooldown_seconds=0)
    await alert_service.send_alert(_alert(), dedupe_key="k", cooldown_seconds=0)

    assert len(recorder.alerts) == 2, recorder.alerts


# --- Fan-out resilience ---------------------------------------------------


async def test_one_channel_failing_does_not_stop_the_other(channels) -> None:
    broken = _RecordingChannel("broken", fail=True)
    working = _RecordingChannel("working")
    channels(broken, working)

    delivered = await alert_service.send_alert(_alert(), dedupe_key="k")

    assert delivered is True, "A healthy channel still delivered"
    assert len(working.alerts) == 1, working.alerts


async def test_send_alert_returns_false_when_every_channel_fails(channels) -> None:
    channels(_RecordingChannel("a", fail=True), _RecordingChannel("b", fail=True))

    delivered = await alert_service.send_alert(_alert(), dedupe_key="k")

    assert delivered is False


async def test_send_alert_never_raises(channels) -> None:
    """Monitoring that can crash what it monitors is worse than none."""

    class _Exploding:
        name = "exploding"

        async def send(self, alert: Alert) -> None:
            raise RuntimeError("unexpected non-AlertError")

    channels(_Exploding())

    assert await alert_service.send_alert(_alert(), dedupe_key="k") is False
