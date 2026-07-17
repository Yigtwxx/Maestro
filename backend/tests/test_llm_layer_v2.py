"""LLM layer v2: token estimation, per-provider tallies, structured output.

Pins the Backend v2 §4.4 behaviours: usage is estimated when a provider omits it
(D10), the meter attributes tokens to the provider that served each call, and
``structured_call`` retries with validation feedback / uses provider-enforced
schema when the adapter supports it (D6).
"""

from __future__ import annotations

from math import ceil
from typing import Any

from pydantic import BaseModel

from app.agents.structured import structured_call
from app.core.constants import (
    PROVIDER_TIER_MODELS,
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
    LLMProvider,
)
from app.services.llm_service import (
    AdapterCapabilities,
    ChatMessage,
    LLMAdapter,
    LLMResponse,
    TokenMeter,
    resolve_model,
)


class _ScriptedAdapter(LLMAdapter):
    """Returns queued responses; records call count and the last v2 kwargs."""

    provider = LLMProvider.OLLAMA

    def __init__(self, responses: list[LLMResponse]) -> None:
        super().__init__(model="fake")
        self._responses = responses
        self.calls = 0
        self.last_kwargs: dict[str, Any] = {}

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: Any = None,
        response_schema: Any = None,
    ) -> LLMResponse:
        self.last_kwargs = {"tools": tools, "response_schema": response_schema}
        response = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return response


async def test_token_meter_estimates_when_provider_omits_usage() -> None:
    content = "hello world, this is the reply"  # 30 chars
    meter = TokenMeter(
        _ScriptedAdapter(
            [
                LLMResponse(
                    content=content,
                    model="m",
                    tokens_used=0,
                    provider=LLMProvider.OLLAMA,
                )
            ]
        )
    )

    await meter.chat([ChatMessage("user", "hi")])

    expected = ceil(len(content) / TOKEN_ESTIMATE_CHARS_PER_TOKEN)
    assert meter.total_tokens == expected, meter.total_tokens
    assert meter.totals[LLMProvider.OLLAMA] == expected, meter.totals


async def test_token_meter_attributes_tokens_to_the_serving_provider() -> None:
    meter = TokenMeter(
        _ScriptedAdapter(
            [
                LLMResponse(
                    content="x", model="m", tokens_used=42, provider=LLMProvider.OPENAI
                )
            ]
        )
    )

    await meter.chat([ChatMessage("user", "hi")])

    assert meter.total_tokens == 42, meter.total_tokens
    assert meter.totals == {LLMProvider.OPENAI: 42}, meter.totals


class _Decision(BaseModel):
    domain: str


async def test_structured_call_retries_with_feedback_then_validates() -> None:
    adapter = _ScriptedAdapter(
        [
            LLMResponse(content="sorry, no json here", model="m", tokens_used=1),
            LLMResponse(content='{"domain": "finance"}', model="m", tokens_used=1),
        ]
    )

    decision = await structured_call(
        adapter, [ChatMessage("user", "route this")], _Decision, max_attempts=2
    )

    assert decision.domain == "finance", decision
    assert adapter.calls == 2, "an invalid first reply must trigger one retry"


async def test_structured_call_sends_schema_when_provider_supports_it() -> None:
    adapter = _ScriptedAdapter(
        [LLMResponse(content='{"domain": "finance"}', model="m", tokens_used=1)]
    )
    adapter.capabilities = AdapterCapabilities(json_schema=True)

    decision = await structured_call(
        adapter, [ChatMessage("user", "route this")], _Decision
    )

    assert decision.domain == "finance", decision
    assert adapter.last_kwargs["response_schema"] is not None, (
        "a json_schema-capable adapter must receive the response schema"
    )


def test_resolve_model_override_beats_preference_and_default() -> None:
    model = resolve_model(
        "main",
        provider=LLMProvider.OPENAI,
        overrides={"main": "gpt-4o-pinned"},
        preferences={"main": "gpt-4o-mini"},
    )
    assert model == "gpt-4o-pinned", model


def test_resolve_model_uses_preference_when_no_override() -> None:
    model = resolve_model(
        "subagent", provider=LLMProvider.OPENAI, preferences={"subagent": "my-cheap"}
    )
    assert model == "my-cheap", model


def test_resolve_model_falls_back_to_provider_tier_default() -> None:
    # subagent -> cheap tier for the provider.
    model = resolve_model("subagent", provider=LLMProvider.OPENAI)
    assert model == PROVIDER_TIER_MODELS["openai"]["cheap"], model


def test_resolve_model_is_none_for_an_untiered_provider() -> None:
    # Ollama has a single local model -> None means "use the adapter default".
    assert resolve_model("main", provider=LLMProvider.OLLAMA) is None
