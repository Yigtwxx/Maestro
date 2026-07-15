"""Provider-agnostic LLM service.

Each provider is an :class:`LLMAdapter`. The default/free adapter is
:class:`OllamaAdapter` (OpenAI-compatible, local). Adding a provider means
adding a new adapter class — existing code is never modified (CLAUDE.md §11, §15.5).

All network calls are wrapped with exponential-backoff retries via ``tenacity``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from math import ceil

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
    DEEPSEEK_API_BASE_URL,
    GEMINI_API_BASE_URL,
    GROQ_API_BASE_URL,
    LLM_CHAT_PROVIDERS,
    MISTRAL_API_BASE_URL,
    MODEL_TIER_DEFAULTS,
    OPENROUTER_API_BASE_URL,
    PERPLEXITY_API_BASE_URL,
    PROVIDER_TIER_MODELS,
    TOGETHER_API_BASE_URL,
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
    XAI_API_BASE_URL,
    LLMProvider,
)
from app.utils.url_guard import check_public_url

logger = logging.getLogger(__name__)

# Cap the provider error body copied into logs/messages: enough to see "model
# not found" without dumping a whole HTML error page. Never includes headers,
# so the Authorization bearer (the API key) can never leak here.
_ERROR_BODY_MAX = 300

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
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str


@dataclass(slots=True)
class ToolCall:
    """A model's request to invoke a tool (native function calling)."""

    id: str
    name: str
    arguments: dict


