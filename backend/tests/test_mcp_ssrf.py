"""The three ``url_guard`` gates in front of a user-supplied MCP host.

Same shape as ``test_custom_api_ssrf.py``, one step stronger: one logical tool
call is three connections, so the resolving check runs on *every* POST rather
than once per call.
"""

from __future__ import annotations

import time
import uuid

import pytest

from app.core.config import settings
from app.schemas.mcp_server import McpServerCreate
from app.services import connected_common, mcp_transport
from app.services.mcp_transport import McpEndpoint, McpSession, McpTransportError

_PASSWORD = "supersecret"
USER = uuid.uuid4()


@pytest.fixture(autouse=True)
def _mcp_on(monkeypatch):
    """The feature ships off, so every route test here opts in.

    Its own refusal — a 403 from ``_require_enabled`` before the host is even
    looked at — is covered in ``test_mcp_servers_api.py``.
    """
    monkeypatch.setattr(settings, "mcp_enabled", True)


_BASE = {
    "slug": "acme",
    "name": "Acme Tools",
    "url": "https://mcp.example.com/mcp",
}


def _payload(**overrides) -> dict:
    return {**_BASE, **overrides}


async def _register_and_login(client, email: str) -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "Owner"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# --- gate 1: the schema, sync and DNS-free ---------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "ftp://mcp.example.com/mcp",
        "http://user:password@mcp.example.com/mcp",
        "not a url",
        "https://mcp.example.com/mcp#frag",
    ],
)
def test_a_malformed_or_credentialed_url_is_refused_at_the_schema(url):
    with pytest.raises(Exception, match="url"):
        McpServerCreate(**_payload(url=url))


# --- gate 2: the route, resolving ------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/mcp",
        "http://127.0.0.1:8000/mcp",
        "http://localhost:5432/mcp",
        "http://10.0.0.5/mcp",
        "http://192.168.1.1/mcp",
    ],
)
async def test_registration_rejects_a_private_or_metadata_host(client, mcp_db, url):
    auth = await _register_and_login(client, f"mcp-ssrf-{abs(hash(url))}@example.com")
    resp = await client.post(
        "/api/v1/mcp-servers", json=_payload(url=url), headers=auth
    )
    assert resp.status_code == 422, resp.text


async def test_registration_rejects_a_host_that_does_not_resolve(client, mcp_db):
    auth = await _register_and_login(client, "mcp-ssrf-nx@example.com")
    resp = await client.post(
        "/api/v1/mcp-servers",
        json=_payload(url="https://this-host-does-not-resolve.invalid/mcp"),
        headers=auth,
    )
    assert resp.status_code == 422, resp.text


async def test_the_route_check_is_skipped_when_the_guard_is_off(
    client, mcp_db, monkeypatch
):
    """Honoured in one place and not the other would make a host registrable and
    then silently unusable."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)
    auth = await _register_and_login(client, "mcp-ssrf-off@example.com")
    resp = await client.post(
        "/api/v1/mcp-servers",
        json=_payload(url="http://127.0.0.1:9/mcp"),
        headers=auth,
    )
    assert resp.status_code == 201, resp.text


# --- gate 3: call time, on every POST --------------------------------------


async def test_a_host_that_turns_private_after_registration_is_refused(monkeypatch):
    """A record outlives its validation, and the DNS for a host the user owns is
    theirs to change afterwards."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", True)

    async def now_private(_url):
        return "resolves to a private address"

    monkeypatch.setattr(mcp_transport, "check_public_url", now_private)
    with pytest.raises(McpTransportError, match="refused"):
        await mcp_transport.list_tools(
            McpEndpoint(url="https://mcp.example.com/mcp"),
            McpSession(),
            cursor=None,
            deadline=time.monotonic() + 5,
        )


async def test_the_check_runs_on_every_post_of_one_call(monkeypatch):
    """One tool call is three connections; checking once would leave two
    unguarded, and their DNS can differ from the first."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", True)
    checked: list[str] = []

    async def record(url):
        checked.append(url)
        return None

    monkeypatch.setattr(mcp_transport, "check_public_url", record)

    async def fake_request_text(url, **kwargs):  # noqa: ANN001
        return connected_common.TextResult(
            text='{"jsonrpc":"2.0","id":"x","result":{}}',
            content_type="application/json",
            status=200,
        )

    monkeypatch.setattr(connected_common, "request_text", fake_request_text)
    endpoint = McpEndpoint(url="https://mcp.example.com/mcp")
    # initialize is two POSTs (handshake + the initialized notification).
    await mcp_transport.initialize(endpoint, deadline=time.monotonic() + 5)
    assert len(checked) == 2


async def test_the_call_time_check_is_skipped_when_the_guard_is_off(monkeypatch):
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)
    called: list[str] = []

    async def record(url):
        called.append(url)
        return "would have been refused"

    monkeypatch.setattr(mcp_transport, "check_public_url", record)

    async def fake_request_text(url, **kwargs):  # noqa: ANN001
        return connected_common.TextResult(
            text='{"jsonrpc":"2.0","id":"x","result":{}}',
            content_type="application/json",
            status=200,
        )

    monkeypatch.setattr(connected_common, "request_text", fake_request_text)
    await mcp_transport.list_tools(
        McpEndpoint(url="https://mcp.example.com/mcp"),
        McpSession(),
        cursor=None,
        deadline=time.monotonic() + 5,
    )
    assert called == []
