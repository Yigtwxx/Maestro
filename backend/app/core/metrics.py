"""Prometheus-format metrics, hand-rolled over in-process counters.

No new dependency and no scraper on the host: the app exposes the text
exposition format at ``/metrics`` and whoever wants a time series points their
own scraper at it. Counters live in memory and are updated on the request hot
path, so ``record_request`` does no I/O and cannot raise -- a metrics bug must
never become a 500 on every request.

There is deliberately **no** ``path`` label. Paths are unbounded
(``/api/v1/tasks/{uuid}``), and label-exploding a hand-rolled registry is
exactly how "lightweight" turns into an OOM. Aggregate latency and error rate
are what the alert thresholds read; per-route breakdowns belong in a real APM.

Every series carries a ``worker`` label. Each uvicorn worker keeps its own
counters and publishes a snapshot to Redis (``services.watchdog``); ``/metrics``
renders its own live counters plus each peer's last snapshot. That is the
Prometheus idiom -- ``sum(rate(...))`` stays correct, and a worker restart
resets one series instead of making a summed counter run backwards.
"""

from __future__ import annotations

import json
import math
import os
import socket
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from app.core.config import settings
from app.core.constants import APP_VERSION

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

# Latency buckets in seconds. Spread for a web API: sub-10ms cache hits at one
# end, the multi-second LLM-bound requests this app actually serves at the other.
_BUCKETS_SECONDS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

_STATUS_CLASSES: tuple[str, ...] = ("1xx", "2xx", "3xx", "4xx", "5xx")

# Fixed rather than derived from the last readiness result, so a series never
# vanishes mid-scrape just because one ping timed out before the map was built.
_DEPENDENCIES: tuple[str, ...] = ("postgres", "mongo", "qdrant", "redis")

# "skipped" is Redis with no REDIS_URL -- a supported single-instance topology,
# not a failure (``database.ping_redis``), so it counts as up.
_UP_STATUSES = frozenset({"ok", "skipped"})

_SECONDS_PER_MINUTE = 60.0

_ALERT_KINDS: tuple[str, ...] = ("readiness", "error_rate")


def worker_id() -> str:
    """Stable per-process series label: ``{hostname}-{pid}``."""
    return f"{socket.gethostname()}-{os.getpid()}"


