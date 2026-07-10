"""Tests for the Gemini adapter, fallback wrapper, and retry predicate."""

from __future__ import annotations

import httpx
import pytest

from app.core.constants import GEMINI_API_BASE_URL, LLMProvider
from app.services.llm_service import (
    ChatMessage,
    FallbackLLMAdapter,
    GeminiAdapter,
    LLMAdapter,
    LLMError,
    LLMResponse,
    _is_retryable,
    get_adapter,
)


class _StubAdapter(LLMAdapter):
    """In-memory adapter that either answers or raises (no network)."""

    provider = LLMProvider.OLLAMA

    def __init__(self, *, response: LLMResponse | None = None) -> None:
        super().__init__()
        self.response = response
        self.calls = 0

    async def chat(self, messages, *, temperature=0.2, max_tokens=None):  # noqa: ANN001
        self.calls += 1
        if self.response is None:
            raise LLMError("quota exceeded")
        return self.response


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://test")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


# --- GeminiAdapter ----------------------------------------------------------


def test_get_adapter_gemini_returns_gemini_adapter():
    adapter = get_adapter(LLMProvider.GEMINI, api_key="k")
    assert isinstance(adapter, GeminiAdapter)
    assert adapter.base_url == GEMINI_API_BASE_URL
    assert adapter.default_model, "GeminiAdapter must have a default model"


# --- FallbackLLMAdapter -----------------------------------------------------


async def test_fallback_primary_success_skips_fallback():
    primary = _StubAdapter(response=LLMResponse(content="from-primary", model="g"))
    fallback = _StubAdapter(response=LLMResponse(content="from-fallback", model="q"))
    adapter = FallbackLLMAdapter(primary=primary, fallback=fallback)

    resp = await adapter.chat([ChatMessage("user", "hi")])

    assert resp.content == "from-primary"
    assert fallback.calls == 0, "fallback must not be called when primary succeeds"


async def test_fallback_primary_error_uses_fallback_and_notifies():
    primary = _StubAdapter(response=None)  # raises LLMError
    fallback = _StubAdapter(response=LLMResponse(content="from-fallback", model="q"))
    reasons: list[str] = []

    async def on_fallback(reason: str) -> None:
        reasons.append(reason)

    adapter = FallbackLLMAdapter(
        primary=primary, fallback=fallback, on_fallback=on_fallback
    )
    resp = await adapter.chat([ChatMessage("user", "hi")])

    assert resp.content == "from-fallback"
    assert reasons == ["quota exceeded"]


async def test_fallback_both_fail_raises_llm_error():
    adapter = FallbackLLMAdapter(
        primary=_StubAdapter(response=None), fallback=_StubAdapter(response=None)
    )
    with pytest.raises(LLMError):
        await adapter.chat([ChatMessage("user", "hi")])


def test_fallback_reports_primary_provider():
    primary = get_adapter(LLMProvider.GEMINI, api_key="k")
    adapter = FallbackLLMAdapter(
        primary=primary, fallback=get_adapter(LLMProvider.OLLAMA)
    )
    assert adapter.provider is LLMProvider.GEMINI


# --- Retry predicate --------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_http_status_error(429), False),  # quota: retry never helps
        (_http_status_error(401), False),
        (_http_status_error(500), True),
        (_http_status_error(503), True),
        (httpx.ConnectError("down"), True),
        (httpx.ConnectTimeout("slow to connect"), True),
        (httpx.ReadTimeout("model is slow"), False),  # retrying won't speed it up
        (ValueError("other"), False),
    ],
)
def test_is_retryable(exc: BaseException, expected: bool):
    assert _is_retryable(exc) is expected, f"{exc!r} should be retryable={expected}"
