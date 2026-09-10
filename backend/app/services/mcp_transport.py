"""Minimal JSON-RPC 2.0 client for remote MCP servers (Streamable HTTP only).

Four methods and no more: ``initialize`` -> ``notifications/initialized`` ->
``tools/list`` -> ``tools/call``, plus a best-effort session ``DELETE``. No GET
stream, no resumability, no server-to-client requests -- we advertise no
sampling, roots or elicitation capability, so a compliant server never sends one
and a non-compliant one is ignored.

**Local stdio is not a transport here and never will be.** Maestro is a hosted
platform; a stdio server means executing a process on our host, which is the
blast radius ``code_execution`` is default-off for.

**Why this exists instead of the official SDK.** The whole outbound-HTTP
security posture rests on one shared client -- ``connected_common.get_client()``
-- which follows no redirects, and on the ``maestro-http-client-follows-redirects``
semgrep rule that pins it. That rule is a source pattern scoped to this tree, so
a client constructed inside a dependency is invisible to it: adopting the SDK
would retire the invariant while CI stayed green. Against that, the protocol
surface actually needed here is four methods. This module constructs no HTTP
client of its own; every socket is the shared one.

The cost is owning the compatibility matrix, and it is bounded three ways: one
advertised protocol version, fail-soft on a version the server answers with, and
an integration test against a real server.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app.core.config import settings
from app.core.constants import (
    MCP_CALL_MAX_BYTES,
    MCP_LIST_MAX_BYTES,
    MCP_PROTOCOL_VERSION,
)
from app.services import connected_common

logger = logging.getLogger(__name__)

JSONRPC_VERSION = "2.0"

_ACCEPT = "application/json, text/event-stream"
_SESSION_HEADER = "mcp-session-id"
_PROTOCOL_HEADER = "MCP-Protocol-Version"
_JSON_CONTENT_TYPE = "application/json"
_SSE_CONTENT_TYPE = "text/event-stream"

# Long enough that a slow server is not cut off mid-handshake, short enough that
# a dead one does not eat a whole deadline on the first of three POSTs.
_MIN_POST_TIMEOUT_SECONDS = 1.0


class McpTransportError(RuntimeError):
    """A transport or protocol failure, carrying a model-readable reason.

    The message is ours, never the server's body: that body is written by a
    third party and would otherwise travel into a prompt or a log unfiltered.
    Raised inside this module and turned into a ``connected_common.failure()``
    sentence by ``mcp_service``; it never escapes into the subagent tool loop.
    """


@dataclass(frozen=True, slots=True)
class McpEndpoint:
    """Where to reach one server and how to authenticate to it.

    ``secret`` is kept out of ``repr`` and the override below keeps it out of
    every string form, so this object can appear in a traceback or a debugger
    without exposing a credential. Same contract as ``CustomApiTool``: do not
    add a field, a ``__str__`` or a ``dict()`` that undoes it.
    """

    url: str
    auth_mode: str = "none"
    auth_name: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    secret: str | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        return f"McpEndpoint(host={urlsplit(self.url).netloc!r})"

    __str__ = __repr__


@dataclass(slots=True)
class McpSession:
    """One server's session for the lifetime of a single tool call.

    Deliberately not cached on ``AgentContext``: a wave of parallel subagents
    shares one context, and mutable session state there is the class of bug
    ``_GrantState`` is local for. The cost is three POSTs per tool call.
    """

    session_id: str | None = None
    protocol_version: str = MCP_PROTOCOL_VERSION
    server_name: str = ""
    server_version: str = ""


def _log_target(url: str) -> str:
    """Host only.

    Not host+path like ``_safe_target``: several hosted MCP gateways key a
    tenant off a path segment, which makes the path closer to a credential than
    to a label.
    """
    return urlsplit(url).netloc or "<mcp server>"


def _headers(endpoint: McpEndpoint, session: McpSession | None) -> dict[str, str]:
    """Assemble one request's headers.

    Ordering is the point: the user's static headers go first and every platform
    header overwrites them, so a registered header can never rebind ``Accept``
    or replay a session id. Registration refuses those names as well
    (``MCP_FORBIDDEN_HEADERS``); this is the second lock.

    ``MCP-Protocol-Version`` is omitted while ``session`` is None -- the spec
    says a client must not send it on ``initialize``, and some servers 400 on it.
    """
    headers = dict(endpoint.headers)
    headers["Content-Type"] = _JSON_CONTENT_TYPE
    headers["Accept"] = _ACCEPT
    if session is not None:
        headers[_PROTOCOL_HEADER] = session.protocol_version
        if session.session_id:
            headers["Mcp-Session-Id"] = session.session_id
    if endpoint.secret:
        if endpoint.auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {endpoint.secret}"
        elif endpoint.auth_mode == "header" and endpoint.auth_name:
            headers[endpoint.auth_name] = endpoint.secret
    return headers


def parse_sse_json_rpc(body: str, request_id: str) -> dict[str, Any] | None:
    """Return the JSON-RPC message whose ``id`` matches, from an SSE body.

    Frames are separated by a blank line and only ``data:`` lines carry payload;
    a multi-line data field is joined with newlines, per the SSE spec. Three
    things are deliberately ignored: frames whose ``event:`` is present and not
    ``message``, messages carrying no ``id`` (progress notifications share this
    stream, and taking "the last frame" would hand one of those back as the
    answer), and ``id:``/``retry:`` lines, since this client does not resume.

    Returns None when the stream ended without the answer, which the caller
    reports as a failure rather than treating as an empty result.
    """
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    for frame in normalized.split("\n\n"):
        event = "message"
        data_lines: list[str] = []
        for line in frame.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                chunk = line[len("data:") :]
                data_lines.append(chunk[1:] if chunk.startswith(" ") else chunk)
        if event != "message" or not data_lines:
            continue
        try:
            message = json.loads("\n".join(data_lines))
        except Exception:  # noqa: BLE001 - a keep-alive or a partial frame
            continue
        if isinstance(message, dict) and str(message.get("id")) == request_id:
            return message
    return None


async def _post(
    endpoint: McpEndpoint,
    session: McpSession | None,
    payload: dict[str, Any],
    *,
    deadline: float,
    max_bytes: int,
) -> connected_common.TextResult:
    """One JSON-RPC POST through the shared, redirect-free client.

    The address is resolved, validated and **pinned** on *every* POST, not
    checked once per registration. One logical tool call is three connections, a
    record outlives its validation, and the DNS for a host the user owns is
    theirs to change between any two of them. Pinning means the socket lands on
    the address that was checked, so there is no window between the two -- while
    ``Host`` and SNI still carry the real name, so TLS verifies normally.
    """
    remaining = max(_MIN_POST_TIMEOUT_SECONDS, deadline - time.monotonic())
    result = await connected_common.request_text(
        endpoint.url,
        method="POST",
        headers=_headers(endpoint, session),
        json_body=payload,
        timeout=remaining,
        log_target=_log_target(endpoint.url),
        max_bytes=max_bytes,
        capture_headers=(_SESSION_HEADER,),
        pin_dns=settings.llm_ssrf_guard_enabled,
    )
    if result.refusal is not None:
        raise McpTransportError(f"the server address was refused: {result.refusal}")
    return result


def _dispatch(result: connected_common.TextResult, request_id: str) -> Any:
    """Turn one HTTP response into a JSON-RPC result, or raise a safe reason."""
    if result.status == 0:
        raise McpTransportError("the server could not be reached")
    if result.status == 202:
        return None  # A notification was accepted; there is no result.
    if 300 <= result.status < 400:
        raise McpTransportError("the server redirected, and redirects are not followed")
    if result.status == 404:
        raise McpTransportError("the server ended the session")
    if result.status >= 400:
        # Status only. An error body from a stranger has no business in a log.
        raise McpTransportError(f"the server answered {result.status}")
    if result.oversized:
        raise McpTransportError("the response was too large to read")

    if result.content_type == _JSON_CONTENT_TYPE:
        try:
            message = json.loads(result.text)
        except Exception as exc:  # noqa: BLE001 - a malformed body is a failure
            raise McpTransportError("the server sent a malformed reply") from exc
    elif result.content_type == _SSE_CONTENT_TYPE:
        message = parse_sse_json_rpc(result.text, request_id)
        if message is None:
            raise McpTransportError("the server's stream carried no reply")
    else:
        raise McpTransportError(
            f"the server replied with an unsupported content type "
            f"({result.content_type or 'none'})"
        )

    if not isinstance(message, dict):
        raise McpTransportError("the server sent a malformed reply")
    if "error" in message:
        detail = ""
        if isinstance(message["error"], dict):
            detail = connected_common.truncate(
                str(message["error"].get("message", "")), 200
            )
        raise McpTransportError(detail or "the server reported an error")
    return message.get("result")


async def _rpc(
    endpoint: McpEndpoint,
    session: McpSession | None,
    method: str,
    params: dict[str, Any] | None,
    *,
    deadline: float,
    max_bytes: int,
    notify: bool = False,
) -> tuple[Any, str | None]:
    """Send one JSON-RPC call and return its result plus any assigned session id.

    Request ids are UUIDs rather than a counter: an id comes back through a body
    we did not write and is string-compared, and two runs share one worker.
    """
    request_id = str(uuid.uuid4())
    payload: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": method}
    if params is not None:
        payload["params"] = params
    if not notify:
        payload["id"] = request_id

    result = await _post(
        endpoint, session, payload, deadline=deadline, max_bytes=max_bytes
    )
    assigned = result.headers.get(_SESSION_HEADER)
    if notify:
        # A notification has no id, so there is nothing to match. Anything but a
        # server error counts as delivered.
        if result.status >= 400:
            raise McpTransportError(f"the server answered {result.status}")
        return None, assigned
    return _dispatch(result, request_id), assigned


async def initialize(endpoint: McpEndpoint, *, deadline: float) -> McpSession:
    """Perform the handshake and return the session to use for later calls.

    A server answering with a protocol version we did not advertise is accepted
    and the value recorded rather than refused: the four methods used here have
    been stable across revisions, so failing closed on a version string would
    break more servers than it protects. The value is surfaced in the UI.
    """
    result, assigned = await _rpc(
        endpoint,
        None,
        "initialize",
        {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            # Empty on purpose: advertising no sampling, roots or elicitation
            # capability is what stops a compliant server ever sending us a
            # request we have no code to answer.
            "capabilities": {},
            "clientInfo": {"name": "maestro", "version": "1"},
        },
        deadline=deadline,
        max_bytes=MCP_LIST_MAX_BYTES,
    )
    info = result if isinstance(result, dict) else {}
    server_info = info.get("serverInfo")
    server_info = server_info if isinstance(server_info, dict) else {}
    session = McpSession(
        session_id=assigned,
        protocol_version=str(info.get("protocolVersion") or MCP_PROTOCOL_VERSION),
        server_name=str(server_info.get("name") or ""),
        server_version=str(server_info.get("version") or ""),
    )
    # Some servers refuse tools/list until this arrives. It is a notification,
    # so there is nothing to match and a 202 is the expected answer.
    await _rpc(
        endpoint,
        session,
        "notifications/initialized",
        {},
        deadline=deadline,
        max_bytes=MCP_LIST_MAX_BYTES,
        notify=True,
    )
    return session


async def list_tools(
    endpoint: McpEndpoint,
    session: McpSession,
    *,
    cursor: str | None,
    deadline: float,
) -> dict[str, Any]:
    """One page of the server's tool catalog."""
    params: dict[str, Any] = {}
    if cursor:
        params["cursor"] = cursor
    result, _ = await _rpc(
        endpoint,
        session,
        "tools/list",
        params,
        deadline=deadline,
        max_bytes=MCP_LIST_MAX_BYTES,
    )
    return result if isinstance(result, dict) else {}


async def call_tool(
    endpoint: McpEndpoint,
    session: McpSession,
    name: str,
    arguments: dict[str, Any],
    *,
    deadline: float,
) -> dict[str, Any]:
    """Invoke one tool by its *remote* name, verbatim as the server advertised it."""
    result, _ = await _rpc(
        endpoint,
        session,
        "tools/call",
        {"name": name, "arguments": arguments},
        deadline=deadline,
        max_bytes=MCP_CALL_MAX_BYTES,
    )
    return result if isinstance(result, dict) else {}


async def close(endpoint: McpEndpoint, session: McpSession) -> None:
    """Release the server's session. Best effort: every failure is swallowed.

    A server that cannot be told to forget a session will time it out on its
    own, and a task must never fail over housekeeping.
    """
    if not session.session_id:
        return
    try:
        await connected_common.request_text(
            endpoint.url,
            method="DELETE",
            headers=_headers(endpoint, session),
            timeout=float(_MIN_POST_TIMEOUT_SECONDS),
            log_target=_log_target(endpoint.url),
            max_bytes=1024,
        )
    except Exception:  # noqa: BLE001 - housekeeping must never fail a task
        logger.debug("MCP session close failed for %s", _log_target(endpoint.url))
