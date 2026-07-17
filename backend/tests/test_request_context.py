"""Request-ID middleware and structured access logging."""

from __future__ import annotations

import logging

import pytest
from fastapi import Request

from app.main import _unhandled_exception_handler, app


async def test_response_carries_unique_request_id(client) -> None:
    first = await client.get("/health")
    second = await client.get("/health")

    assert "X-Request-ID" in first.headers, first.headers
    assert "X-Request-ID" in second.headers, second.headers
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


async def test_access_log_records_structured_fields(client, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="maestro.access"):
        resp = await client.get("/does-not-exist")

    assert resp.status_code == 404, resp.text
    records = [r for r in caplog.records if r.name == "maestro.access"]
    assert len(records) == 1, records
    record = records[0]
    assert record.method == "GET"
    assert record.path == "/does-not-exist"
    assert record.status == 404
    assert record.request_id == resp.headers["X-Request-ID"]
    assert record.duration_ms >= 0


async def test_health_probes_are_not_access_logged(client, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="maestro.access"):
        await client.get("/health")

    records = [r for r in caplog.records if r.name == "maestro.access"]
    assert records == [], records


async def test_unhandled_error_still_emits_access_log_line(client, caplog) -> None:
    async def _boom() -> None:
        raise RuntimeError("boom")

    app.router.add_api_route("/_test/boom", _boom)
    try:
        with caplog.at_level(logging.INFO, logger="maestro.access"):
            # ServerErrorMiddleware re-raises after sending the 500, and the
            # ASGI test transport surfaces that re-raise as an exception.
            with pytest.raises(RuntimeError, match="boom"):
                await client.get("/_test/boom")
    finally:
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "path", None) != "/_test/boom"
        ]

    records = [r for r in caplog.records if r.name == "maestro.access"]
    assert len(records) == 1, records
    assert records[0].status == 500
    assert records[0].path == "/_test/boom"


async def test_exception_handler_returns_request_id_and_cors_headers() -> None:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/tasks",
        "headers": [(b"origin", b"http://localhost:3000")],
        "query_string": b"",
        "server": ("test", 80),
        "scheme": "http",
    }
    request = Request(scope)
    request.state.request_id = "abc123"

    response = await _unhandled_exception_handler(request, RuntimeError("secret"))

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "abc123"
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    # The raw exception message must never leak into the response body.
    assert b"secret" not in response.body
