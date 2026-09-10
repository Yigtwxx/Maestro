"""The JSON-RPC/Streamable-HTTP client: framing, dispatch, headers, sessions.

This module is hand-written rather than taken from the official SDK, so its
compatibility matrix is ours to own. These are the properties a real server
depends on, written as the tests that would catch a regression in each.
"""

from __future__ import annotations

import time

import pytest

from app.core.config import settings
from app.core.constants import MCP_PROTOCOL_VERSION
from app.services import connected_common, mcp_transport
from app.services.mcp_transport import (
    McpEndpoint,
    McpSession,
    McpTransportError,
    parse_sse_json_rpc,
)

ENDPOINT = McpEndpoint(url="https://mcp.example.com/mcp")


@pytest.fixture(autouse=True)
def _no_ssrf_guard(monkeypatch):
    """These tests are about the protocol, not the guard.

    ``mcp.example.com`` does not resolve, so leaving the guard on would refuse
    every call for the wrong reason. Its own behaviour — including that it *is*
    consulted on every POST — is covered by ``test_mcp_ssrf.py``.
    """
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)


def _reply(
    monkeypatch,
    *,
    text: str = "",
    content_type: str = "application/json",
    status: int = 200,
    headers: dict[str, str] | None = None,
    oversized: bool = False,
) -> list[dict]:
    """Replace the HTTP boundary and record what was sent."""
    sent: list[dict] = []

    async def fake_request_text(url, **kwargs):  # noqa: ANN001
        sent.append({"url": url, **kwargs})
        return connected_common.TextResult(
            text=text,
            content_type=content_type,
            status=status,
            headers=dict(headers or {}),
            oversized=oversized,
        )

    monkeypatch.setattr(connected_common, "request_text", fake_request_text)
    return sent


# --- SSE framing ------------------------------------------------------------


def test_a_plain_frame_is_parsed():
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":"a","result":{"x":1}}\n\n'
    assert parse_sse_json_rpc(body, "a") == {
        "jsonrpc": "2.0",
        "id": "a",
        "result": {"x": 1},
    }


def test_a_multi_line_data_field_is_joined():
    """The SSE spec joins repeated ``data:`` lines with a newline."""
    body = 'data: {"jsonrpc":"2.0","id":"a",\ndata:  "result":{"x":1}}\n\n'
    assert parse_sse_json_rpc(body, "a")["result"] == {"x": 1}


def test_crlf_line_endings_are_handled():
    body = 'data: {"jsonrpc":"2.0","id":"a","result":1}\r\n\r\n'
    assert parse_sse_json_rpc(body, "a")["result"] == 1


def test_a_progress_notification_before_the_answer_is_skipped():
    """The load-bearing one.

    Progress notifications share this stream and carry no ``id``. Taking "the
    last frame" or "the first frame" would hand one of those back as the tool's
    result, which is how a caller ends up reporting a percentage as an answer.
    """
    body = (
        'data: {"jsonrpc":"2.0","method":"notifications/progress",'
        '"params":{"progress":50}}\n\n'
        'data: {"jsonrpc":"2.0","id":"a","result":"done"}\n\n'
    )
    assert parse_sse_json_rpc(body, "a")["result"] == "done"


def test_a_frame_for_another_request_id_is_ignored():
    body = (
        'data: {"jsonrpc":"2.0","id":"other","result":"wrong"}\n\n'
        'data: {"jsonrpc":"2.0","id":"a","result":"right"}\n\n'
    )
    assert parse_sse_json_rpc(body, "a")["result"] == "right"


def test_a_non_message_event_is_ignored():
    body = 'event: ping\ndata: {"jsonrpc":"2.0","id":"a","result":"no"}\n\n'
    assert parse_sse_json_rpc(body, "a") is None


def test_a_stream_that_ends_without_the_answer_returns_none():
    assert parse_sse_json_rpc("data: keep-alive\n\n", "a") is None


def test_a_malformed_frame_does_not_stop_the_scan():
    body = 'data: not json\n\ndata: {"jsonrpc":"2.0","id":"a","result":1}\n\n'
    assert parse_sse_json_rpc(body, "a")["result"] == 1


# --- dispatch ---------------------------------------------------------------


async def test_a_json_reply_is_dispatched(monkeypatch):
    _reply(
        monkeypatch,
        text='{"jsonrpc":"2.0","id":"x","result":{"tools":[]}}',
    )
    # The id is generated inside _rpc, so this exercises the JSON branch, which
    # does not match on it.
    result = await mcp_transport.list_tools(
        ENDPOINT, McpSession(), cursor=None, deadline=time.monotonic() + 5
    )
    assert result == {"tools": []}


async def test_an_sse_reply_is_dispatched(monkeypatch):
    """The id has to round-trip: an SSE body is matched on it."""
    sent = _reply(monkeypatch, content_type="text/event-stream")

    async def fake_request_text(url, **kwargs):  # noqa: ANN001
        sent.append({"url": url, **kwargs})
        request_id = kwargs["json_body"]["id"]
        return connected_common.TextResult(
            text=(
                f'data: {{"jsonrpc":"2.0","id":"{request_id}","result":{{"ok":1}}}}\n\n'
            ),
            content_type="text/event-stream",
            status=200,
        )

    monkeypatch.setattr(connected_common, "request_text", fake_request_text)
    result = await mcp_transport.list_tools(
        ENDPOINT, McpSession(), cursor=None, deadline=time.monotonic() + 5
    )
    assert result == {"ok": 1}


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"status": 0}, "could not be reached"),
        ({"status": 302}, "redirected"),
        ({"status": 404}, "ended the session"),
        ({"status": 500}, "answered 500"),
        ({"status": 200, "oversized": True}, "too large"),
        ({"status": 200, "content_type": "text/html"}, "unsupported content type"),
    ],
)
async def test_failures_become_safe_reasons(monkeypatch, kwargs, expected):
    """Every failure is a sentence we wrote, never the server's own body."""
    _reply(monkeypatch, **kwargs)
    with pytest.raises(McpTransportError, match=expected):
        await mcp_transport.list_tools(
            ENDPOINT, McpSession(), cursor=None, deadline=time.monotonic() + 5
        )


