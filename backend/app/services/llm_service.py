"""Provider-agnostic LLM service.

Each provider is an :class:`LLMAdapter`. The default/free adapter is
:class:`OllamaAdapter` (OpenAI-compatible, local). Adding a provider means
adding a new adapter class — existing code is never modified (CLAUDE.md §11, §15.5).

All network calls are wrapped with exponential-backoff retries via ``tenacity``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.constants import (
    ANTHROPIC_API_URL,
    ANTHROPIC_DEFAULT_MAX_TOKENS,
    ANTHROPIC_VERSION,
    GEMINI_API_BASE_URL,
    LLMProvider,
)

_HTTP_TIMEOUT = httpx.Timeout(
    settings.llm_request_timeout_seconds, connect=settings.llm_connect_timeout_seconds
)

# One process-wide client so chat/embedding calls reuse the keep-alive pool
# instead of paying a fresh TCP+TLS handshake per request. Created lazily;
# closed by the FastAPI lifespan on shutdown (see ``app.main``).
_client: httpx.AsyncClient | None = None


def _http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
    return _client


async def aclose() -> None:
    """Close the shared HTTP client. Idempotent; safe to call on shutdown."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _is_retryable(exc: BaseException) -> bool:
    """Retry transient failures only; 4xx (quota/auth) never recovers via retry.

    A read-timeout means the model is slow, not that the request is broken —
    retrying just triples the wait without fixing anything, so only connection-
    level failures (and 5xx) are treated as retryable.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    if isinstance(exc, httpx.ReadTimeout):
        return False
    return isinstance(exc, httpx.TransportError)


_retry_policy = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_retryable),
)


@dataclass(slots=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(slots=True)
class LLMResponse:
    content: str
    model: str
    tokens_used: int = 0
    raw: dict = field(default_factory=dict)


class LLMError(RuntimeError):
    """Raised when an LLM provider call fails."""


# --- Base adapter ---------------------------------------------------------


class LLMAdapter(ABC):
    """Interface every provider adapter must implement."""

    provider: LLMProvider

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Run a chat completion and return the assistant message."""


# --- OpenAI-compatible base (Ollama, OpenAI) ------------------------------


class _OpenAICompatAdapter(LLMAdapter):
    """Shared implementation for OpenAI-compatible ``/chat/completions`` APIs."""

    base_url: str
    default_model: str

    @_retry_policy
    async def _post(self, path: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = await _http_client().post(
            f"{self.base_url.rstrip('/')}{path}", json=payload, headers=headers
        )
        resp.raise_for_status()
        return resp.json()

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        model = self.model or self.default_model
        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        try:
            data = await self._post("/chat/completions", payload)
        except httpx.HTTPError as exc:  # network/HTTP failure after retries
            raise LLMError(f"{self.provider.value} chat failed") from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError("Malformed LLM response") from exc
        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            model=model,
            tokens_used=int(usage.get("total_tokens", 0)),
            raw=data,
        )


class OllamaAdapter(_OpenAICompatAdapter):
    """Free/local tier via Ollama's OpenAI-compatible endpoint."""

    provider = LLMProvider.OLLAMA
    base_url = settings.free_model_endpoint
    default_model = settings.free_model_name


class OpenAIAdapter(_OpenAICompatAdapter):
    """OpenAI provider (BYOK). Requires ``api_key``."""

    provider = LLMProvider.OPENAI
    base_url = "https://api.openai.com/v1"
    default_model = "gpt-4o-mini"


class GeminiAdapter(_OpenAICompatAdapter):
    """Google Gemini via its OpenAI-compatible endpoint (BYOK, free tier)."""

    provider = LLMProvider.GEMINI
    base_url = GEMINI_API_BASE_URL
    default_model = settings.gemini_model_name


# --- Anthropic (Messages API) ---------------------------------------------