@dataclass(slots=True)
class LLMResponse:
    content: str
    model: str
    tokens_used: int = 0
    # Split usage (feeds cost/trace breakdowns); ``tokens_used`` stays the total.
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Which provider actually served the call (set by the concrete adapter; a
    # FallbackLLMAdapter forwards the inner response so this stays accurate).
    provider: LLMProvider | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdapterCapabilities:
    """What an adapter's provider supports, so call sites branch on capability
    rather than on provider name (Backend v2 §4.4)."""

    streaming: bool = False
    native_tools: bool = False
    json_schema: bool = False  # provider-enforced structured output


@dataclass(slots=True)
class ToolDef:
    """Provider-agnostic tool declaration (maps to each provider's tool schema)."""

    name: str
    description: str
    parameters: dict  # JSON schema


@dataclass(slots=True)
class StreamEvent:
    """One chunk of a streamed completion."""

    kind: str  # "text_delta" | "tool_call" | "usage" | "done"
    text: str = ""
    tool_call: ToolCall | None = None
    input_tokens: int = 0
    output_tokens: int = 0


def _parse_openai_tool_calls(raw: object) -> list[ToolCall]:
    """Parse an OpenAI ``message.tool_calls`` array into :class:`ToolCall`s.

    Arguments arrive as a JSON *string*; a malformed one degrades to ``{}`` so a
    bad tool call never crashes the loop (the executor then reports missing args).
    """
    if not isinstance(raw, list):
        return []
    import json

    calls: list[ToolCall] = []
    for item in raw:
        function = (item or {}).get("function") or {}
        name = str(function.get("name", "")).strip()
        if not name:
            continue
        try:
            args = json.loads(function.get("arguments") or "{}")
        except (json.JSONDecodeError, TypeError):
            args = {}
        calls.append(
            ToolCall(
                id=str(item.get("id", "")),
                name=name,
                arguments=args if isinstance(args, dict) else {},
            )
        )
    return calls


def _optional_chat_kwargs(
    tools: list[ToolDef] | None, response_schema: dict | None
) -> dict:
    """Forward the v2 ``chat`` kwargs only when set.

    Adapters (and test fakes) written against the original
    ``chat(messages, *, temperature, max_tokens)`` signature keep working when no
    tools/schema are in play — the common path — while capable adapters still
    receive them when ``structured_call``/native tools request them.
    """
    extra: dict = {}
    if tools is not None:
        extra["tools"] = tools
    if response_schema is not None:
        extra["response_schema"] = response_schema
    return extra


class LLMError(RuntimeError):
    """Raised when an LLM provider call fails."""


def _require_header_safe_key(provider: LLMProvider, api_key: str) -> str:
    """Reject a stored key that cannot be an HTTP auth header value.

    API keys are ASCII bearer tokens. A stray non-ASCII character (a mis-paste,
    e.g. a Turkish 'ı') makes httpx raise a cryptic ``UnicodeEncodeError`` while
    encoding the ``Authorization`` / ``x-api-key`` header — which the agent layer
    otherwise surfaces to the user as an opaque "all subtasks failed". Fail early
    with an actionable message instead (never logging the key itself).
    """
    if not api_key.isascii():
        raise LLMError(
            f"The stored {provider.value} API key contains non-ASCII characters "
            "and cannot be used. Re-enter it under Settings > API Keys."
        )
    return api_key


# --- Base adapter ---------------------------------------------------------


class LLMAdapter(ABC):
    """Interface every provider adapter must implement."""

    provider: LLMProvider
    # Default: least-capable. Subclasses opt in to what their provider supports.
    capabilities: AdapterCapabilities = AdapterCapabilities()

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
        tools: list[ToolDef] | None = None,
        response_schema: dict | None = None,
    ) -> LLMResponse:
        """Run a chat completion and return the assistant message.

        ``tools`` enables native function calling (when
        ``capabilities.native_tools``); ``response_schema`` requests a
        provider-enforced JSON object (when ``capabilities.json_schema``).
        Adapters ignore what their provider does not support.
        """

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[ToolDef] | None = None,
        response_schema: dict | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a completion as :class:`StreamEvent`s.

        The default degrades a non-streaming provider gracefully: it runs
        ``chat`` and yields the whole reply as one ``text_delta`` then a
        ``done`` event, so call sites never branch on ``capabilities.streaming``.
        """
        extra = _optional_chat_kwargs(tools, response_schema)
        response = await self.chat(
            messages, temperature=temperature, max_tokens=max_tokens, **extra
        )
        if response.content:
            yield StreamEvent(kind="text_delta", text=response.content)
        for call in response.tool_calls:
            yield StreamEvent(kind="tool_call", tool_call=call)
        yield StreamEvent(
            kind="done",
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )


# --- OpenAI-compatible base (Ollama, OpenAI) ------------------------------


class _OpenAICompatAdapter(LLMAdapter):
    """Shared implementation for OpenAI-compatible ``/chat/completions`` APIs."""

    base_url: str
    default_model: str

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(api_key=api_key, model=model)
        # A per-instance base_url shadows the class attribute. Named providers
        # pass None and keep their class-level endpoint (so tests that read
        # ``get_adapter(GEMINI).base_url`` still pass); only the custom adapter
        # sets it from the user's stored key.
        if base_url:
            self.base_url = base_url

    @_retry_policy
    async def _post(self, path: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            key = _require_header_safe_key(self.provider, self.api_key)
            headers["Authorization"] = f"Bearer {key}"
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
        tools: list[ToolDef] | None = None,
        response_schema: dict | None = None,
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
        if tools and self.capabilities.native_tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        if response_schema is not None and self.capabilities.json_schema:
            # Provider-enforced structured output (OpenAI/Gemini json_schema).
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": response_schema,
                },
            }
        try:
            data = await self._post("/chat/completions", payload)
        except httpx.HTTPStatusError as exc:  # 4xx/5xx after retries
            status = exc.response.status_code
            body = exc.response.text[:_ERROR_BODY_MAX]
            # Real cause (e.g. 404 "model not found", 401 auth) — otherwise this
            # is swallowed and the operator sees nothing in the terminal.
            logger.warning(
                "%s chat failed: HTTP %s model=%s body=%s",
                self.provider.value,
                status,
                model,
                body,
            )
            raise LLMError(f"{self.provider.value} chat failed: HTTP {status}") from exc
        except httpx.HTTPError as exc:  # network/connection failure after retries
            # %r not %s: str(httpx.ReadTimeout()) is "", which logged a bare
            # "ollama chat failed:  model=..." with no cause. repr keeps the
            # exception class (e.g. ReadTimeout('')) so timeouts are diagnosable.
            logger.warning(
                "%s chat failed: %r model=%s", self.provider.value, exc, model
            )
            raise LLMError(f"{self.provider.value} chat failed") from exc
        try:
            choice = data["choices"][0]
            message = choice["message"]
            content = message.get("content") or ""
        except (KeyError, IndexError) as exc:
            raise LLMError("Malformed LLM response") from exc
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        total = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
        return LLMResponse(
            content=content,
            model=model,
            tokens_used=total,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            finish_reason=choice.get("finish_reason"),
            tool_calls=_parse_openai_tool_calls(message.get("tool_calls")),
            provider=self.provider,
            raw=data,
        )


class OllamaAdapter(_OpenAICompatAdapter):
    """Free/local tier via Ollama's OpenAI-compatible endpoint."""

    provider = LLMProvider.OLLAMA
    base_url = settings.free_model_endpoint
    default_model = settings.free_model_name
    # qwen-class local models only reliably do ``format: json``, not native
    # tools or provider-enforced schemas — structured_call uses the fallback.
    capabilities = AdapterCapabilities(
        streaming=False,
        native_tools=settings.ollama_native_tools,
        json_schema=False,
    )


