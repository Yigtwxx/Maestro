"""Observability wiring: structured logging and Sentry error tracking.

Both are opt-in and degrade to no-ops so local development and the test suite
need no extra services:

* ``configure_logging`` picks a plain or JSON formatter from ``LOG_FORMAT``.
* ``init_sentry`` is a no-op unless ``SENTRY_DSN`` is set; when it is, it wires
  the FastAPI and logging integrations and scrubs PII before events leave the
  process (CLAUDE.md §9.1/§15 — API keys, prompts and card data never leave).
"""

from __future__ import annotations

import json
import logging
from typing import Any

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


def configure_logging() -> None:
    """Install the root logging handler for the configured ``LOG_FORMAT``.

    ``json`` swaps in :class:`JsonLogFormatter`; anything else keeps the plain
    ``basicConfig`` text format used during local development.
    """
    level = settings.log_level.upper()
    if settings.log_format.lower() == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(level)
    else:
        logging.basicConfig(level=level)


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
