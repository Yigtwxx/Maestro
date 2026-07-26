"""Observability wiring: structured logging and Sentry error tracking.

Both are opt-in and degrade to no-ops so local development and the test suite
need no extra services:

* ``configure_logging`` picks a colourised console or JSON formatter from
  ``LOG_FORMAT``.
* ``init_sentry`` is a no-op unless ``SENTRY_DSN`` is set; when it is, it wires
  the FastAPI and logging integrations and scrubs PII before events leave the
  process (CLAUDE.md §9.1/§15 — API keys, prompts and card data never leave).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import IO, Any

from app.core.config import settings

logger = logging.getLogger("maestro")

# Request headers that may carry credentials. Dropped from every Sentry event on
# top of send_default_pii=False, which already omits body, cookies and client IP.
_SENSITIVE_HEADERS = frozenset(
    {"authorization", "cookie", "x-api-key", "x-forwarded-for"}
)

# Standard LogRecord attributes; anything else on the record is treated as a
# structured "extra" field and merged into the JSON payload.
_RESERVED_LOG_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


# ANSI SGR codes. Kept as literals rather than pulling in a colour library: the
# console formatter is a development convenience and must not add a dependency.
_RESET = "\033[0m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BOLD_RED = "\033[1;31m"

_LEVEL_STYLES = {
    logging.DEBUG: _DIM,
    logging.INFO: "",  # No colour: healthy noise should not compete with status codes.
    logging.WARNING: _YELLOW,
    logging.ERROR: _RED,
    logging.CRITICAL: _BOLD_RED,
}


def _status_style(status: int) -> str:
    """Colour for an HTTP status: green 2xx, cyan 3xx, yellow 4xx, red 5xx."""
    if status < 300:
        return _GREEN
    if status < 400:
        return _CYAN
    if status < 500:
        return _YELLOW
    return _BOLD_RED


def _enable_windows_ansi() -> None:
    """Turn on virtual-terminal processing so ANSI codes render on Windows.

    Legacy ``conhost`` prints the escape sequences literally otherwise. Best
    effort: colour is cosmetic, so any failure here must never break logging.
    """
    try:  # pragma: no cover - platform specific
        from colorama import just_fix_windows_console

        just_fix_windows_console()
    except Exception:  # pragma: no cover - colorama is a win32-only click dep
        pass


def supports_color(stream: IO[str]) -> bool:
    """Whether ANSI colour should be written to ``stream``.

    Honours the ``NO_COLOR`` / ``FORCE_COLOR`` conventions so piping logs into a
    file or an aggregator yields clean text.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    try:
        if not stream.isatty():
            return False
    except (AttributeError, ValueError):  # detached or closed stream
        return False
    if sys.platform == "win32":
        _enable_windows_ansi()
    return True


class ConsoleLogFormatter(logging.Formatter):
    """Human-readable, colour-coded console output for local development.

    Access records — the ones ``main._log_access`` tags with ``status`` — are
    rendered as ``GET /api/v1/tasks 200 12.4ms`` with the status colour-coded,
    so a healthy run is legible at a glance instead of a wall of
    ``INFO:maestro.access:request``. Every other record keeps its logger name
    and message.
    """

    def __init__(self, *, color: bool) -> None:
        super().__init__(datefmt="%H:%M:%S")
        self._color = color

    def _paint(self, text: str, style: str) -> str:
        if not self._color or not style:
            return text
        return f"{style}{text}{_RESET}"

    def format(self, record: logging.LogRecord) -> str:
        stamp = self._paint(self.formatTime(record, self.datefmt), _DIM)
        level_style = _LEVEL_STYLES.get(record.levelno, "")
        level = self._paint(f"{record.levelname:<8}", level_style)
        line = f"{stamp} {level}{self._render_message(record)}"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            line = f"{line}\n{self.formatStack(record.stack_info)}"
        return line

    def _render_message(self, record: logging.LogRecord) -> str:
        status = getattr(record, "status", None)
        if not isinstance(status, int):
            return f"{self._paint(record.name, _DIM)}  {record.getMessage()}"
        parts = [
            str(getattr(record, "method", "")),
            str(getattr(record, "path", "")),
            self._paint(str(status), _status_style(status)),
        ]
        duration = getattr(record, "duration_ms", None)
        if duration is not None:
            parts.append(self._paint(f"{duration}ms", _DIM))
        return " ".join(part for part in parts if part)


class JsonLogFormatter(logging.Formatter):
    """Render each log record as a single-line JSON object.

    Keeps the fields an aggregator needs (timestamp, level, logger, message)
    and folds any structured ``extra=`` fields in without a dependency.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _route_uvicorn_logs() -> None:
    """Fold uvicorn's own loggers into the root handler.

    Uvicorn installs its handlers with ``propagate=False``, so without this its
    lines keep a second format — plain text even under ``LOG_FORMAT=json``.
    ``uvicorn.access`` is silenced outright rather than reformatted: the
    ``maestro.access`` middleware line reports the same request plus a request
    id and a duration, so keeping both would double every request.
    """
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    # No handlers and no propagation: records are dropped before any output.
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False


def configure_logging() -> None:
    """Install the root logging handler for the configured ``LOG_FORMAT``.

    ``json`` swaps in :class:`JsonLogFormatter`; anything else installs
    :class:`ConsoleLogFormatter`, which colour-codes HTTP status codes for local
    development. Either way uvicorn's loggers are folded into the same handler
    so the terminal carries one consistent stream.
    """
    level = settings.log_level.upper()
    handler = logging.StreamHandler()
    if settings.log_format.lower() == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(ConsoleLogFormatter(color=supports_color(handler.stream)))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    _route_uvicorn_logs()


def _scrub_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Strip credential-bearing fields from a Sentry event before it is sent.

    Second line of defence behind ``send_default_pii=False``: drops sensitive
    request headers and the request body (prompts may contain user data).
    """
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            for name in list(headers):
                if name.lower() in _SENSITIVE_HEADERS:
                    headers[name] = "[scrubbed]"
        # Bodies can carry prompts, API keys or card data — never ship them.
        request.pop("data", None)
    return event


def init_sentry() -> bool:
    """Initialise Sentry if ``SENTRY_DSN`` is set. Returns whether it was enabled.

    A no-op (returns ``False``) when the DSN is empty, so dev and CI stay free of
    any network egress or extra runtime cost.
    """
    dsn = settings.sentry_dsn.strip()
    if not dsn:
        return False

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment.strip() or settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        before_send=_scrub_event,
        integrations=[
            FastApiIntegration(),
            # Breadcrumbs from INFO+, and any logger.error/exception (including
            # background-task failures) becomes a Sentry event automatically.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    logger.info("Sentry error tracking enabled (env=%s)", settings.environment)
    return True
