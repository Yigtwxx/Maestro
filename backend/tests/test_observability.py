"""Observability: Sentry stays off without a DSN, and PII is scrubbed."""

from __future__ import annotations

import io
import json
import logging
import sys

import pytest

from app.core import observability
from app.core.config import settings
from app.core.observability import (
    ConsoleLogFormatter,
    JsonLogFormatter,
    _scrub_event,
    init_sentry,
)


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


def _access_record(status: int, *, duration_ms: float = 12.4) -> logging.LogRecord:
    """An access record shaped like the one ``main._log_access`` emits."""
    record = logging.LogRecord(
        name="maestro.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request",
        args=(),
        exc_info=None,
    )
    record.request_id = "abc123"
    record.method = "GET"
    record.path = "/api/v1/tasks"
    record.status = status
    record.duration_ms = duration_ms
    return record


@pytest.mark.parametrize(
    "status,style",
    [(200, "\033[32m"), (302, "\033[36m"), (404, "\033[33m"), (500, "\033[1;31m")],
)
def test_console_formatter_colours_status_by_class(status: int, style: str) -> None:
    line = ConsoleLogFormatter(color=True).format(_access_record(status))

    assert f"{style}{status}\033[0m" in line, line


def test_console_formatter_renders_access_request_details() -> None:
    line = ConsoleLogFormatter(color=False).format(_access_record(200))

    assert "GET /api/v1/tasks 200 12.4ms" in line, line


def test_console_formatter_without_colour_emits_no_escape_codes() -> None:
    line = ConsoleLogFormatter(color=False).format(_access_record(500))

    assert "\033" not in line, line


def test_console_formatter_keeps_logger_name_for_plain_records() -> None:
    record = logging.LogRecord(
        name="maestro",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Maestro backend starting (env=%s)",
        args=("development",),
        exc_info=None,
    )

    line = ConsoleLogFormatter(color=False).format(record)

    assert "maestro" in line, line
    assert "Maestro backend starting (env=development)" in line, line


def test_console_formatter_appends_exception_traceback() -> None:
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

    line = ConsoleLogFormatter(color=False).format(record)

    assert "ValueError: boom" in line, line


def test_supports_color_respects_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")

    assert observability.supports_color(sys.stdout) is False


def test_supports_color_respects_force_color(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")

    assert observability.supports_color(sys.stdout) is True


def test_supports_color_is_false_for_a_non_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)

    assert observability.supports_color(io.StringIO()) is False


def test_configure_logging_text_installs_console_handler(monkeypatch) -> None:
    monkeypatch.setattr(settings, "log_format", "text")
    monkeypatch.setattr(settings, "log_level", "INFO")

    try:
        observability.configure_logging()
        root = logging.getLogger()
        assert any(
            isinstance(h.formatter, ConsoleLogFormatter) for h in root.handlers
        ), root.handlers
    finally:
        logging.getLogger().handlers.clear()
        logging.basicConfig(level=logging.INFO)


def test_configure_logging_silences_uvicorn_access_logger(monkeypatch) -> None:
    """Our own access line replaces uvicorn's, otherwise every request logs twice."""
    monkeypatch.setattr(settings, "log_format", "text")
    access = logging.getLogger("uvicorn.access")
    access.addHandler(logging.NullHandler())

    try:
        observability.configure_logging()

        assert access.handlers == [], access.handlers
        assert access.propagate is False
        # uvicorn's other loggers keep flowing, through the root handler.
        assert logging.getLogger("uvicorn.error").propagate is True
    finally:
        access.handlers.clear()
        access.propagate = True
        logging.getLogger().handlers.clear()
        logging.basicConfig(level=logging.INFO)


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