class AnthropicAdapter(LLMAdapter):
    """Anthropic (Claude) provider (BYOK).

    The Messages API differs from the OpenAI schema: the system prompt is a
    top-level field (not a message), ``max_tokens`` is required, and the reply
    text lives under ``content[].text``. Auth uses the ``x-api-key`` header.
    """

    provider = LLMProvider.ANTHROPIC
    default_model = "claude-sonnet-5"

    @staticmethod
    def _split_system(messages: list[ChatMessage]) -> tuple[str, list[dict]]:
        """Separate the system prompt from the conversational turns."""
        system_parts = [m.content for m in messages if m.role == "system"]
        turns = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        return "\n\n".join(system_parts), turns

    @_retry_policy
    async def _post(self, payload: dict) -> dict:
        if not self.api_key:
            raise LLMError("Anthropic provider requires an API key (BYOK).")
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }
        resp = await _http_client().post(
            ANTHROPIC_API_URL, json=payload, headers=headers
        )
        resp.raise_for_status()
        return resp.json()

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        model = self.model or self.default_model
        system, turns = self._split_system(messages)
        payload: dict = {
            "model": model,
            "messages": turns,
            "max_tokens": max_tokens or ANTHROPIC_DEFAULT_MAX_TOKENS,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        try:
            data = await self._post(payload)
        except httpx.HTTPError as exc:  # network/HTTP failure after retries
            raise LLMError("anthropic chat failed") from exc
        try:
            blocks = data["content"]
            content = "".join(
                b.get("text", "") for b in blocks if b.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            raise LLMError("Malformed Anthropic response") from exc
        usage = data.get("usage") or {}
        tokens = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        return LLMResponse(content=content, model=model, tokens_used=tokens, raw=data)


# --- Fallback wrapper -------------------------------------------------------


class FallbackLLMAdapter(LLMAdapter):
    """Try ``primary`` per call; on any :class:`LLMError` retry with ``fallback``.

    Each ``chat()`` call attempts the primary independently, so a mid-task quota
    exhaustion (e.g. Gemini free-tier 429) only degrades the failing calls.
    ``on_fallback`` (if given) is awaited with the failure reason before the
    fallback call, so callers can surface the switch to the user.
    """

    def __init__(
        self,
        *,
        primary: LLMAdapter,
        fallback: LLMAdapter,
        on_fallback: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self.provider = primary.provider
        self.primary = primary
        self.fallback = fallback
        self.on_fallback = on_fallback

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        try:
            return await self.primary.chat(
                messages, temperature=temperature, max_tokens=max_tokens
            )
        except LLMError as exc:
            if self.on_fallback is not None:
                await self.on_fallback(str(exc))
            return await self.fallback.chat(
                messages, temperature=temperature, max_tokens=max_tokens
            )


class TokenMeter(LLMAdapter):
    """Counts tokens across every call made through the adapter it wraps.

    Wrapping the adapter once, at the top of a task, is what makes billing
    honest: orchestrator routing, main-agent planning and synthesis, reviewer
    passes and subagent work all flow through the same counter, whereas summing
    per-subagent metadata silently misses the rest.
    """

    def __init__(self, inner: LLMAdapter) -> None:
        super().__init__(api_key=None, model=inner.model)
        self.provider = inner.provider
        self.inner = inner
        self.total_tokens = 0

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        response = await self.inner.chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )
        self.total_tokens += response.tokens_used
        return response


# --- Factory --------------------------------------------------------------

_ADAPTERS: dict[LLMProvider, type[LLMAdapter]] = {
    LLMProvider.OLLAMA: OllamaAdapter,
    LLMProvider.OPENAI: OpenAIAdapter,
    LLMProvider.ANTHROPIC: AnthropicAdapter,
    LLMProvider.GEMINI: GeminiAdapter,
}


def get_adapter(
    provider: LLMProvider,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMAdapter:
    """Return an adapter instance for the given provider."""
    try:
        adapter_cls = _ADAPTERS[provider]
    except KeyError as exc:
        raise LLMError(f"Unsupported LLM provider: {provider}") from exc
    return adapter_cls(api_key=api_key, model=model)


# --- Embeddings (free/local via Ollama) -----------------------------------


@_retry_policy
async def _embed_request(inputs: list[str]) -> list[list[float]]:
    payload = {"model": settings.embedding_model_name, "input": inputs}
    base_url = settings.embedding_endpoint or settings.free_model_endpoint
    resp = await _http_client().post(f"{base_url.rstrip('/')}/embeddings", json=payload)
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in data["data"]]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts with the free/local embedding model (nomic-embed-text)."""
    if not texts:
        return []
    try:
        return await _embed_request(texts)
    except (httpx.HTTPError, KeyError) as exc:
        raise LLMError("Embedding request failed") from exc
