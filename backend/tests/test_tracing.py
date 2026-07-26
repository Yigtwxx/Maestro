"""Execution tracing (Backend v2 §4.5): spans, cost, and the read side.

Covers the guarantees the trace layer must hold: nesting via contextvars, a
no-op when disabled, gen_ai-shaped llm spans with per-call cost recorded under
the TokenMeter, and owner-scoped trace reads.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.core.config import settings
from app.core.constants import LLMProvider, SpanKind
from app.services import trace_service
from app.services.llm_service import (
    ChatMessage,
    LLMAdapter,
    LLMResponse,
    TokenMeter,
    TracedAdapter,
)
from app.utils import tracing


class _FakeSpans:
    """In-memory stand-in for the Mongo ``trace_spans`` collection."""

    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs: list[dict[str, Any]] = list(docs or [])

    async def insert_many(self, batch: list[dict], ordered: bool = True) -> None:
        self.docs.extend(batch)

    def find(self, query: dict, projection: dict | None = None) -> _FakeCursor:
        scalar = {k: v for k, v in query.items() if not isinstance(v, dict)}
        matched = [
            {k: v for k, v in doc.items() if k != "_id"}
            for doc in self.docs
            if all(doc.get(k) == v for k, v in scalar.items())
        ]
        return _FakeCursor(matched)


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, *args: Any, **kwargs: Any) -> _FakeCursor:
        return self

    def limit(self, n: int) -> _FakeCursor:
        self._docs = self._docs[:n]
        return self

    async def __aiter__(self):  # noqa: ANN204
        for doc in self._docs:
            yield doc


class _StubAdapter(LLMAdapter):
    """Returns a fixed response with real usage numbers."""

    provider = LLMProvider.OPENAI

    def __init__(self, response: LLMResponse) -> None:
        super().__init__()
        self.model = response.model
        self._response = response

    async def chat(self, messages, *, temperature=0.2, max_tokens=None, **_):  # noqa: ANN001
        return self._response


@pytest.fixture
def tracing_on(monkeypatch):
    """Enable tracing against a fresh tracer + fake collection; return the fake."""
    monkeypatch.setattr(settings, "tracing_enabled", True)
    fake = _FakeSpans()
    monkeypatch.setattr(tracing, "tracer", tracing.Tracer())
    monkeypatch.setattr(tracing, "_spans_collection", lambda: fake)
    return fake


# --- cost ------------------------------------------------------------------


def test_cost_usd_prefers_model_pricing() -> None:
    # gpt-4o-mini: (0.00015 in, 0.0006 out) per 1k.
    cost = tracing.cost_usd("gpt-4o-mini", "openai", 1000, 1000)
    assert cost == pytest.approx(0.00075), cost


def test_cost_usd_falls_back_to_blended_provider_rate() -> None:
    # Unknown model -> blended anthropic rate 0.006 per 1k over all tokens.
    cost = tracing.cost_usd("mystery-model", "anthropic", 1000, 0)
    assert cost == pytest.approx(0.006), cost


def test_cost_usd_unknown_provider_is_free() -> None:
    assert tracing.cost_usd("x", "custom", 5000, 5000) == 0.0


# --- tracer ----------------------------------------------------------------


async def test_span_is_noop_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "tracing_enabled", False)
    monkeypatch.setattr(tracing, "tracer", tracing.Tracer())
    called = False

    def _boom():  # noqa: ANN202
        nonlocal called
        called = True
        raise AssertionError("Mongo must not be touched when tracing is off")

    monkeypatch.setattr(tracing, "_spans_collection", _boom)
    async with tracing.tracer.span("task", SpanKind.TASK, trace_id="t1") as span:
        span.set_attribute("k", "v")  # safe no-op
    await tracing.force_flush()
    assert called is False, "disabled tracing buffered/flushed a span"


async def test_spans_nest_and_flush(tracing_on) -> None:
    async with tracing.tracer.span(
        "task", SpanKind.TASK, trace_id="task-1", user_id="u1"
    ):
        async with tracing.tracer.span("step:route", SpanKind.STEP) as child:
            child.set_attribute("maestro.domain", "software")

    await tracing.force_flush()
    assert len(tracing_on.docs) == 2, tracing_on.docs
    by_name = {d["name"]: d for d in tracing_on.docs}
    assert by_name["step:route"]["parent_span_id"] == by_name["task"]["span_id"]
    # trace_id and user_id are inherited from the parent.
    assert by_name["step:route"]["trace_id"] == "task-1"
    assert by_name["step:route"]["user_id"] == "u1"


async def test_span_override_records_while_server_setting_is_off(
    monkeypatch,
) -> None:
    """A task that opted in traces even though TRACING_ENABLED is false."""
    monkeypatch.setattr(settings, "tracing_enabled", False)
    fake = _FakeSpans()
    monkeypatch.setattr(tracing, "tracer", tracing.Tracer())
    monkeypatch.setattr(tracing, "_spans_collection", lambda: fake)

    tracing.tracer.set_enabled(True)
    async with tracing.tracer.span("task", SpanKind.TASK, trace_id="t-on"):
        pass
    await tracing.force_flush()
    assert len(fake.docs) == 1, f"Expected 1 span, got {fake.docs}"


async def test_span_override_suppresses_while_server_setting_is_on(
    tracing_on,
) -> None:
    """A task that opted out records nothing, server-wide setting notwithstanding."""
    tracing.tracer.set_enabled(False)
    async with tracing.tracer.span("task", SpanKind.TASK, trace_id="t-off"):
        pass
    await tracing.force_flush()
    assert tracing_on.docs == [], f"Expected no spans, got {tracing_on.docs}"


async def test_span_records_error_status(tracing_on) -> None:
    with pytest.raises(RuntimeError):
        async with tracing.tracer.span("task", SpanKind.TASK, trace_id="t"):
            raise RuntimeError("boom")
    await tracing.force_flush()
    assert tracing_on.docs[0]["status"] == "error"
    assert "boom" in (tracing_on.docs[0]["error_message"] or "")


# --- TracedAdapter ---------------------------------------------------------


async def test_traced_adapter_records_llm_span_under_meter(tracing_on) -> None:
    response = LLMResponse(
        content="hello",
        model="gpt-4o-mini",
        tokens_used=30,
        input_tokens=20,
        output_tokens=10,
        provider=LLMProvider.OPENAI,
    )
    meter = TokenMeter(TracedAdapter(_StubAdapter(response)))
    out = await meter.chat([ChatMessage("user", "hi there")])

    assert out.content == "hello"
    assert meter.total_tokens == 30, "TokenMeter must still count above TracedAdapter"

    await tracing.force_flush()
    assert len(tracing_on.docs) == 1, tracing_on.docs
    span = tracing_on.docs[0]
    assert span["name"] == "llm.chat" and span["kind"] == SpanKind.LLM.value
    attrs = span["attributes"]
    assert attrs["gen_ai.system"] == "openai"
    assert attrs["gen_ai.response.model"] == "gpt-4o-mini"
    assert attrs["gen_ai.usage.input_tokens"] == 20
    assert attrs["gen_ai.usage.output_tokens"] == 10
    assert attrs["maestro.tokens.estimated"] is False
    # cost = 20/1k*0.00015 + 10/1k*0.0006 = 0.000009
    assert span["cost_usd"] == pytest.approx(0.000009), span["cost_usd"]
    # No prompt/response body is ever stored; only a short request preview.
    assert attrs["maestro.request.preview"] == "hi there"
    assert "hello" not in str(span)


async def test_traced_adapter_marks_estimated_when_usage_missing(tracing_on) -> None:
    response = LLMResponse(content="body", model="qwen3", tokens_used=0)
    await TracedAdapter(_StubAdapter(response)).chat([ChatMessage("user", "q")])
    await tracing.force_flush()
    assert tracing_on.docs[0]["attributes"]["maestro.tokens.estimated"] is True


# --- read side -------------------------------------------------------------


async def test_get_trace_returns_none_for_foreign_task(monkeypatch) -> None:
    async def _no_task(task_id, user_id):  # noqa: ANN001
        return None

    monkeypatch.setattr(trace_service.task_service, "get_task", _no_task)
    result = await trace_service.get_trace("t1", uuid.uuid4())
    assert result is None, "a non-owned task must not expose a trace"


async def test_get_trace_summary_rolls_up_tokens_and_cost(monkeypatch) -> None:
    user_id = uuid.uuid4()

    async def _owned(task_id, uid):  # noqa: ANN001
        return {"task_id": task_id}

    fake = _FakeSpans(
        [
            {
                "trace_id": "t1",
                "user_id": str(user_id),
                "name": "llm.chat",
                "kind": "llm",
                "duration_ms": 100,
                "cost_usd": 0.002,
                "attributes": {
                    "gen_ai.usage.input_tokens": 100,
                    "gen_ai.usage.output_tokens": 50,
                },
            },
            {
                "trace_id": "t1",
                "user_id": str(user_id),
                "name": "llm.chat",
                "kind": "llm",
                "duration_ms": 40,
                "cost_usd": 0.001,
                "attributes": {
                    "gen_ai.usage.input_tokens": 10,
                    "gen_ai.usage.output_tokens": 5,
                },
            },
        ]
    )
    monkeypatch.setattr(trace_service.task_service, "get_task", _owned)
    monkeypatch.setattr(trace_service, "_spans_collection", lambda: fake)

    summary = await trace_service.get_trace_summary("t1", user_id)
    assert summary is not None
    assert summary["input_tokens"] == 110
    assert summary["output_tokens"] == 55
    assert summary["cost_usd"] == pytest.approx(0.003)
    node = next(n for n in summary["nodes"] if n["name"] == "llm.chat")
    assert node["count"] == 2
