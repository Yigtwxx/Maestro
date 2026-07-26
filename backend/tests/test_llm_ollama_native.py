"""The Ollama adapter drives Ollama's native ``/api/chat`` (no network).

Why this endpoint at all: the OpenAI-compatible shim cannot express three
controls this model tier needs, and all three were measured on qwen3.5:9b before
the adapter was changed.

* ``think`` — a thinking model's reasoning is reported in a field Maestro never
  reads, but it is still charged against ``max_tokens``. 25-33% of replies came
  back with empty content and ``finish_reason=length``, at ~60s each. Raising
  ``max_tokens`` did not help (the model reasoned longer); turning thinking off
  gave 6/6 non-empty at 3.6s.
* ``format`` — a compiled JSON-schema grammar instead of parsing JSON back out
  of prose. Every agent schema validated 5/5, ``PlanResult`` and its ``$defs``
  included.
* ``num_ctx`` — Ollama loads a model at 4096 tokens and truncates a longer
  prompt from the front, taking the system prompt first.

These tests pin the request shape, the response mapping, and the 404 fallback
that keeps a non-Ollama OpenAI-compatible server working.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services import llm_service
from app.services.llm_service import ChatMessage, LLMError, OllamaAdapter

NATIVE_REPLY = {
    "model": "qwen3.5:9b",
    "message": {"role": "assistant", "content": "hello"},
    "done_reason": "stop",
    "prompt_eval_count": 11,
    "eval_count": 5,
}


class _Capture:
    """Stands in for the shared httpx client and records what was posted."""

    def __init__(self, reply: dict[str, Any], status: int = 200) -> None:
        self._reply = reply
        self._status = status
        self.urls: list[str] = []
        self.payloads: list[dict[str, Any]] = []

    async def post(
        self, url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None
    ) -> httpx.Response:
        self.urls.append(url)
        self.payloads.append(json)
        request = httpx.Request("POST", url)
        return httpx.Response(self._status, json=self._reply, request=request)


@pytest.fixture(autouse=True)
def _reset_native_flag():
    """The 404 fallback latches on the class; keep it from leaking across tests."""
    OllamaAdapter._native_available = True
    yield
    OllamaAdapter._native_available = True


def _install(monkeypatch, capture: _Capture) -> None:
    monkeypatch.setattr(llm_service, "_http_client", lambda: capture)


async def test_chat_posts_to_native_endpoint_with_thinking_and_context_controls(
    monkeypatch,
):
    capture = _Capture(NATIVE_REPLY)
    _install(monkeypatch, capture)

    await OllamaAdapter().chat([ChatMessage("user", "hi")], max_tokens=256)

    assert capture.urls == ["http://localhost:11434/api/chat"], capture.urls
    payload = capture.payloads[0]
    # think must be sent explicitly: omitting it lets the model default to on,
    # which is the empty-reply failure this endpoint switch exists to remove.
    assert payload["think"] is settings.ollama_think, payload
    assert payload["stream"] is False, payload
    options = payload["options"]
    assert options["num_ctx"] == settings.ollama_num_ctx, options
    # max_tokens is num_predict here; sending it as max_tokens would be ignored
    # and the model would run to the context limit.
    assert options["num_predict"] == 256, options


async def test_native_base_url_strips_the_openai_v1_suffix(monkeypatch):
    capture = _Capture(NATIVE_REPLY)
    _install(monkeypatch, capture)

    adapter = OllamaAdapter()
    adapter.base_url = "http://ollama.internal:11434/v1/"
    await adapter.chat([ChatMessage("user", "hi")])

    assert capture.urls == ["http://ollama.internal:11434/api/chat"], capture.urls


async def test_response_schema_is_sent_as_native_format(monkeypatch):
    capture = _Capture(NATIVE_REPLY)
    _install(monkeypatch, capture)
    schema = {"type": "object", "properties": {"domain": {"type": "string"}}}

    await OllamaAdapter().chat([ChatMessage("user", "hi")], response_schema=schema)

    assert capture.payloads[0]["format"] == schema, capture.payloads[0]


async def test_usage_is_read_from_native_counter_fields(monkeypatch):
    capture = _Capture(NATIVE_REPLY)
    _install(monkeypatch, capture)

    response = await OllamaAdapter().chat([ChatMessage("user", "hi")])

    # Native uses prompt_eval_count/eval_count, not an OpenAI "usage" object; if
    # these are misread every task reports zero tokens and the quota ledger and
    # the budget guard both go blind.
    assert response.input_tokens == 11, response
    assert response.output_tokens == 5, response
    assert response.tokens_used == 16, response
    assert response.content == "hello", response
    assert response.finish_reason == "stop", response


async def test_native_tool_call_arguments_survive_as_an_object(monkeypatch):
    reply = {
        **NATIVE_REPLY,
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "web_search", "arguments": {"query": "btc"}}}
            ],
        },
    }
    capture = _Capture(reply)
    _install(monkeypatch, capture)

    response = await OllamaAdapter().chat([ChatMessage("user", "hi")])

    # Ollama sends arguments already decoded; the OpenAI parser json.loads() a
    # dict, gets {}, and every tool call silently loses its arguments.
    assert len(response.tool_calls) == 1, response.tool_calls
    assert response.tool_calls[0].arguments == {"query": "btc"}, response.tool_calls


async def test_missing_native_endpoint_falls_back_to_the_openai_shim(monkeypatch):
    """A 404 means this host is not Ollama; the shim must take over silently."""
    calls: list[dict[str, Any]] = []

    async def fake_super_chat(self, messages, **kwargs):  # noqa: ANN001, ANN202
        calls.append(kwargs)
        return llm_service.LLMResponse(content="from shim", model="m", tokens_used=1)

    _install(monkeypatch, _Capture({"error": "not found"}, status=404))
    monkeypatch.setattr(llm_service._OpenAICompatAdapter, "chat", fake_super_chat)

    adapter = OllamaAdapter()
    first = await adapter.chat([ChatMessage("user", "hi")], max_tokens=64)

    assert first.content == "from shim", first
    assert OllamaAdapter._native_available is False, (
        "the 404 must latch so later calls skip the dead endpoint"
    )
    # And the choice must stick, otherwise every call pays a doomed round trip.
    await adapter.chat([ChatMessage("user", "again")])
    assert len(calls) == 2, calls


async def test_non_404_native_error_raises_llm_error(monkeypatch):
    """A 500 is a real provider failure, not a wrong-endpoint signal."""
    _install(monkeypatch, _Capture({"error": "boom"}, status=500))

    with pytest.raises(LLMError):
        await OllamaAdapter().chat([ChatMessage("user", "hi")])

    assert OllamaAdapter._native_available is True, (
        "a transient 500 must not permanently disable the native endpoint"
    )


async def test_native_api_disabled_uses_the_openai_shim(monkeypatch):
    """The config switch is the operator's one-line rollback."""
    called: list[str] = []

    async def fake_super_chat(self, messages, **kwargs):  # noqa: ANN001, ANN202
        called.append("shim")
        return llm_service.LLMResponse(content="shim", model="m", tokens_used=1)

    monkeypatch.setattr(settings, "ollama_native_api", False)
    monkeypatch.setattr(llm_service._OpenAICompatAdapter, "chat", fake_super_chat)
    _install(monkeypatch, _Capture(NATIVE_REPLY))

    await OllamaAdapter().chat([ChatMessage("user", "hi")])

    assert called == ["shim"], called


