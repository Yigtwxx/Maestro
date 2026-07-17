"""Tests for the Gemini adapter, fallback wrapper, and retry predicate."""

from __future__ import annotations

import httpx
import pytest

from app.core.constants import (
    GEMINI_API_BASE_URL,
    LLM_CHAT_PROVIDERS,
    LLMProvider,
)
from app.services.llm_service import (
    _ADAPTERS,
    ChatMessage,
    CustomOpenAICompatAdapter,
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


async def test_chat_non_ascii_api_key_raises_clear_llm_error():
    """A mis-pasted key with a non-ASCII character must fail with a clear
    LLMError, not a raw httpx UnicodeEncodeError (which the agent layer would
    otherwise surface to the user as an opaque "all subtasks failed")."""
    # 'ı' (U+0131) mid-key: httpx cannot ASCII-encode the Authorization header.
    # NOTE: deliberately not a real Google key shape (no "AIza" prefix) so
    # secret scanners don't flag this fixture.
    adapter = get_adapter(
        LLMProvider.GEMINI, api_key="fake-gemini-key-ABCDEFGHIJKLMNOPQRSTUVWıXYZ"
    )
    with pytest.raises(LLMError):
        await adapter.chat([ChatMessage("user", "merhaba")])


async def test_anthropic_non_ascii_api_key_raises_clear_llm_error():
    """Same guard on the Anthropic ``x-api-key`` header path."""
    # Not a real Anthropic key shape (avoids secret scanners); the 'ı' is
    # the only thing under test.
    adapter = get_adapter(LLMProvider.ANTHROPIC, api_key="fake-anthropic-key-ıllegal")
    with pytest.raises(LLMError):
        await adapter.chat([ChatMessage("user", "merhaba")])


# --- Provider registry / new OpenAI-compatible brains -----------------------


def test_every_chat_provider_has_an_adapter():
    """LLM_CHAT_PROVIDERS and the adapter registry must never drift apart."""
    missing = LLM_CHAT_PROVIDERS - set(_ADAPTERS)
    assert not missing, f"chat providers without adapters: {missing}"


@pytest.mark.parametrize(
    "provider",
    [
        LLMProvider.GROQ,
        LLMProvider.DEEPSEEK,
        LLMProvider.MISTRAL,
        LLMProvider.XAI,
        LLMProvider.OPENROUTER,
        LLMProvider.TOGETHER,
        LLMProvider.PERPLEXITY,
    ],
)
def test_get_adapter_named_openai_compat_has_endpoint_and_model(provider: LLMProvider):
    adapter = get_adapter(provider, api_key="k")
    assert adapter.provider is provider
    assert adapter.base_url.startswith("https://"), f"{provider} needs a base URL"
    assert adapter.default_model, f"{provider} needs a default model"


# --- Custom OpenAI-compatible provider --------------------------------------


def test_get_adapter_custom_uses_supplied_endpoint_and_model():
    adapter = get_adapter(
        LLMProvider.CUSTOM,
        api_key="k",
        base_url="https://my-host/v1",
        model="llama-3.1-8b",
    )
    assert isinstance(adapter, CustomOpenAICompatAdapter)
    assert adapter.base_url == "https://my-host/v1"
    assert adapter.model == "llama-3.1-8b"


def test_get_adapter_named_provider_ignores_base_url_override():
    """A base_url passed for a named provider must not shadow its endpoint."""
    adapter = get_adapter(LLMProvider.GEMINI, api_key="k", base_url="https://evil/v1")
    assert adapter.base_url == GEMINI_API_BASE_URL


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
