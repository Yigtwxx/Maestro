"""Watchdog: alert on state transitions, not on ticks; gauges without channels."""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from app.core import database
from app.core.config import settings
from app.core.metrics import metrics
from app.services import alert_service, watchdog
from app.services.alerts.base import Alert


@pytest.fixture
def sent_alerts(monkeypatch):
    """Capture what the watchdog decided to send, bypassing every channel."""
    captured: list[tuple[Alert, str]] = []

    async def _capture(alert: Alert, *, dedupe_key: str, cooldown_seconds=None) -> bool:
        captured.append((alert, dedupe_key))
        return True

    monkeypatch.setattr(watchdog.alert_service, "send_alert", _capture)
    return captured


@pytest.fixture
def probes(monkeypatch):
    """Drive check_readiness by naming which dependencies are healthy."""

    def _set(*, failing: str | None = None) -> None:
        async def _ok() -> None:
            return None

        async def _boom() -> None:
            raise RuntimeError("connection refused")

        async def _redis_ok() -> str:
            return "ok"

        for name, healthy in (
            ("ping_postgres", _ok),
            ("ping_mongo", _ok),
            ("ping_qdrant", _ok),
        ):
            monkeypatch.setattr(
                database, name, _boom if name == f"ping_{failing}" else healthy
            )
        monkeypatch.setattr(
            database, "ping_redis", _boom if failing == "redis" else _redis_ok
        )

    return _set


# --- Readiness transitions ------------------------------------------------


async def test_first_tick_when_ready_does_not_alert(probes, sent_alerts) -> None:
    """Booting healthy is not an event."""
    probes()

    await watchdog.watchdog.tick()

    assert sent_alerts == []