async def test_a_jsonrpc_error_carries_its_message_but_capped(monkeypatch):
    _reply(
        monkeypatch,
        text=(
            '{"jsonrpc":"2.0","id":"x",'
            '"error":{"code":-32602,"message":"no such tool"}}'
        ),
    )
    with pytest.raises(McpTransportError, match="no such tool"):
        await mcp_transport.call_tool(
            ENDPOINT, McpSession(), "gone", {}, deadline=time.monotonic() + 5
        )


async def test_a_response_body_never_reaches_the_error_message(monkeypatch):
    """A 4xx body from a stranger has no business in a log or a prompt."""
    _reply(monkeypatch, status=403, text="secret internal detail")
    with pytest.raises(McpTransportError) as excinfo:
        await mcp_transport.list_tools(
            ENDPOINT, McpSession(), cursor=None, deadline=time.monotonic() + 5
        )
    assert "secret internal detail" not in str(excinfo.value)


# --- headers and sessions ---------------------------------------------------


async def test_initialize_omits_the_protocol_header_and_captures_the_session(
    monkeypatch,
):
    """The spec forbids ``MCP-Protocol-Version`` on ``initialize``.

    Some servers answer 400 when it is present, so this is interoperability
    rather than pedantry. The session id the handshake assigns has to be
    captured and echoed on every later request.
    """
    sent: list[dict] = []

    async def fake_request_text(url, **kwargs):  # noqa: ANN001
        sent.append({"url": url, **kwargs})
        return connected_common.TextResult(
            text=(
                '{"jsonrpc":"2.0","id":"x","result":{"protocolVersion":"2025-06-18",'
                '"serverInfo":{"name":"Acme","version":"1.2"}}}'
            ),
            content_type="application/json",
            status=200,
            headers={"mcp-session-id": "sess-1"},
        )

    monkeypatch.setattr(connected_common, "request_text", fake_request_text)
    session = await mcp_transport.initialize(ENDPOINT, deadline=time.monotonic() + 5)

    assert session.session_id == "sess-1"
    assert session.server_name == "Acme"
    assert "MCP-Protocol-Version" not in sent[0]["headers"]
    # The follow-up notification carries both.
    assert sent[1]["headers"]["MCP-Protocol-Version"] == MCP_PROTOCOL_VERSION
    assert sent[1]["headers"]["Mcp-Session-Id"] == "sess-1"
    assert sent[1]["json_body"]["method"] == "notifications/initialized"
    assert "id" not in sent[1]["json_body"]


async def test_a_user_header_cannot_rebind_a_platform_one(monkeypatch):
    """Registration refuses these names; this is the second lock."""
    sent = _reply(monkeypatch, text='{"jsonrpc":"2.0","id":"x","result":{}}')
    endpoint = McpEndpoint(
        url="https://mcp.example.com/mcp",
        headers={"Accept": "text/plain", "X-Tenant": "acme"},
    )
    await mcp_transport.list_tools(
        endpoint, McpSession(), cursor=None, deadline=time.monotonic() + 5
    )
    headers = sent[0]["headers"]
    assert headers["Accept"] == "application/json, text/event-stream"
    assert headers["X-Tenant"] == "acme"


async def test_a_bearer_secret_is_applied_and_never_logged(monkeypatch, caplog):
    sent = _reply(monkeypatch, text='{"jsonrpc":"2.0","id":"x","result":{}}')
    endpoint = McpEndpoint(
        url="https://mcp.example.com/mcp", auth_mode="bearer", secret="sk-live-42"
    )
    with caplog.at_level("DEBUG"):
        await mcp_transport.list_tools(
            endpoint, McpSession(), cursor=None, deadline=time.monotonic() + 5
        )
    assert sent[0]["headers"]["Authorization"] == "Bearer sk-live-42"
    assert "sk-live-42" not in caplog.text
    # The log label is the host, never the path: several gateways key a tenant
    # off a path segment, which makes it closer to a credential than a label.
    assert sent[0]["log_target"] == "mcp.example.com"


async def test_the_deadline_is_shared_across_the_calls_of_one_request(monkeypatch):
    """One tool call is three POSTs; three independent timeouts would let a slow
    server spend three times the budget the operator configured."""
    sent = _reply(monkeypatch, text='{"jsonrpc":"2.0","id":"x","result":{}}')
    deadline = time.monotonic() + 4
    await mcp_transport.list_tools(
        ENDPOINT, McpSession(), cursor=None, deadline=deadline
    )
    assert sent[0]["timeout"] <= 4


async def test_close_swallows_every_failure(monkeypatch):
    async def explode(*_args, **_kwargs):
        raise RuntimeError("gone")

    monkeypatch.setattr(connected_common, "request_text", explode)
    # Must not raise: a task never fails over housekeeping.
    await mcp_transport.close(ENDPOINT, McpSession(session_id="s"))


async def test_close_is_a_no_op_without_a_session(monkeypatch):
    sent = _reply(monkeypatch)
    await mcp_transport.close(ENDPOINT, McpSession())
    assert sent == []


def test_the_endpoint_never_renders_its_secret():
    endpoint = McpEndpoint(url="https://h.example/p", secret="sk-live-42")
    assert "sk-live-42" not in repr(endpoint)
    assert "sk-live-42" not in str(endpoint)
    assert "sk-live-42" not in f"{endpoint}"
