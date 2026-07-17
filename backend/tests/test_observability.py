"""Observability: Sentry stays off without a DSN, and PII is scrubbed."""

from __future__ import annotations

import json
import logging
import sys

from app.core import observability
from app.core.config import settings
from app.core.observability import JsonLogFormatter, _scrub_event, init_sentry


def test_init_sentry_without_dsn_is_a_noop(monkeypatch) -> None:
    monkeypatch.setattr(settings, "sentry_dsn", "")

    assert init_sentry() is False


def test_init_sentry_blank_dsn_is_a_noop(monkeypatch) -> None:
    monkeypatch.setattr(settings, "sentry_dsn", "   ")

    assert init_sentry() is False


def test_scrub_event_masks_sensitive_headers() -> None:
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret-token",
                "X-Api-Key": "sk-live-123",
                "Content-Type": "application/json",
            }
        }
    }

    scrubbed = _scrub_event(event, {})

    headers = scrubbed["request"]["headers"]
    assert headers["Authorization"] == "[scrubbed]", headers
    assert headers["X-Api-Key"] == "[scrubbed]", headers
    # Non-sensitive headers are preserved.
    assert headers["Content-Type"] == "application/json", headers


def test_scrub_event_drops_request_body() -> None:
    event = {"request": {"data": {"prompt": "user's private prompt"}}}

    scrubbed = _scrub_event(event, {})

    assert "data" not in scrubbed["request"], scrubbed


def test_scrub_event_tolerates_missing_request() -> None:
    event = {"level": "error"}

    assert _scrub_event(event, {}) == {"level": "error"}


def test_json_formatter_emits_valid_json_with_core_fields() -> None:
    record = logging.LogRecord(
        name="maestro",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )

    line = JsonLogFormatter().format(record)
    payload = json.loads(line)

    assert payload["level"] == "INFO", payload
    assert payload["logger"] == "maestro", payload
    assert payload["message"] == "hello world", payload
    assert "timestamp" in payload, payload


def test_json_formatter_includes_exception_and_extra() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="maestro",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    record.task_id = "abc-123"  # structured extra field

    payload = json.loads(JsonLogFormatter().format(record))

    assert "ValueError: boom" in payload["exception"], payload
    assert payload["task_id"] == "abc-123", payload


def test_configure_logging_json_installs_json_handler(monkeypatch) -> None:
    monkeypatch.setattr(settings, "log_format", "json")
    monkeypatch.setattr(settings, "log_level", "INFO")

    try:
        observability.configure_logging()
        root = logging.getLogger()
        assert any(
            isinstance(h.formatter, JsonLogFormatter)
            for h in root.handlers
            if h.formatter is not None
        ), root.handlers
    finally:
        # Restore a plain handler so JSON lines don't leak into other tests.
        monkeypatch.setattr(settings, "log_format", "text")
        logging.getLogger().handlers.clear()
        logging.basicConfig(level=logging.INFO)