class OpenAIAdapter(_OpenAICompatAdapter):
    """OpenAI provider (BYOK). Requires ``api_key``."""

    provider = LLMProvider.OPENAI
    base_url = "https://api.openai.com/v1"
    default_model = "gpt-4o-mini"
    capabilities = AdapterCapabilities(
        streaming=False, native_tools=False, json_schema=True
    )


class GeminiAdapter(_OpenAICompatAdapter):
    """Google Gemini via its OpenAI-compatible endpoint (BYOK, free tier)."""

    provider = LLMProvider.GEMINI
    base_url = GEMINI_API_BASE_URL
    default_model = settings.gemini_model_name
    capabilities = AdapterCapabilities(
        streaming=False, native_tools=False, json_schema=True
    )


class GroqAdapter(_OpenAICompatAdapter):
    """Groq (BYOK). OpenAI-compatible; fast Llama/Mixtral inference."""

    provider = LLMProvider.GROQ
    base_url = GROQ_API_BASE_URL
    default_model = "llama-3.3-70b-versatile"


class DeepSeekAdapter(_OpenAICompatAdapter):
    """DeepSeek (BYOK). OpenAI-compatible."""

    provider = LLMProvider.DEEPSEEK
    base_url = DEEPSEEK_API_BASE_URL
    default_model = "deepseek-chat"


class MistralAdapter(_OpenAICompatAdapter):
    """Mistral AI (BYOK). OpenAI-compatible."""

    provider = LLMProvider.MISTRAL
    base_url = MISTRAL_API_BASE_URL
    default_model = "mistral-small-latest"


class XAIAdapter(_OpenAICompatAdapter):
    """xAI Grok (BYOK). OpenAI-compatible."""

    provider = LLMProvider.XAI
    base_url = XAI_API_BASE_URL
    default_model = "grok-2-latest"


class OpenRouterAdapter(_OpenAICompatAdapter):
    """OpenRouter (BYOK). OpenAI-compatible gateway to many models."""

    provider = LLMProvider.OPENROUTER
    base_url = OPENROUTER_API_BASE_URL
    default_model = "openai/gpt-4o-mini"


class TogetherAdapter(_OpenAICompatAdapter):
    """Together AI (BYOK). OpenAI-compatible."""

    provider = LLMProvider.TOGETHER
    base_url = TOGETHER_API_BASE_URL
    default_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"


class PerplexityAdapter(_OpenAICompatAdapter):
    """Perplexity (BYOK). OpenAI-compatible; Sonar online models."""

    provider = LLMProvider.PERPLEXITY
    base_url = PERPLEXITY_API_BASE_URL
    default_model = "sonar"


