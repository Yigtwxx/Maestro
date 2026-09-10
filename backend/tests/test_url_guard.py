"""SSRF guard for outbound, user-supplied URLs (``url_guard``) and its
enforcement in the custom OpenAI-compatible LLM adapter.

The custom provider lets an authenticated user store an arbitrary base_url the
backend later POSTs to server-side; without this guard that is an SSRF sink
onto cloud-metadata and internal services (CLAUDE.md §9.3/§9.4).
"""

from __future__ import annotations

import pytest

from app.services import llm_service
from app.services.llm_service import CustomOpenAICompatAdapter, LLMError
from app.utils import url_guard


@pytest.mark.parametrize(
    "url,reason",
    [
        ("ftp://host/x", url_guard.REASON_BAD_SCHEME),
        ("file:///etc/passwd", url_guard.REASON_BAD_SCHEME),
        ("not-a-url", url_guard.REASON_BAD_SCHEME),
        ("http://user:pass@host/x", url_guard.REASON_CREDENTIALS),
        ("http:///no-host/x", url_guard.REASON_NO_HOST),
    ],
)
def test_validate_url_shape_rejects_unsafe(url: str, reason: str) -> None:
    assert url_guard.validate_url_shape(url) == reason


@pytest.mark.parametrize("url", ["http://example.com/v1", "https://api.host:8443/v1"])
def test_validate_url_shape_accepts_wellformed(url: str) -> None:
    assert url_guard.validate_url_shape(url) is None


async def test_check_public_url_blocks_private_host(monkeypatch) -> None:
    monkeypatch.setattr(url_guard, "resolve_is_public", lambda hostname: False)
    reason = await url_guard.check_public_url("http://169.254.169.254/v1")
    assert reason == url_guard.REASON_NOT_PUBLIC


async def test_check_public_url_allows_public_host(monkeypatch) -> None:
    monkeypatch.setattr(url_guard, "resolve_is_public", lambda hostname: True)
    assert await url_guard.check_public_url("https://api.example.com/v1") is None


async def test_custom_adapter_rejects_private_endpoint_before_request(
    monkeypatch,
) -> None:
    """Request-time guard: the adapter refuses a non-public base_url before it
    ever reaches the network — this closes the DNS-rebinding window and covers
    keys stored before the guard existed."""
    monkeypatch.setattr(llm_service.settings, "llm_ssrf_guard_enabled", True)

    async def _blocked(url: str) -> str:
        return url_guard.REASON_NOT_PUBLIC

    monkeypatch.setattr(llm_service, "check_public_url", _blocked)
    adapter = CustomOpenAICompatAdapter(
        api_key="sk", model="m", base_url="http://169.254.169.254/v1"
    )
    with pytest.raises(LLMError, match="custom endpoint rejected"):
        await adapter._post("/chat/completions", {})


async def test_custom_adapter_guard_disabled_skips_check(monkeypatch) -> None:
    """With the guard off (self-hosted), the SSRF check is not consulted."""
    monkeypatch.setattr(llm_service.settings, "llm_ssrf_guard_enabled", False)
    called = False

    async def _tripwire(url: str) -> str | None:
        nonlocal called
        called = True
        return None

    async def _fake_super_post(self, path: str, payload: dict) -> dict:
        return {"ok": True}

    monkeypatch.setattr(llm_service, "check_public_url", _tripwire)
    monkeypatch.setattr(
        llm_service._OpenAICompatAdapter, "_post", _fake_super_post, raising=True
    )
    adapter = CustomOpenAICompatAdapter(
        api_key="sk", model="m", base_url="http://localhost:11434/v1"
    )
    result = await adapter._post("/chat/completions", {})
    assert result == {"ok": True}
    assert called is False, "guard must not run when disabled"


def test_a_name_that_does_not_exist_reads_differently_from_a_private_one():
    """Two failures, two places to look.

    Reporting a typo'd hostname as "not publicly routable" sends the user
    hunting for a network policy problem. Observed while registering a real MCP
    endpoint against a host that simply did not exist.
    """
    import asyncio

    from app.utils.url_guard import REASON_NO_DNS, REASON_NOT_PUBLIC, check_public_url

    assert (
        asyncio.run(check_public_url("https://no-such-host-xyz.invalid/mcp"))
        == REASON_NO_DNS
    )
    assert asyncio.run(check_public_url("http://127.0.0.1/mcp")) == REASON_NOT_PUBLIC


def test_pinning_rewrites_only_the_host():
    """The address is pinned; the path, query and port are untouched."""
    import asyncio

    from app.utils import url_guard as guard

    original = guard.resolve_addresses
    try:
        guard.resolve_addresses = lambda _h: {"93.184.216.34"}
        target, reason = asyncio.run(
            guard.pin_public_url("https://api.example.com:8443/v1/x?a=1")
        )
    finally:
        guard.resolve_addresses = original

    assert reason is None
    assert target.url == "https://93.184.216.34:8443/v1/x?a=1"
    assert target.host_header == "api.example.com:8443"
    assert target.sni_hostname == "api.example.com"


def test_a_host_answering_with_one_private_address_is_refused_whole():
    """A name resolving to one public and one private address is the rebinding
    setup itself; picking the public one would make it work."""
    import asyncio

    from app.utils import url_guard as guard

    original = guard.resolve_addresses
    try:
        guard.resolve_addresses = lambda _h: {"93.184.216.34", "10.0.0.5"}
        target, reason = asyncio.run(guard.pin_public_url("https://api.example.com/v1"))
    finally:
        guard.resolve_addresses = original

    assert target is None
    assert reason == guard.REASON_NOT_PUBLIC


async def test_a_pinned_request_never_shares_a_connection_across_hostnames():
    """The bug pinning introduces if it reuses the shared client.

    httpcore keys its pool on the origin, and after pinning that origin is the
    literal address — so two different hostnames behind one shared CDN address
    would share a TLS connection, and the second one's certificate would never
    be verified. Observed against two real CDN-fronted MCP servers. A dedicated
    client per pinned request makes the reuse structurally impossible; this
    pins that each call built its own.
    """
    import httpx

    from app.services import connected_common
    from app.utils import url_guard as guard

    built: list[httpx.AsyncClient] = []

    def factory() -> httpx.AsyncClient:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
            follow_redirects=False,
        )
        built.append(client)
        return client

    original_resolve = guard.resolve_addresses
    original_public = guard.resolve_is_public
    original_factory = connected_common.new_pinned_client
    try:
        guard.resolve_addresses = lambda _h: {"93.184.216.34"}
        guard.resolve_is_public = lambda _h: True
        connected_common.new_pinned_client = factory
        for host in ("a.example.com", "b.example.com"):
            await connected_common.request_api(
                f"https://{host}/v1",
                timeout=5,
                max_bytes=1000,
                log_target=host,
                pin_dns=True,
            )
    finally:
        guard.resolve_addresses = original_resolve
        guard.resolve_is_public = original_public
        connected_common.new_pinned_client = original_factory

    assert len(built) == 2, "the two hostnames shared a client"
    assert all(client.is_closed for client in built), "a pinned client leaked"
