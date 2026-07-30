"""Prometheus exposition: format correctness, counters, and the /metrics gate."""

from __future__ import annotations

import logging

import pytest

from app.core import database
from app.core import metrics as metrics_module
from app.core.config import settings
from app.core.constants import METRICS_TOKEN_HEADER
from app.core.metrics import CONTENT_TYPE, MetricsRegistry, Snapshot, metrics

_METRICS_TOKEN = "metrics-token-for-tests"


def _series(body: str, name: str) -> list[str]:
    """Every sample line belonging to `name` (labels included, comments not)."""
    return [
        line
        for line in body.splitlines()
        if not line.startswith("#") and line.split("{")[0].split(" ")[0] == name
    ]


def _value(body: str, name: str, label: str) -> float:
    """The single sample of `name` whose label set contains `label`."""
    for line in _series(body, name):
        if label in line:
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"{name} with {label} not found in:\n{body}")


# --- Exposition format ----------------------------------------------------


def test_render_emits_one_help_and_type_pair_per_family() -> None:
    """Repeating the metadata per series is a protocol violation."""
    registry = MetricsRegistry()
    registry.record_request(200, 0.01)

    body = registry.render()

    for prefix in ("# HELP ", "# TYPE "):
        names = [
            line.split(" ")[2] for line in body.splitlines() if line.startswith(prefix)
        ]
        duplicates = {name for name in names if names.count(name) > 1}
        assert not duplicates, f"{prefix.strip()} repeated for {duplicates}"


def test_render_body_ends_with_a_newline() -> None:
    body = MetricsRegistry().render()

    assert body.endswith("\n"), repr(body[-20:])


def test_render_emits_only_comments_and_samples() -> None:
    registry = MetricsRegistry()
    registry.record_request(500, 1.5)
    registry.set_dependencies({"postgres": "ok", "redis": "skipped"}, ready=True)

    body = registry.render()

    for line in body.splitlines():
        if line.startswith("#"):
            continue
        name, _, value = line.rpartition(" ")
        assert name, f"Sample line has no name: {line!r}"
        float(value)  # Raises if the value is not a valid float.


def test_histogram_buckets_are_cumulative_and_inf_equals_count() -> None:
    registry = MetricsRegistry()
    for duration in (0.001, 0.03, 0.4, 30.0):
        registry.record_request(200, duration)

    body = registry.render()
    buckets = _series(body, "maestro_http_request_duration_seconds_bucket")
    values = [float(line.rsplit(" ", 1)[1]) for line in buckets]

    assert values == sorted(values), f"Buckets are not cumulative: {values}"
    count = _value(body, "maestro_http_request_duration_seconds_count", "worker=")
    assert values[-1] == count, f"+Inf {values[-1]} != _count {count}"
    assert count == 4, count


def test_histogram_sum_accumulates_every_observation() -> None:
    registry = MetricsRegistry()
    registry.record_request(200, 0.25)
    registry.record_request(200, 0.75)

    total = _value(
        registry.render(), "maestro_http_request_duration_seconds_sum", "worker="
    )

    assert total == pytest.approx(1.0), total


@pytest.mark.parametrize(
    ("status", "status_class"),
    [(100, "1xx"), (200, "2xx"), (301, "3xx"), (404, "4xx"), (500, "5xx")],
)
def test_requests_are_counted_by_status_class(status: int, status_class: str) -> None:
    registry = MetricsRegistry()
    registry.record_request(status, 0.01)

    body = registry.render()

    assert _value(body, "maestro_http_requests_total", f'"{status_class}"') == 1


def test_every_status_class_series_is_always_present() -> None:
    """A series that appears only after its first hit breaks rate() at boot."""
    body = MetricsRegistry().render()

    assert len(_series(body, "maestro_http_requests_total")) == 5, body


def test_label_values_are_escaped(monkeypatch) -> None:
    registry = MetricsRegistry()
    monkeypatch.setattr(registry, "_worker", 'we"ird\\worker', raising=False)

    body = registry.render()

    assert 'worker="we\\"ird\\\\worker"' in body, body


def test_record_request_cannot_raise_on_an_unexpected_status() -> None:
    """The hot path runs inside the HTTP middleware: a raise 500s every request."""
    registry = MetricsRegistry()

    registry.record_request(0, 0.0)
    registry.record_request(999, 0.0)

    assert _value(registry.render(), "maestro_http_requests_total", '"1xx"') == 1
    assert _value(registry.render(), "maestro_http_requests_total", '"5xx"') == 1


# --- Dependency gauges ----------------------------------------------------


def test_dependency_gauge_treats_skipped_redis_as_up() -> None:
    """`skipped` is the supported no-REDIS_URL topology, not a failure."""
    registry = MetricsRegistry()
    registry.set_dependencies(
        {"postgres": "ok", "mongo": "error", "qdrant": "ok", "redis": "skipped"},
        ready=False,
    )

    body = registry.render()

    assert _value(body, "maestro_dependency_up", '"redis"') == 1
    assert _value(body, "maestro_dependency_up", '"mongo"') == 0
    assert _value(body, "maestro_readiness_up", "worker=") == 0


def test_gauges_are_absent_before_the_first_watchdog_tick() -> None:
    """Unknown must not render as 0 — that would look like a real outage."""
    body = MetricsRegistry().render()

    assert _series(body, "maestro_dependency_up") == [], body
    assert _series(body, "maestro_readiness_up") == [], body


# --- Rolling error-rate window --------------------------------------------