async def test_degraded_alerts_only_after_the_configured_failures(
    probes, sent_alerts, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alert_readiness_failures", 2)
    probes(failing="mongo")

    await watchdog.watchdog.tick()
    assert sent_alerts == [], "One failing tick must not page: services restart"

    await watchdog.watchdog.tick()

    assert len(sent_alerts) == 1, sent_alerts
    assert sent_alerts[0][1] == "readiness:degraded"


async def test_a_degraded_first_tick_still_waits(
    probes, sent_alerts, monkeypatch
) -> None:
    """A backend booting before Postgres passes its healthcheck must stay quiet."""
    monkeypatch.setattr(settings, "alert_readiness_failures", 2)
    probes(failing="postgres")

    await watchdog.watchdog.tick()

    assert sent_alerts == []


async def test_steady_state_degraded_does_not_re_alert(
    probes, sent_alerts, monkeypatch
) -> None:
    """Alerts fire on a transition, never on a tick."""
    monkeypatch.setattr(settings, "alert_readiness_failures", 1)
    probes(failing="mongo")

    for _ in range(5):
        await watchdog.watchdog.tick()

    assert len(sent_alerts) == 1, sent_alerts


async def test_single_tick_flap_never_alerts(probes, sent_alerts, monkeypatch) -> None:
    monkeypatch.setattr(settings, "alert_readiness_failures", 2)

    probes()
    await watchdog.watchdog.tick()
    probes(failing="qdrant")
    await watchdog.watchdog.tick()
    probes()
    await watchdog.watchdog.tick()

    assert sent_alerts == [], sent_alerts


async def test_recovery_alerts_once_after_a_degraded_period(
    probes, sent_alerts, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alert_readiness_failures", 1)

    probes(failing="mongo")
    await watchdog.watchdog.tick()
    probes()
    await watchdog.watchdog.tick()
    await watchdog.watchdog.tick()

    keys = [key for _, key in sent_alerts]
    assert keys == ["readiness:degraded", "readiness:recovered"], keys


async def test_recovery_is_not_swallowed_by_the_degraded_cooldown(
    probes, monkeypatch, channels_recorder
) -> None:
    """The dedupe key encodes the state, so the two claims never collide."""
    monkeypatch.setattr(settings, "alert_readiness_failures", 1)
    monkeypatch.setattr(settings, "alert_cooldown_seconds", 3600)

    probes(failing="mongo")
    await watchdog.watchdog.tick()
    probes()
    await watchdog.watchdog.tick()

    titles = [alert.title for alert in channels_recorder.alerts]
    assert len(titles) == 2, titles
    assert "recovered" in titles[1].lower(), titles


async def test_alert_body_names_the_failing_dependency(
    probes, sent_alerts, monkeypatch
) -> None:
    """Operator audience, unlike /health/ready — this is a decision, not a leak."""
    monkeypatch.setattr(settings, "alert_readiness_failures", 1)
    probes(failing="mongo")

    await watchdog.watchdog.tick()

    alert, _ = sent_alerts[0]
    assert "mongo" in alert.title, alert.title
    assert "mongo" in alert.details["failing"], alert.details


async def test_recovery_alert_reports_the_downtime(
    probes, sent_alerts, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alert_readiness_failures", 1)

    probes(failing="mongo")
    await watchdog.watchdog.tick()
    probes()
    await watchdog.watchdog.tick()

    recovery, _ = sent_alerts[-1]
    assert "downtime_seconds" in recovery.details, recovery.details


# --- Metrics stay live without any alert channel --------------------------


async def test_tick_updates_the_gauges_without_any_channel_configured(
    probes,
) -> None:
    """/metrics must be accurate on a deployment that never set ALERT_*."""
    probes(failing="mongo")

    await watchdog.watchdog.tick()

    body = metrics.render()
    assert 'maestro_dependency_up{worker="' in body
    assert '"mongo"} 0' in body, body
    assert "maestro_readiness_up" in body


# --- Error-rate alerting --------------------------------------------------


async def test_error_rate_alert_needs_the_minimum_volume(
    sent_alerts, monkeypatch
) -> None:
    """One error in three requests at 04:00 is noise, not an incident."""
    monkeypatch.setattr(settings, "alert_error_rate_min_requests", 20)
    for _ in range(3):
        metrics.record_request(500, 0.01)

    await watchdog.check_error_rate()

    assert sent_alerts == []


async def test_error_rate_alert_is_silent_below_the_threshold(
    sent_alerts, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alert_error_rate_min_requests", 10)
    monkeypatch.setattr(settings, "alert_error_rate_threshold", 0.5)
    for _ in range(19):
        metrics.record_request(200, 0.01)
    metrics.record_request(500, 0.01)

    await watchdog.check_error_rate()

    assert sent_alerts == []


async def test_error_rate_alert_fires_above_the_threshold(
    sent_alerts, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alert_error_rate_min_requests", 10)
    monkeypatch.setattr(settings, "alert_error_rate_threshold", 0.05)
    for _ in range(10):
        metrics.record_request(200, 0.01)
    for _ in range(10):
        metrics.record_request(500, 0.01)

    await watchdog.check_error_rate()

    assert len(sent_alerts) == 1, sent_alerts
    alert, key = sent_alerts[0]
    assert key == "error_rate"
    assert alert.details["server_errors"] == "10", alert.details


# --- Loop resilience ------------------------------------------------------


async def test_a_failing_job_neither_stops_its_siblings_nor_the_loop(
    monkeypatch,
) -> None:
    """A raise costs one tick. The loop must survive to run the next one."""
    ran: list[str] = []

    async def _boom() -> None:
        raise RuntimeError("job exploded")

    async def _ok() -> None:
        ran.append("ok")

    monkeypatch.setattr(watchdog, "_JOBS", (_boom, _ok))
    monkeypatch.setattr(settings, "alert_watchdog_interval_seconds", 0.01)

    loop = asyncio.create_task(watchdog.periodic_watch())
    while len(ran) < 3:
        await asyncio.sleep(0.01)
    loop.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await loop

    assert len(ran) >= 3, "The loop stopped after the first raising job"


async def test_publish_snapshot_is_a_noop_without_redis(monkeypatch) -> None:
    monkeypatch.setattr(watchdog, "get_redis_client", lambda: None)

    await watchdog.publish_snapshot()

    assert await watchdog.read_peer_snapshots() == []


# --- Fixtures used above --------------------------------------------------


@pytest.fixture
def channels_recorder(monkeypatch):
    """Install one recording channel so the real send_alert path is exercised."""

    class _Recorder:
        name = "recording"

        def __init__(self) -> None:
            self.alerts: list[Alert] = []

        async def send(self, alert: Alert) -> None:
            self.alerts.append(alert)

    recorder = _Recorder()
    monkeypatch.setattr(alert_service, "get_alert_channels", lambda: (recorder,))
    return recorder
