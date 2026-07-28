"""Generalized tool directive loop: data_fetch + code_execution (no I/O)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agents import subagent
from app.agents import tools as tool_directives
from app.agents.base import AgentContext
from app.agents.registry import get_domain_info
from app.core.config import settings
from app.core.constants import (
    CODE_EXECUTION_ACTION,
    DATA_FETCH_ACTION,
    DATA_FETCH_SELECTOR_MAX_CHARS,
    WEB_SEARCH_ACTION,
    LLMProvider,
)
from app.services import code_execution_service, data_fetch_service
from app.services.code_execution_service import ExecutionResult
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse

FETCH_DOMAIN = "searching"  # declares web_search + data_fetch
CODE_DOMAIN = "software"  # declares code_execution (no web_search)

FETCH_DIRECTIVE = json.dumps({"action": "data_fetch", "url": "https://example.com/doc"})
CODE_DIRECTIVE = json.dumps({"action": "code_execution", "code": "print(2 + 2)"})
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


@pytest.fixture
def fetch_calls(monkeypatch) -> list[str]:
    calls: list[str] = []

    async def fake_fetch(
        url: str, *, selector: str | None = None, render: bool = False
    ) -> str:
        calls.append(url)
        return "<fetched_content>\nPage text.\n</fetched_content>"

    monkeypatch.setattr(data_fetch_service, "fetch", fake_fetch)
    return calls


@pytest.fixture
def exec_calls(monkeypatch) -> list[str]:
    calls: list[str] = []

    async def fake_run(code: str) -> ExecutionResult:
        calls.append(code)
        return ExecutionResult(stdout="4\n", exit_code=0)

    monkeypatch.setattr(code_execution_service, "run_python", fake_run)
    monkeypatch.setattr(code_execution_service, "_availability", True)
    # The operator switch ships off, so the tool needs both gates opened here.
    monkeypatch.setattr(settings, "code_execution_enabled", True)
    return calls


async def _run(adapter: LLMAdapter, *, domain: str, **ctx_kwargs):
    events: list[tuple[Any, dict]] = []

    async def emit(event_type, payload):  # noqa: ANN001 - EmitFn shape
        events.append((event_type, payload))

    ctx = AgentContext(adapter=adapter, emit=emit, **ctx_kwargs)
    member = get_domain_info(domain).team[0]
    result = await subagent.run_subtask(
        ctx, domain=domain, member=member, brief="Do the thing", index=0
    )
    return result, events


async def test_data_fetch_directive_round_trip(fetch_calls):
    adapter = ScriptedAdapter([FETCH_DIRECTIVE, FINAL_ANSWER])
    result, _ = await _run(adapter, domain=FETCH_DOMAIN)

    assert result.data["output"] == FINAL_ANSWER, result.data
    assert fetch_calls == ["https://example.com/doc"], fetch_calls
    assert result.metadata["fetches_used"] == 1, result.metadata
    second_call_texts = [m.content for m in adapter.calls[1]]
    assert any("Page text." in t for t in second_call_texts), second_call_texts


async def test_code_execution_directive_round_trip(exec_calls):
    adapter = ScriptedAdapter([CODE_DIRECTIVE, FINAL_ANSWER])
    result, _ = await _run(adapter, domain=CODE_DOMAIN)

    assert result.data["output"] == FINAL_ANSWER, result.data
    assert exec_calls == ["print(2 + 2)"], exec_calls
    assert result.metadata["executions_used"] == 1, result.metadata
    second_call_texts = [m.content for m in adapter.calls[1]]
    assert any("4" in t for t in second_call_texts), second_call_texts


async def test_total_tool_budget_forces_final_answer(fetch_calls):
    adapter = ScriptedAdapter([FETCH_DIRECTIVE, FETCH_DIRECTIVE, "Forced final."])
    result, _ = await _run(
        adapter, domain=FETCH_DOMAIN, max_data_fetches=5, max_tool_calls=1
    )

    assert result.data["output"] == "Forced final.", result.data
    assert len(fetch_calls) == 1, f"Only one fetch within budget, got {fetch_calls}"
    last_call_texts = [m.content for m in adapter.calls[2]]
    assert any("Tool budget exhausted" in t for t in last_call_texts), last_call_texts


async def test_directive_for_undeclared_tool_is_final_answer(fetch_calls):
    # software does not declare data_fetch; the directive is just an answer.
    adapter = ScriptedAdapter([FETCH_DIRECTIVE])
    result, _ = await _run(adapter, domain=CODE_DOMAIN)

    assert result.data["output"] == FETCH_DIRECTIVE, result.data
    assert fetch_calls == [], "Fetch must never run for undeclared domains"
    assert len(adapter.calls) == 1, f"Expected 1 LLM call, got {len(adapter.calls)}"


async def test_docker_unavailable_removes_code_rule_from_prompt():
    # conftest pins the sandbox as unavailable by default.
    adapter = ScriptedAdapter([FINAL_ANSWER])
    _, _ = await _run(adapter, domain=CODE_DOMAIN)

    system_prompt = adapter.calls[0][0].content
    assert '"action": "code_execution"' not in system_prompt, system_prompt


async def test_docker_available_adds_code_rule_to_prompt(exec_calls):
    adapter = ScriptedAdapter([FINAL_ANSWER])
    _, _ = await _run(adapter, domain=CODE_DOMAIN)

    system_prompt = adapter.calls[0][0].content
    assert '"action": "code_execution"' in system_prompt, system_prompt
    assert "You can use tools" in system_prompt, system_prompt


async def test_tool_events_reach_live_stream(fetch_calls):
    adapter = ScriptedAdapter([FETCH_DIRECTIVE, FINAL_ANSWER])
    _, events = await _run(adapter, domain=FETCH_DOMAIN)

    tool_events = [p for _, p in events if p.get("action") == DATA_FETCH_ACTION]
    assert len(tool_events) == 2, f"Expected before/after events, got {tool_events}"
    assert all(p["url"] == "https://example.com/doc" for p in tool_events), tool_events


@pytest.mark.parametrize(
    ("content", "expected_action"),
    [
        ('{"action": "web_search", "query": "q"}', WEB_SEARCH_ACTION),
        ('{"action": "data_fetch", "url": "https://x.example"}', DATA_FETCH_ACTION),
        ('{"action": "code_execution", "code": "print(1)"}', CODE_EXECUTION_ACTION),
    ],
)
def test_parse_directive_known_actions(content: str, expected_action: str):
    enabled = frozenset({WEB_SEARCH_ACTION, DATA_FETCH_ACTION, CODE_EXECUTION_ACTION})
    directive = tool_directives.parse_directive(content, enabled)
    assert directive is not None, f"Expected directive for {content}"
    assert directive.action == expected_action, directive


@pytest.mark.parametrize(
    ("render_value", "expected"),
    [
        ("true", True),
        (True, True),
        ("yes", True),
        (1, True),
        ("false", False),
        (False, False),
        (None, False),
    ],
)
def test_parse_directive_data_fetch_render_coercion(render_value, expected: bool):
    """Models emit true/"true"/"yes"/1 interchangeably for a boolean flag."""
    content = json.dumps(
        {"action": "data_fetch", "url": "https://x.example", "render": render_value}
    )
    directive = tool_directives.parse_directive(content, frozenset({DATA_FETCH_ACTION}))
    assert directive is not None, content
    assert (directive.args.get("render") == "true") is expected, directive.args


def test_parse_directive_data_fetch_keeps_selector():
    content = json.dumps(
        {"action": "data_fetch", "url": "https://x.example", "selector": "h2.title"}
    )
    directive = tool_directives.parse_directive(content, frozenset({DATA_FETCH_ACTION}))
    assert directive is not None, content
    assert directive.args["selector"] == "h2.title", directive.args


@pytest.mark.parametrize(
    "selector",
    ["a" * (DATA_FETCH_SELECTOR_MAX_CHARS + 1), "h2\ninjected"],
)
def test_parse_directive_drops_malformed_selector_but_keeps_url(selector: str):
    """A bad selector must degrade to a full-text fetch, not kill the directive.

    Returning None here would make the loop read the JSON as the subagent's
    final answer, which is strictly worse than fetching the whole page.
    """
    content = json.dumps(
        {"action": "data_fetch", "url": "https://x.example", "selector": selector}
    )
    directive = tool_directives.parse_directive(content, frozenset({DATA_FETCH_ACTION}))
    assert directive is not None, "The directive must survive a bad selector"
    assert directive.args == {"url": "https://x.example"}, directive.args


@pytest.mark.parametrize(
    "content",
    [
        "plain text answer",
        '{"action": "web_search"}',  # missing required arg
        '{"action": "data_fetch", "url": ""}',  # empty arg
        '{"action": "unknown_tool", "query": "q"}',  # unknown action
        '{"result": {"action": "none"}, "summary": "a JSON deliverable"}',
    ],
)
def test_parse_directive_non_directives_return_none(content: str):
    enabled = frozenset({WEB_SEARCH_ACTION, DATA_FETCH_ACTION, CODE_EXECUTION_ACTION})
    directive = tool_directives.parse_directive(content, enabled)
    assert directive is None, f"{content!r} must be a final answer, got {directive}"
