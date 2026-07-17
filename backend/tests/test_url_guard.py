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