async def test_malformed_native_reply_raises_llm_error(monkeypatch):
    _install(monkeypatch, _Capture({"done_reason": "stop"}))

    with pytest.raises(LLMError):
        await OllamaAdapter().chat([ChatMessage("user", "hi")])


class _Sequence:
    """Serves a scripted list of replies and records each payload."""

    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self._replies = list(replies)
        self.payloads: list[dict[str, Any]] = []

    async def post(
        self, url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None
    ) -> httpx.Response:
        self.payloads.append(json)
        reply = self._replies.pop(0) if self._replies else NATIVE_REPLY
        return httpx.Response(200, json=reply, request=httpx.Request("POST", url))


EMPTY_REPLY = {
    "model": "qwen3.5:9b",
    "message": {"role": "assistant", "content": ""},
    "done_reason": "length",
    "prompt_eval_count": 9,
    "eval_count": 1536,
}


async def test_schema_calls_never_think_even_when_thinking_is_enabled(monkeypatch):
    """A grammar already fixes the output shape, so reasoning only risks it.

    Reasoning is charged against max_tokens but returned in a field Maestro does
    not read, so a schema call that reasons too long yields no JSON at all. That
    is the failure this split exists to remove, so it must not depend on the
    operator leaving ollama_think off.
    """
    capture = _Capture(NATIVE_REPLY)
    _install(monkeypatch, capture)
    monkeypatch.setattr(settings, "ollama_think", True)

    await OllamaAdapter().chat(
        [ChatMessage("user", "hi")], response_schema={"type": "object"}
    )

    assert capture.payloads[0]["think"] is False, capture.payloads[0]


async def test_free_form_calls_honour_the_thinking_setting(monkeypatch):
    """Deliverables are the only place reasoning can pay for itself."""
    capture = _Capture(NATIVE_REPLY)
    _install(monkeypatch, capture)
    monkeypatch.setattr(settings, "ollama_think", True)

    await OllamaAdapter().chat([ChatMessage("user", "hi")])

    assert capture.payloads[0]["think"] is True, capture.payloads[0]


async def test_empty_thinking_reply_is_retried_once_without_thinking(monkeypatch):
    """Recover the turn instead of handing the caller a blank.

    A blank subagent reply is reported as EMPTY_SUBAGENT_ANSWER and costs the
    member its subtask, so spending one cheap extra call is worth it.
    """
    sequence = _Sequence([EMPTY_REPLY, NATIVE_REPLY])
    _install(monkeypatch, sequence)
    monkeypatch.setattr(settings, "ollama_think", True)

    response = await OllamaAdapter().chat([ChatMessage("user", "hi")])

    assert len(sequence.payloads) == 2, sequence.payloads
    assert sequence.payloads[0]["think"] is True, sequence.payloads[0]
    assert sequence.payloads[1]["think"] is False, sequence.payloads[1]
    assert response.content == "hello", response


async def test_empty_reply_without_thinking_is_not_retried(monkeypatch):
    """Nothing to change on a second try, so the call must not be doubled."""
    sequence = _Sequence([EMPTY_REPLY, NATIVE_REPLY])
    _install(monkeypatch, sequence)
    monkeypatch.setattr(settings, "ollama_think", False)

    response = await OllamaAdapter().chat([ChatMessage("user", "hi")])

    assert len(sequence.payloads) == 1, sequence.payloads
    assert response.content == "", response


async def test_thinking_reply_with_only_a_tool_call_is_not_retried(monkeypatch):
    """Empty content plus a tool call is a normal turn, not a lost one."""
    tool_reply = {
        **EMPTY_REPLY,
        "done_reason": "stop",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "web_search", "arguments": {}}}],
        },
    }
    sequence = _Sequence([tool_reply, NATIVE_REPLY])
    _install(monkeypatch, sequence)
    monkeypatch.setattr(settings, "ollama_think", True)

    response = await OllamaAdapter().chat([ChatMessage("user", "hi")])

    assert len(sequence.payloads) == 1, sequence.payloads
    assert len(response.tool_calls) == 1, response.tool_calls