class CustomOpenAICompatAdapter(_OpenAICompatAdapter):
    """User-supplied OpenAI-compatible endpoint (self-hosted, gateway, etc.).

    ``base_url`` and ``model`` come from the stored API key, not a class
    attribute — the placeholder ``default_model`` is never used because a model
    is required when connecting a custom endpoint.
    """

    provider = LLMProvider.CUSTOM
    base_url = ""  # overridden per instance from the stored key
    default_model = ""  # unused: model is required for custom endpoints

    async def _post(self, path: str, payload: dict) -> dict:
        """Guard the user-controlled base_url before every request (SSRF).

        Re-checking here (not only at key creation) closes the DNS-rebinding
        window and covers keys stored before the guard existed. Runs once per
        call, ahead of the base adapter's retry loop.
        """
        if settings.llm_ssrf_guard_enabled:
            reason = await check_public_url(self.base_url)
            if reason is not None:
                raise LLMError(f"custom endpoint rejected: {reason}")
        return await super()._post(path, payload)


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
            "x-api-key": _require_header_safe_key(self.provider, self.api_key),
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
        tools: list[ToolDef] | None = None,
        response_schema: dict | None = None,
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
        except httpx.HTTPStatusError as exc:  # 4xx/5xx after retries
            status = exc.response.status_code
            body = exc.response.text[:_ERROR_BODY_MAX]
            # Real cause (e.g. 404 model, 401 auth) — otherwise this is swallowed
            # and the operator sees nothing in the terminal.
            logger.warning(
                "anthropic chat failed: HTTP %s model=%s body=%s", status, model, body
            )
            raise LLMError(f"anthropic chat failed: HTTP {status}") from exc
        except httpx.HTTPError as exc:  # network/connection failure after retries
            # %r not %s so a timeout's empty str() doesn't log a blank cause.
            logger.warning("anthropic chat failed: %r model=%s", exc, model)
            raise LLMError("anthropic chat failed") from exc
        try:
            blocks = data["content"]
            content = "".join(
                b.get("text", "") for b in blocks if b.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            raise LLMError("Malformed Anthropic response") from exc
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        return LLMResponse(
            content=content,
            model=model,
            tokens_used=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=data.get("stop_reason"),
            provider=self.provider,
            raw=data,
        )


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
        # Structured/streaming call sites branch on capabilities: expose the
        # primary's so a Gemini task keeps its provider-enforced JSON path.
        self.capabilities = primary.capabilities
        self.primary = primary
        self.fallback = fallback
        self.on_fallback = on_fallback

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[ToolDef] | None = None,
        response_schema: dict | None = None,
    ) -> LLMResponse:
        extra = _optional_chat_kwargs(tools, response_schema)
        try:
            return await self.primary.chat(
                messages, temperature=temperature, max_tokens=max_tokens, **extra
            )
        except LLMError as primary_exc:
            logger.warning(
                "primary %s failed (%s); trying fallback %s",
                self.primary.provider.value,
                primary_exc,
                self.fallback.provider.value,
            )
            if self.on_fallback is not None:
                await self.on_fallback(str(primary_exc))
            try:
                return await self.fallback.chat(
                    messages, temperature=temperature, max_tokens=max_tokens, **extra
                )
            except LLMError as fallback_exc:
                # Both brains are down: surface *both* reasons so the task error
                # (and the UI) says why, instead of a bare fallback message.
                logger.error(
                    "both providers failed: %s -> %s ; %s -> %s",
                    self.primary.provider.value,
                    primary_exc,
                    self.fallback.provider.value,
                    fallback_exc,
                )
                raise LLMError(
                    f"{self.primary.provider.value} failed ({primary_exc}); "
                    f"fallback {self.fallback.provider.value} failed ({fallback_exc})"
                ) from fallback_exc


class _TokenCounter:
    """Shared running token tally (§4.1). One instance backs every metered
    adapter in an :class:`AdapterPool`, so per-role adapters using different
    models still sum into a single, honest total."""

    __slots__ = ("total", "totals")

    def __init__(self) -> None:
        self.total = 0
        self.totals: dict[LLMProvider, int] = {}


