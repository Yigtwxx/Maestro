"""Built-in view_original_request directive: on-demand raw-task access (no I/O)."""

from __future__ import annotations

import json
from typing import Any

from app.agents import subagent
from app.agents import tools as tool_directives
from app.agents.base import AgentContext
from app.agents.registry import get_domain_info
from app.core.constants import (
    ORIGINAL_REQUEST_OPEN,
    VIEW_ORIGINAL_REQUEST_ACTION,
    LLMProvider,
)
from app.services import data_fetch_service
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse

# software declares only code_execution, and conftest pins Docker off, so at
# runtime it has zero executable tools — the tool-less domain case.
TOOLLESS_DOMAIN = "software"
FETCH_DOMAIN = "searching"  # declares web_search + data_fetch

OBJECTIVE = "the big goal"
VIEW_DIRECTIVE = json.dumps({"action": "view_original_request"})
FETCH_DIRECTIVE = json.dumps({"action": "data_fetch", "url": "https://example.com/doc"})
FINAL_ANSWER = "Final answer."


class ScriptedAdapter(LLMAdapter):
    """Returns scripted replies in order; repeats the last when exhausted."""

    provider = LLMProvider.OLLAMA

    def __init__(self, replies: list[str]) -> None:
        super().__init__()
        self.replies = replies
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return LLMResponse(content=reply, model="fake", tokens_used=7)


async def _run(
    adapter: LLMAdapter, *, domain: str, objective: str = OBJECTIVE, **ctx_kwargs
):
    events: list[tuple[Any, dict]] = []

    async def emit(event_type, payload):  # noqa: ANN001 - EmitFn shape
        events.append((event_type, payload))

    ctx = AgentContext(adapter=adapter, emit=emit, **ctx_kwargs)
    member = get_domain_info(domain).team[0]
    result = await subagent.run_subtask(
        ctx,
        domain=domain,
        member=member,
        brief="Do the thing",
        index=0,
        objective=objective,
    )
    return result, events


def test_parse_directive_view_action_enabled_returns_directive():
    enabled = frozenset({VIEW_ORIGINAL_REQUEST_ACTION})
    directive = tool_directives.parse_directive(VIEW_DIRECTIVE, enabled)
    assert directive is not None, f"Expected directive for {VIEW_DIRECTIVE}"
    assert directive.action == VIEW_ORIGINAL_REQUEST_ACTION, directive


def test_parse_directive_view_action_disabled_returns_none():
    directive = tool_directives.parse_directive(VIEW_DIRECTIVE, frozenset())
    assert directive is None, f"Disabled action must be a final answer: {directive}"


async def test_view_directive_feeds_back_objective_in_toolless_domain():
    adapter = ScriptedAdapter([VIEW_DIRECTIVE, FINAL_ANSWER])
    result, _ = await _run(adapter, domain=TOOLLESS_DOMAIN)

    assert result.data["output"] == FINAL_ANSWER, result.data
    assert result.metadata["original_request_views"] == 1, result.metadata
    system_prompt = adapter.calls[0][0].content
    # The request now ships with the prompt as delimited context, so the model
    # no longer has to ask for it. The directive is kept anyway: it is how a
    # request longer than OBJECTIVE_MAX_CHARS gets read in full, and this test
    # covers that it still executes and still feeds the objective back.
    assert ORIGINAL_REQUEST_OPEN in system_prompt, system_prompt
    assert '"action": "view_original_request"' in system_prompt, system_prompt
    second_call_texts = [m.content for m in adapter.calls[1]]
    assert any(
        ORIGINAL_REQUEST_OPEN in text and OBJECTIVE in text
        for text in second_call_texts
    ), f"Objective not fed back inside tags: {second_call_texts}"


async def test_view_second_request_exhausts_budget_and_forces_final_answer():
    adapter = ScriptedAdapter([VIEW_DIRECTIVE, VIEW_DIRECTIVE, "Forced final."])
    result, _ = await _run(adapter, domain=TOOLLESS_DOMAIN)

    assert result.data["output"] == "Forced final.", result.data
    assert result.metadata["original_request_views"] == 1, result.metadata
    last_call_texts = [m.content for m in adapter.calls[2]]
    assert any("Tool budget exhausted" in t for t in last_call_texts), last_call_texts


async def test_view_does_not_consume_total_tool_budget(monkeypatch):
    fetch_calls: list[str] = []

    async def fake_fetch(
        url: str, *, selector: str | None = None, render: bool = False
    ) -> str:
        fetch_calls.append(url)
        return "<fetched_content>\nPage text.\n</fetched_content>"

    monkeypatch.setattr(data_fetch_service, "fetch", fake_fetch)
    adapter = ScriptedAdapter([VIEW_DIRECTIVE, FETCH_DIRECTIVE, FINAL_ANSWER])
    result, _ = await _run(adapter, domain=FETCH_DOMAIN, max_tool_calls=1)

    assert result.data["output"] == FINAL_ANSWER, result.data
    assert fetch_calls == ["https://example.com/doc"], (
        f"Fetch must still fit in the total budget, got {fetch_calls}"
    )
    assert result.metadata["tool_calls_used"] == 1, (
        f"View must not count as an executable call: {result.metadata}"
    )


async def test_view_directive_without_objective_is_final_answer():
    adapter = ScriptedAdapter([VIEW_DIRECTIVE])
    result, _ = await _run(adapter, domain=TOOLLESS_DOMAIN, objective="")

    assert result.data["output"] == VIEW_DIRECTIVE, result.data
    assert len(adapter.calls) == 1, f"Expected 1 LLM call, got {len(adapter.calls)}"
    system_prompt = adapter.calls[0][0].content
    assert '"action": "view_original_request"' not in system_prompt, system_prompt


async def test_view_directive_emits_live_stream_events():
    adapter = ScriptedAdapter([VIEW_DIRECTIVE, FINAL_ANSWER])
    _, events = await _run(adapter, domain=TOOLLESS_DOMAIN)

    tool_events = [
        payload
        for _, payload in events
        if payload.get("action") == VIEW_ORIGINAL_REQUEST_ACTION
    ]
    assert len(tool_events) == 2, f"Expected before/after events, got {tool_events}"