def _escape_label(value: str) -> str:
    """Escape a label value per the exposition format (backslash, quote, LF)."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(pairs: Iterable[tuple[str, str]]) -> str:
    """Render ``{k="v",…}``, or an empty string when there are no pairs."""
    rendered = ",".join(f'{key}="{_escape_label(value)}"' for key, value in pairs)
    return f"{{{rendered}}}" if rendered else ""


def _num(value: float) -> str:
    """Format a metric value: integers bare, floats without exponent noise."""
    if isinstance(value, int) or value.is_integer():
        return str(int(value))
    return repr(round(value, 6))


@dataclass(slots=True)
class Snapshot:
    """One worker's counter state, serialisable for the cross-worker view.

    ``ready`` is None until the watchdog has run its first tick; the readiness
    and dependency gauges are then simply not emitted for that worker, which is
    honest about "not known yet" in a way that a default of 0 or 1 would not be.
    """

    worker: str
    started_at: float
    scraped_at: float
    requests: dict[str, int]
    duration_buckets: list[int]
    duration_sum: float
    duration_count: int
    dependencies: dict[str, str]
    ready: bool | None
    alerts_sent: dict[str, int]
    alerts_suppressed: dict[str, int]

    def to_json(self) -> str:
        """Serialise for the Redis snapshot key."""
        return json.dumps(
            {
                "worker": self.worker,
                "started_at": self.started_at,
                "scraped_at": self.scraped_at,
                "requests": self.requests,
                "duration_buckets": self.duration_buckets,
                "duration_sum": self.duration_sum,
                "duration_count": self.duration_count,
                "dependencies": self.dependencies,
                "ready": self.ready,
                "alerts_sent": self.alerts_sent,
                "alerts_suppressed": self.alerts_suppressed,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str) -> Snapshot:
        """Rebuild a peer's snapshot. Raises on anything malformed.

        Callers treat a raise as "skip this peer": a corrupt or truncated key
        must cost one worker's series, never the whole scrape.
        """
        data = json.loads(raw)
        buckets = [int(count) for count in data["duration_buckets"]]
        if len(buckets) != len(_BUCKETS_SECONDS):
            raise ValueError("snapshot bucket count does not match this build")
        ready = data["ready"]
        return cls(
            worker=str(data["worker"]),
            started_at=float(data["started_at"]),
            scraped_at=float(data["scraped_at"]),
            requests={str(k): int(v) for k, v in data["requests"].items()},
            duration_buckets=buckets,
            duration_sum=float(data["duration_sum"]),
            duration_count=int(data["duration_count"]),
            dependencies={str(k): str(v) for k, v in data["dependencies"].items()},
            ready=None if ready is None else bool(ready),
            alerts_sent={str(k): int(v) for k, v in data["alerts_sent"].items()},
            alerts_suppressed={
                str(k): int(v) for k, v in data["alerts_suppressed"].items()
            },
        )


class MetricsRegistry:
    """Process-local counters plus the rolling 5xx window the watchdog reads."""

    def __init__(self) -> None:
        self._worker = worker_id()
        self._started_at = time.time()
        self._requests: dict[str, int] = dict.fromkeys(_STATUS_CLASSES, 0)
        self._duration_buckets = [0] * len(_BUCKETS_SECONDS)
        self._duration_sum = 0.0
        self._duration_count = 0
        self._dependencies: dict[str, str] = {}
        self._ready: bool | None = None
        self._alerts_sent: dict[str, int] = dict.fromkeys(_ALERT_KINDS, 0)
        self._alerts_suppressed: dict[str, int] = dict.fromkeys(_ALERT_KINDS, 0)
        # (minute_epoch, total, server_errors), oldest first.
        self._window: deque[list[float]] = deque()

    # --- Hot path ---------------------------------------------------------

    def record_request(self, status: int, duration_seconds: float) -> None:
        """Count one served request. Called from the HTTP middleware.

        Total by construction: pure arithmetic on pre-sized containers, no I/O
        and no lookup that can miss. If this could raise, every request in the
        app would 500.
        """
        status_class = f"{min(max(status // 100, 1), 5)}xx"
        self._requests[status_class] += 1

        self._duration_sum += duration_seconds
        self._duration_count += 1
        for index, upper in enumerate(_BUCKETS_SECONDS):
            if duration_seconds <= upper:
                self._duration_buckets[index] += 1
                break

        self._record_in_window(status >= 500)

    def _record_in_window(self, is_server_error: bool) -> None:
        """Fold one request into the current minute bucket, evicting old ones."""
        minute = math.floor(time.time() / _SECONDS_PER_MINUTE)
        if not self._window or self._window[-1][0] != minute:
            self._window.append([minute, 0, 0])
            self._trim_window(minute)
        current = self._window[-1]
        current[1] += 1
        if is_server_error:
            current[2] += 1

    def _trim_window(self, minute: float) -> None:
        """Drop buckets older than the widest window anyone can ask for."""
        span = math.ceil(settings.alert_error_rate_window_seconds / _SECONDS_PER_MINUTE)
        oldest = minute - span
        while self._window and self._window[0][0] < oldest:
            self._window.popleft()

    # --- Watchdog writes --------------------------------------------------

    def set_dependencies(self, checks: Mapping[str, str], *, ready: bool) -> None:
        """Publish the latest readiness result to the gauges."""
        self._dependencies = dict(checks)
        self._ready = ready

    def record_alert(self, kind: str, *, sent: bool) -> None:
        """Count one alert as delivered or suppressed by the dedupe claim."""
        counter = self._alerts_sent if sent else self._alerts_suppressed
        counter[kind] = counter.get(kind, 0) + 1

    # --- Watchdog reads ---------------------------------------------------

    def error_rate_window(self, window_seconds: float) -> tuple[int, int]:
        """``(total, server_errors)`` over the trailing ``window_seconds``.

        Minute-granular: a bucket is included when its minute starts inside the
        window. Coarser than the request timestamps, and deliberately so -- the
        alternative is retaining one entry per request.
        """
        now_minute = math.floor(time.time() / _SECONDS_PER_MINUTE)
        oldest = now_minute - math.ceil(window_seconds / _SECONDS_PER_MINUTE) + 1
        total = 0
        errors = 0
        for minute, bucket_total, bucket_errors in self._window:
            if minute >= oldest:
                total += int(bucket_total)
                errors += int(bucket_errors)
        return total, errors

    # --- Exposition -------------------------------------------------------

    def snapshot(self) -> Snapshot:
        """This worker's current state, ready to publish or render."""
        return Snapshot(
            worker=self._worker,
            started_at=self._started_at,
            scraped_at=time.time(),
            requests=dict(self._requests),
            duration_buckets=list(self._duration_buckets),
            duration_sum=self._duration_sum,
            duration_count=self._duration_count,
            dependencies=dict(self._dependencies),
            ready=self._ready,
            alerts_sent=dict(self._alerts_sent),
            alerts_suppressed=dict(self._alerts_suppressed),
        )

    def render(self, peers: Iterable[Snapshot] = ()) -> str:
        """Render the exposition body for this worker plus every peer.

        One ``# HELP``/``# TYPE`` pair per metric family, then every worker's
        series for that family -- emitting the pair per series is a protocol
        violation that some scrapers accept and others reject outright.
        """
        workers = [self.snapshot(), *peers]
        lines: list[str] = []
        for family in _FAMILIES:
            lines.append(f"# HELP {family.name} {family.help}")
            lines.append(f"# TYPE {family.name} {family.kind}")
            for snapshot in workers:
                lines.extend(family.render(snapshot))
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        """Drop all state (tests, mirroring ``rate_limiter.Limiter.reset``)."""
        self._started_at = time.time()
        self._requests = dict.fromkeys(_STATUS_CLASSES, 0)
        self._duration_buckets = [0] * len(_BUCKETS_SECONDS)
        self._duration_sum = 0.0
        self._duration_count = 0
        self._dependencies = {}
        self._ready = None
        self._alerts_sent = dict.fromkeys(_ALERT_KINDS, 0)
        self._alerts_suppressed = dict.fromkeys(_ALERT_KINDS, 0)
        self._window.clear()