class TokenMeter(LLMAdapter):
    """Counts tokens across every call made through the adapter it wraps.

    Wrapping the adapter once, at the top of a task, is what makes billing
    honest: orchestrator routing, main-agent planning and synthesis, reviewer
    passes and subagent work all flow through the same counter, whereas summing
    per-subagent metadata silently misses the rest. Pass a shared ``counter`` so
    several per-role meters (an :class:`AdapterPool`) share one total.
    """

    def __init__(
        self, inner: LLMAdapter, *, counter: _TokenCounter | None = None
    ) -> None:
        super().__init__(api_key=None, model=inner.model)
        self.provider = inner.provider
        self.capabilities = inner.capabilities
        self.inner = inner
        self._counter = counter or _TokenCounter()

    @property
    def total_tokens(self) -> int:
        return self._counter.total

    @total_tokens.setter
    def total_tokens(self, value: int) -> None:
        # Seeding on resume (engine) sets the running total directly.
        self._counter.total = value

    @property
    def totals(self) -> dict[LLMProvider, int]:
        # Per-provider tally: which brain actually served each call (the
        # ``billable`` split reads this).
        return self._counter.totals

    def _record(self, response: LLMResponse) -> int:
        """Count a response's tokens, estimating when the provider omits usage."""
        tokens = response.tokens_used
        if tokens <= 0 and response.content:
            # Provider reported no usage — estimate so the task is not free.
            tokens = ceil(len(response.content) / TOKEN_ESTIMATE_CHARS_PER_TOKEN)
        self._counter.total += tokens
        served = response.provider or self.provider
        self._counter.totals[served] = self._counter.totals.get(served, 0) + tokens
        return tokens

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[ToolDef] | None = None,
        response_schema: dict | None = None,
    ) -> LLMResponse:
        extra = _optional_chat_kwargs(tools, response_schema)
        response = await self.inner.chat(
            messages, temperature=temperature, max_tokens=max_tokens, **extra
        )
        self._record(response)
        return response