def test_error_rate_window_counts_totals_and_server_errors() -> None:
    registry = MetricsRegistry()
    for _ in range(8):
        registry.record_request(200, 0.01)
    for _ in range(2):
        registry.record_request(503, 0.01)

    total, errors = registry.error_rate_window(300.0)

    assert (total, errors) == (10, 2)


def test_error_rate_window_drops_buckets_older_than_the_window(monkeypatch) -> None:
    registry = MetricsRegistry()
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(metrics_module.time, "time", lambda: clock["now"])

    registry.record_request(500, 0.01)
    clock["now"] += 600  # Ten minutes later, well outside a 300s window.
    registry.record_request(200, 0.01)

    total, errors = registry.error_rate_window(300.0)

    assert (total, errors) == (1, 0), registry._window


def test_window_memory_is_bounded_by_the_configured_span(monkeypatch) -> None:
    """Without eviction on write the deque would grow for the process lifetime."""
    registry = MetricsRegistry()
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(metrics_module.time, "time", lambda: clock["now"])

    for _ in range(120):
        registry.record_request(200, 0.01)
        clock["now"] += 60

    span = settings.alert_error_rate_window_seconds / 60
    assert len(registry._window) <= span + 2, len(registry._window)


# --- Snapshots (cross-worker view) ----------------------------------------


def test_snapshot_round_trips_through_json() -> None:
    registry = MetricsRegistry()
    registry.record_request(200, 0.3)
    registry.set_dependencies({"postgres": "ok"}, ready=True)
    registry.record_alert("readiness", sent=True)
    original = registry.snapshot()

    restored = Snapshot.from_json(original.to_json())

    assert restored == original, f"{restored} != {original}"


def test_peer_snapshots_render_alongside_this_worker() -> None:
    registry = MetricsRegistry()
    registry.record_request(200, 0.01)
    peer = registry.snapshot()
    peer.worker = "other-host-99"

    body = registry.render([peer])

    assert len(_series(body, "maestro_http_requests_total")) == 10, body
    assert 'worker="other-host-99"' in body


def test_a_snapshot_from_another_build_is_rejected() -> None:
    """Mismatched buckets must cost one peer's series, never the whole scrape."""
    registry = MetricsRegistry()
    raw = registry.snapshot().to_json().replace('"duration_buckets":[0', '"x":[0', 1)

    with pytest.raises((ValueError, KeyError, TypeError)):
        Snapshot.from_json(raw)


# --- The /metrics endpoint ------------------------------------------------


async def test_metrics_endpoint_404s_without_a_token(client, monkeypatch) -> None:
    """An unconfigured deployment must not advertise the surface at all."""
    monkeypatch.setattr(settings, "metrics_token", "")

    resp = await client.get("/metrics")

    assert resp.status_code == 404, resp.text


async def test_metrics_endpoint_404s_with_a_wrong_token(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "metrics_token", _METRICS_TOKEN)

    resp = await client.get("/metrics", headers={METRICS_TOKEN_HEADER: "nope"})

    assert resp.status_code == 404, resp.text


async def test_metrics_endpoint_unset_token_never_authorizes(
    client, monkeypatch
) -> None:
    """An empty token must not turn an empty header into a valid credential."""
    monkeypatch.setattr(settings, "metrics_token", "")

    resp = await client.get("/metrics", headers={METRICS_TOKEN_HEADER: ""})

    assert resp.status_code == 404, resp.text


async def test_metrics_endpoint_serves_exposition_with_the_token(
    client, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "metrics_token", _METRICS_TOKEN)

    resp = await client.get("/metrics", headers={METRICS_TOKEN_HEADER: _METRICS_TOKEN})

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith(CONTENT_TYPE.split(";")[0])
    assert "maestro_http_requests_total" in resp.text
    assert "maestro_build_info" in resp.text


async def test_probe_traffic_is_not_counted(client, monkeypatch) -> None:
    """`/health/ready` answers 503 when degraded; counting it would double-page.

    A degraded dependency would otherwise trip the 5xx error-rate alert on top
    of the readiness alert that already reports the same fault.
    """

    async def _ok() -> None:
        return None

    async def _boom() -> None:
        raise RuntimeError("down")

    async def _redis_ok() -> str:
        return "ok"

    monkeypatch.setattr(database, "ping_postgres", _ok)
    monkeypatch.setattr(database, "ping_mongo", _boom)
    monkeypatch.setattr(database, "ping_qdrant", _ok)
    monkeypatch.setattr(database, "ping_redis", _redis_ok)
    monkeypatch.setattr(settings, "metrics_token", _METRICS_TOKEN)

    degraded = await client.get("/health/ready")
    await client.get("/health")
    await client.get("/metrics", headers={METRICS_TOKEN_HEADER: _METRICS_TOKEN})

    assert degraded.status_code == 503, degraded.text
    total, errors = metrics.error_rate_window(300.0)
    assert (total, errors) == (0, 0), "Probe traffic leaked into the counters"


async def test_real_traffic_is_counted(client) -> None:
    """The counterpart to the exclusion: ordinary routes must still register."""
    await client.get("/api/v1/billing/plans")

    total, _ = metrics.error_rate_window(300.0)

    assert total == 1, total


async def test_metrics_path_is_not_access_logged(client, monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "metrics_token", _METRICS_TOKEN)

    with caplog.at_level(logging.INFO, logger="maestro.access"):
        await client.get("/metrics", headers={METRICS_TOKEN_HEADER: _METRICS_TOKEN})

    records = [record for record in caplog.records if record.name == "maestro.access"]
    assert records == [], records