# --- Metric families ------------------------------------------------------


_Renderer = Callable[["Snapshot"], list[str]]


@dataclass(slots=True, frozen=True)
class _Family:
    """One metric family: its metadata plus how to render a worker's series."""

    name: str
    kind: str
    help: str
    render: _Renderer


def _build_info(snapshot: Snapshot) -> list[str]:
    labels = _labels(
        (
            ("worker", snapshot.worker),
            ("version", APP_VERSION),
            ("environment", settings.environment),
        )
    )
    return [f"maestro_build_info{labels} 1"]


def _start_time(snapshot: Snapshot) -> list[str]:
    labels = _labels((("worker", snapshot.worker),))
    return [f"maestro_process_start_time_seconds{labels} {_num(snapshot.started_at)}"]


def _uptime(snapshot: Snapshot) -> list[str]:
    labels = _labels((("worker", snapshot.worker),))
    uptime = max(0.0, snapshot.scraped_at - snapshot.started_at)
    return [f"maestro_process_uptime_seconds{labels} {_num(uptime)}"]


def _requests_total(snapshot: Snapshot) -> list[str]:
    lines = []
    for status_class in _STATUS_CLASSES:
        labels = _labels(
            (("worker", snapshot.worker), ("status_class", status_class)),
        )
        count = snapshot.requests.get(status_class, 0)
        lines.append(f"maestro_http_requests_total{labels} {count}")
    return lines