class TracedAdapter(LLMAdapter):
    """Records one ``llm.chat`` trace span per call (Backend v2 §4.5).

    Placed *under* :class:`TokenMeter` in the chain (``TokenMeter(TracedAdapter(
    inner))``) so token counts and per-call cost land on the llm span. A no-op
    when tracing is disabled — ``tracer.span`` yields a null span and nothing is
    buffered. Prompt/response bodies are never stored: the span carries token
    counts, cost, and a short request-side preview only.
    """

    def __init__(self, inner: LLMAdapter) -> None:
        super().__init__(api_key=None, model=inner.model)
        self.provider = inner.provider
        self.capabilities = inner.capabilities
        self.inner = inner

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[ToolDef] | None = None,
        response_schema: dict | None = None,
    ) -> LLMResponse:
        # Imported lazily so the LLM layer carries no hard dependency on the
        # observability layer (and to keep import order simple).
        from app.core.constants import SPAN_PREVIEW_CHARS, SpanKind
        from app.utils import tracing

        extra = _optional_chat_kwargs(tools, response_schema)
        preview = next((m.content for m in reversed(messages) if m.role == "user"), "")[
            :SPAN_PREVIEW_CHARS
        ]
        async with tracing.tracer.span(
            "llm.chat",
            SpanKind.LLM,
            **{
                "gen_ai.operation.name": "chat",
                "gen_ai.system": self.provider.value,
                "gen_ai.request.model": self.model,
                "maestro.request.preview": preview,
            },
        ) as span:
            response = await self.inner.chat(
                messages, temperature=temperature, max_tokens=max_tokens, **extra
            )
            served = (response.provider or self.provider).value
            estimated = response.tokens_used <= 0
            span.set_attribute("gen_ai.system", served)
            span.set_attribute("gen_ai.response.model", response.model)
            span.set_attribute("gen_ai.usage.input_tokens", response.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", response.output_tokens)
            span.set_attribute("gen_ai.response.finish_reason", response.finish_reason)
            span.set_attribute("maestro.tokens.estimated", estimated)
            span.cost_usd = tracing.cost_usd(
                response.model, served, response.input_tokens, response.output_tokens
            )
            return response


# --- Factory --------------------------------------------------------------

_ADAPTERS: dict[LLMProvider, type[LLMAdapter]] = {
    LLMProvider.OLLAMA: OllamaAdapter,
    LLMProvider.OPENAI: OpenAIAdapter,
    LLMProvider.ANTHROPIC: AnthropicAdapter,
    LLMProvider.GEMINI: GeminiAdapter,
    LLMProvider.GROQ: GroqAdapter,
    LLMProvider.DEEPSEEK: DeepSeekAdapter,
    LLMProvider.MISTRAL: MistralAdapter,
    LLMProvider.XAI: XAIAdapter,
    LLMProvider.OPENROUTER: OpenRouterAdapter,
    LLMProvider.TOGETHER: TogetherAdapter,
    LLMProvider.PERPLEXITY: PerplexityAdapter,
    LLMProvider.CUSTOM: CustomOpenAICompatAdapter,
}

# Every chat provider must have an adapter, else a task selecting it passes the
# LLM_CHAT_PROVIDERS gate but fails at runtime in get_adapter. Turn that latent
# drift into an import-time error (CLAUDE.md §Tur 5 known-limit note).
assert LLM_CHAT_PROVIDERS <= set(_ADAPTERS), (
    f"chat providers without adapters: {LLM_CHAT_PROVIDERS - set(_ADAPTERS)}"
)


def get_adapter(
    provider: LLMProvider,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> LLMAdapter:
    """Return an adapter instance for the given provider.

    ``base_url`` is only meaningful for the custom OpenAI-compatible provider;
    named providers ignore it and keep their built-in endpoint.
    """
    try:
        adapter_cls = _ADAPTERS[provider]
    except KeyError as exc:
        raise LLMError(f"Unsupported LLM provider: {provider}") from exc
    if provider is LLMProvider.CUSTOM:
        return adapter_cls(api_key=api_key, model=model, base_url=base_url)
    return adapter_cls(api_key=api_key, model=model)


class AdapterPool:
    """Per-role metered/traced adapters that share one token counter (§4.4).

    Resolves a model per role (task override > user preference > provider tier
    default) and caches one adapter per model, all feeding a single
    :class:`_TokenCounter`. A task can therefore run its subagents on a cheap
    model and its synthesis on a strong one while still being billed as one
    honest total. A custom endpoint's fixed model overrides role resolution.
    """

    def __init__(
        self,
        *,
        provider: LLMProvider,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        overrides: dict | None = None,
        preferences: dict | None = None,
        on_fallback: Callable[[str], Awaitable[None]] | None = None,
        traced: bool = False,
    ) -> None:
        self.provider = provider
        self._api_key = api_key
        self._base_url = base_url
        self._model_override = model
        self._overrides = overrides
        self._preferences = preferences
        self._on_fallback = on_fallback
        self._traced = traced
        self._counter = _TokenCounter()
        self._cache: dict[str | None, TokenMeter] = {}

    @property
    def total_tokens(self) -> int:
        return self._counter.total

    @total_tokens.setter
    def total_tokens(self, value: int) -> None:
        self._counter.total = value

    @property
    def totals(self) -> dict[LLMProvider, int]:
        return self._counter.totals

    def _build(self, model: str | None) -> TokenMeter:
        adapter: LLMAdapter = get_adapter(
            self.provider,
            api_key=self._api_key,
            base_url=self._base_url,
            model=model,
        )
        if self.provider is LLMProvider.GEMINI:
            adapter = FallbackLLMAdapter(
                primary=adapter,
                fallback=get_adapter(LLMProvider.OLLAMA),
                on_fallback=self._on_fallback,
            )
        if self._traced:
            adapter = TracedAdapter(adapter)
        return TokenMeter(adapter, counter=self._counter)

    def for_model(self, model: str | None) -> TokenMeter:
        if model not in self._cache:
            self._cache[model] = self._build(model)
        return self._cache[model]

    def for_role(self, role: str) -> TokenMeter:
        """The metered adapter for a role, at that role's resolved model."""
        model = self._model_override or resolve_model(
            role,
            provider=self.provider,
            overrides=self._overrides,
            preferences=self._preferences,
        )
        return self.for_model(model)


def resolve_model(
    role: str,
    *,
    provider: LLMProvider,
    overrides: dict | None = None,
    preferences: dict | None = None,
) -> str | None:
    """Pick a model for a role: task override > user preference > provider tier
    default. ``None`` means "let the adapter use its default model" (Backend v2
    §4.4). Roles are the ``AgentRole`` values (e.g. ``"main"``, ``"subagent"``)."""
    if overrides and overrides.get(role):
        return overrides[role]
    if preferences and preferences.get(role):
        return preferences[role]
    tier = MODEL_TIER_DEFAULTS.get(role)
    tier_models = PROVIDER_TIER_MODELS.get(provider.value)
    if tier and tier_models:
        return tier_models.get(tier)
    return None


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
