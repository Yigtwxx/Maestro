"""The three ``url_guard`` gates in front of a user-supplied MCP host.

Same shape as ``test_custom_api_ssrf.py``, one step stronger: one logical tool
call is three connections, so the resolving check runs on *every* POST rather
than once per call.
"""

from __future__ import annotations

import time
import uuid

import httpx
import pytest

from app.core.config import settings
from app.schemas.mcp_server import McpServerCreate
from app.services import connected_common, mcp_transport
from app.services.mcp_transport import McpEndpoint, McpSession, McpTransportError
from app.utils import url_guard

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


# --- gate 3: call time, on every POST, and pinned ---------------------------


def _pin_to(monkeypatch, addresses: set[str] | None) -> list[str]:
    """Replace the DNS boundary and record which hostnames were resolved.

    ``url_guard.resolve_addresses`` is the real edge: ``_pin`` looks it up as a
    module global, so substituting it governs both the validation and the
    address the socket is pinned to.
    """
    resolved: list[str] = []

    def fake(hostname: str) -> set[str] | None:
        resolved.append(hostname)
        return addresses

    monkeypatch.setattr(url_guard, "resolve_addresses", fake)
    monkeypatch.setattr(
        url_guard,
        "resolve_is_public",
        lambda h: (
            addresses is not None
            and all(__import__("ipaddress").ip_address(a).is_global for a in addresses)
        ),
    )
    return resolved


def _capture_requests(monkeypatch) -> list:
    """Replace the *transport*, not the client.

    A hand-rolled fake client would not exercise ``_stream_capped``'s real
    build-then-send path, which is exactly where the pin is applied. A
    ``MockTransport`` behind a real ``AsyncClient`` keeps that path intact and
    still hands back the fully-built request, extensions included.
    """
    sent: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b'{"jsonrpc":"2.0","id":"x","result":{}}',
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    monkeypatch.setattr(connected_common, "get_client", lambda: client)
    monkeypatch.setattr(connected_common, "new_pinned_client", lambda: client)
    return sent


async def test_a_host_that_turns_private_after_registration_is_refused(monkeypatch):
    """A record outlives its validation, and the DNS for a host the user owns is
    theirs to change afterwards."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", True)
    _pin_to(monkeypatch, {"10.0.0.5"})
    with pytest.raises(McpTransportError, match="refused"):
        await mcp_transport.list_tools(
            McpEndpoint(url="https://mcp.example.com/mcp"),
            McpSession(),
            cursor=None,
            deadline=time.monotonic() + 5,
        )


async def test_a_host_that_stops_resolving_says_so(monkeypatch):
    """A typo reported as "not publicly routable" sends the user hunting for a
    network policy problem that does not exist."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", True)
    _pin_to(monkeypatch, None)
    with pytest.raises(McpTransportError, match="could not be resolved"):
        await mcp_transport.list_tools(
            McpEndpoint(url="https://mcp.example.com/mcp"),
            McpSession(),
            cursor=None,
            deadline=time.monotonic() + 5,
        )


async def test_the_socket_is_pinned_to_the_address_that_was_validated(monkeypatch):
    """The rebinding window, closed.

    Checking and then connecting by name leaves a gap in which the name can
    move. The request goes to the literal address instead — while ``Host`` and
    the TLS SNI still carry the real name, so virtual hosting routes and the
    certificate is still verified against what the user typed. Pinning the
    address must never become "skip the certificate check".
    """
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", True)
    _pin_to(monkeypatch, {"93.184.216.34"})
    sent = _capture_requests(monkeypatch)

    await mcp_transport.list_tools(
        McpEndpoint(url="https://mcp.example.com/mcp"),
        McpSession(),
        cursor=None,
        deadline=time.monotonic() + 5,
    )
    request = sent[0]
    assert request.url.host == "93.184.216.34"
    assert request.headers["Host"] == "mcp.example.com"
    assert request.extensions["sni_hostname"] == "mcp.example.com"


async def test_the_pin_runs_on_every_post_of_one_call(monkeypatch):
    """One tool call is three connections; pinning once would leave two to the
    resolver, and their answers can differ from the first."""
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", True)
    resolved = _pin_to(monkeypatch, {"93.184.216.34"})
    _capture_requests(monkeypatch)

    endpoint = McpEndpoint(url="https://mcp.example.com/mcp")
    # initialize is two POSTs (handshake + the initialized notification).
    await mcp_transport.initialize(endpoint, deadline=time.monotonic() + 5)
    assert len(resolved) == 2


async def test_nothing_is_pinned_when_the_guard_is_off(monkeypatch):
    monkeypatch.setattr(settings, "llm_ssrf_guard_enabled", False)
    resolved = _pin_to(monkeypatch, {"10.0.0.5"})
    sent = _capture_requests(monkeypatch)

    await mcp_transport.list_tools(
        McpEndpoint(url="https://mcp.example.com/mcp"),
        McpSession(),
        cursor=None,
        deadline=time.monotonic() + 5,
    )
    assert resolved == []
    assert sent[0].url.host == "mcp.example.com"