def _request_duration(snapshot: Snapshot) -> list[str]:
    lines = []
    cumulative = 0
    for upper, count in zip(_BUCKETS_SECONDS, snapshot.duration_buckets, strict=True):
        cumulative += count
        labels = _labels((("worker", snapshot.worker), ("le", _num(upper))))
        lines.append(
            f"maestro_http_request_duration_seconds_bucket{labels} {cumulative}"
        )
    # Everything slower than the last bucket lands only in +Inf, which is why
    # it must equal _count rather than the running total above.
    inf_labels = _labels((("worker", snapshot.worker), ("le", "+Inf")))
    lines.append(
        f"maestro_http_request_duration_seconds_bucket{inf_labels} "
        f"{snapshot.duration_count}"
    )
    worker_labels = _labels((("worker", snapshot.worker),))
    lines.append(
        f"maestro_http_request_duration_seconds_sum{worker_labels} "
        f"{_num(snapshot.duration_sum)}"
    )
    lines.append(
        f"maestro_http_request_duration_seconds_count{worker_labels} "
        f"{snapshot.duration_count}"
    )
    return lines


def _dependency_up(snapshot: Snapshot) -> list[str]:
    if snapshot.ready is None:
        return []
    lines = []
    for dependency in _DEPENDENCIES:
        status = snapshot.dependencies.get(dependency)
        if status is None:
            continue
        labels = _labels(
            (("worker", snapshot.worker), ("dependency", dependency)),
        )
        lines.append(f"maestro_dependency_up{labels} {int(status in _UP_STATUSES)}")
    return lines


def _readiness_up(snapshot: Snapshot) -> list[str]:
    if snapshot.ready is None:
        return []
    labels = _labels((("worker", snapshot.worker),))
    return [f"maestro_readiness_up{labels} {int(snapshot.ready)}"]


def _alerts(counter_name: str, attribute: str) -> _Renderer:
    """Build the renderer for one alert counter family."""

    def _render(snapshot: Snapshot) -> list[str]:
        counts: dict[str, int] = getattr(snapshot, attribute)
        lines = []
        for kind in _ALERT_KINDS:
            labels = _labels((("worker", snapshot.worker), ("kind", kind)))
            lines.append(f"{counter_name}{labels} {counts.get(kind, 0)}")
        return lines

    return _render


_FAMILIES: tuple[_Family, ...] = (
    _Family(
        "maestro_build_info",
        "gauge",
        "Build and environment identity of each worker (always 1).",
        _build_info,
    ),
    _Family(
        "maestro_process_start_time_seconds",
        "gauge",
        "Unix timestamp at which the worker process started.",
        _start_time,
    ),
    _Family(
        "maestro_process_uptime_seconds",
        "gauge",
        "Seconds since the worker process started.",
        _uptime,
    ),
    _Family(
        "maestro_http_requests_total",
        "counter",
        "HTTP requests served, by response status class. Health and metrics "
        "probes are excluded.",
        _requests_total,
    ),
    _Family(
        "maestro_http_request_duration_seconds",
        "histogram",
        "Latency of served HTTP requests, in seconds.",
        _request_duration,
    ),
    _Family(
        "maestro_dependency_up",
        "gauge",
        "Whether each backing service answered its last readiness ping "
        "(a skipped Redis counts as up).",
        _dependency_up,
    ),
    _Family(
        "maestro_readiness_up",
        "gauge",
        "Whether every required dependency answered the last readiness check.",
        _readiness_up,
    ),
    _Family(
        "maestro_alerts_sent_total",
        "counter",
        "Operator alerts delivered to at least one channel, by kind.",
        _alerts("maestro_alerts_sent_total", "alerts_sent"),
    ),
    _Family(
        "maestro_alerts_suppressed_total",
        "counter",
        "Operator alerts suppressed by the dedupe cooldown, by kind.",
        _alerts("maestro_alerts_suppressed_total", "alerts_suppressed"),
    ),
)


metrics = MetricsRegistry()
