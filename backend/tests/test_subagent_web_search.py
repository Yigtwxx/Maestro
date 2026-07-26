"""Tests for the subagent web-search directive loop (no network)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agents import subagent
from app.agents.base import AgentContext
from app.agents.prompts import SUBAGENT_NO_RETRIEVAL_NUDGE
from app.agents.registry import get_domain_info
from app.core.constants import (
    WEB_SEARCH_RESULTS_OPEN,
    EventType,
    LLMProvider,
    SubagentStatus,
)
from app.services import web_search_service
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse
from app.services.web_search_service import SearchOutcome, SearchResult

SEARCH_DOMAIN = "searching"  # declares the web_search tool
NO_SEARCH_DOMAIN = "software"  # does not declare web_search

DIRECTIVE = json.dumps(
    {"action": "web_search", "query": "latest claude news", "category": "news"}
)
FINAL_ANSWER = "Final answer using fresh results."


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


@pytest.fixture
def search_calls(monkeypatch) -> list[tuple[str, str]]:
    """Stub the search service; record (query, category) calls."""
    calls: list[tuple[str, str]] = []

    async def fake_search(query: str, *, category: str = "text"):
        calls.append((query, category))
        return SearchOutcome(
            results=[
                SearchResult(
                    title="Anthropic ships new model",
                    url="https://news.example/a",
                    snippet="Fresh news snippet.",
                    date="2026-07-01",
                )
            ],
            query=query,
            attempted=[query],
        )

    monkeypatch.setattr(web_search_service, "search", fake_search)
    return calls


def _ctx(adapter: LLMAdapter, events: list[tuple[Any, dict]], **kwargs) -> AgentContext:
    async def emit(event_type, payload):  # noqa: ANN001 - EmitFn shape
        events.append((event_type, payload))

    return AgentContext(adapter=adapter, emit=emit, **kwargs)


async def _run(ctx: AgentContext, *, domain: str):
    member = get_domain_info(domain).team[0]
    return await subagent.run_subtask(
        ctx, domain=domain, member=member, brief="Summarize recent news", index=0
    )


async def test_subagent_directive_triggers_search_and_returns_final_answer(
    search_calls,
):
    adapter = ScriptedAdapter([DIRECTIVE, FINAL_ANSWER])
    events: list[tuple[Any, dict]] = []
    result = await _run(_ctx(adapter, events), domain=SEARCH_DOMAIN)

    assert result.status is SubagentStatus.SUCCESS
    assert result.data["output"] == FINAL_ANSWER, result.data
    assert result.metadata["searches_used"] == 1, result.metadata
    assert search_calls == [("latest claude news", "news")], search_calls
    # Results block was fed back before the second LLM call.
    second_call_texts = [m.content for m in adapter.calls[1]]
    assert any(WEB_SEARCH_RESULTS_OPEN in t for t in second_call_texts), (
        second_call_texts
    )
    # Search activity is visible in the live stream.
    search_events = [
        p for e, p in events if e is EventType.AGENT_MESSAGE and "query" in p
    ]
    assert [p["query"] for p in search_events] == ["latest claude news"] * 2, events


async def test_subagent_plain_answer_is_nudged_once_but_never_forced_to_search(
    search_calls,
):
    """A member holding search and never using it gets one question, not a search.

    Four escalating system-prompt rules failed to make a local model retrieve
    before asserting a fact, and it kept describing sources it had never opened.
    The nudge is a user-role turn asking it to either retrieve or stand behind
    the answer unchanged — deliberately not a forced search, because for a
    general-knowledge question not searching is the right call.

    So: exactly one extra call, no search executed when the model declines, and
    the original answer preserved.
    """
    adapter = ScriptedAdapter(["Just a direct answer."])
    result = await _run(_ctx(adapter, []), domain=SEARCH_DOMAIN)

    assert result.data["output"] == "Just a direct answer."
    assert result.metadata["searches_used"] == 0, result.metadata
    assert len(adapter.calls) == 2, f"Expected 1 nudge, got {len(adapter.calls)}"
    assert search_calls == [], "Search must not run without a directive"
    assert adapter.calls[1][-1].content == SUBAGENT_NO_RETRIEVAL_NUDGE, adapter.calls[
        1
    ][-1]


async def test_a_member_that_already_searched_is_not_nudged(search_calls):
    """The nudge exists for a member that retrieved nothing, not for every member."""
    adapter = ScriptedAdapter([DIRECTIVE, "Answer from the results."])
    result = await _run(
        _ctx(adapter, [{"title": "t", "url": "u", "snippet": "s"}]),
        domain=SEARCH_DOMAIN,
    )

    assert result.metadata["searches_used"] == 1, result.metadata
    assert len(adapter.calls) == 2, f"No nudge expected, got {len(adapter.calls)}"


async def test_subagent_search_budget_exhaustion_forces_final_answer(search_calls):
    adapter = ScriptedAdapter([DIRECTIVE, DIRECTIVE, "Forced final."])
    result = await _run(_ctx(adapter, [], max_web_searches=1), domain=SEARCH_DOMAIN)

    assert result.data["output"] == "Forced final.", result.data
    assert result.metadata["searches_used"] == 1, result.metadata
    assert len(adapter.calls) == 3, f"Expected max+2 calls, got {len(adapter.calls)}"
    last_call_texts = [m.content for m in adapter.calls[2]]
    assert any("Tool budget exhausted" in t for t in last_call_texts), last_call_texts
    assert search_calls == [("latest claude news", "news")], search_calls


async def test_subagent_empty_results_appends_no_results_notice(monkeypatch):
    async def empty_search(query: str, *, category: str = "text"):
        return SearchOutcome(query=query, attempted=[query, "relaxed variant"])

    monkeypatch.setattr(web_search_service, "search", empty_search)
    adapter = ScriptedAdapter([DIRECTIVE, FINAL_ANSWER])
    result = await _run(_ctx(adapter, []), domain=SEARCH_DOMAIN)

    assert result.data["output"] == FINAL_ANSWER
    second_call_texts = [m.content for m in adapter.calls[1]]
    notice = next(
        (t for t in second_call_texts if "No web results for any of these" in t), ""
    )
    assert notice, second_call_texts
    # Naming the exhausted variants is what stops the model resending them.
    assert '"relaxed variant"' in notice, notice


async def test_subagent_domain_without_web_search_tool_gets_no_tool_prompt(
    search_calls,
):
    adapter = ScriptedAdapter([DIRECTIVE])
    result = await _run(_ctx(adapter, []), domain=NO_SEARCH_DOMAIN)

    system_prompt = adapter.calls[0][0].content
    assert '"action": "web_search"' not in system_prompt, system_prompt
    assert len(adapter.calls) == 1, "Directive must be treated as a final answer"
    assert search_calls == [], "Search must never run for non-search domains"
    assert "searches_used" not in result.metadata, result.metadata
