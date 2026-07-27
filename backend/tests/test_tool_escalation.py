"""Phase B: a subagent escalates to the Main Agent for a tool it was not given.

The approver is the Main Agent LLM (autonomous, agent-to-agent) — not the
human-in-the-loop channel. A grant mutates the running loop's tool set; the
grant count and granted specs stay LOCAL to each ``_run_subtask``, so a wave of
siblings sharing one AgentContext never leaks grants between members.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agents import main_agent, subagent
from app.agents.base import AgentContext
from app.agents.registry import get_domain_info
from app.agents.schemas import GrantDecision
from app.core.constants import (
    DATA_FETCH_ACTION,
    REQUEST_TOOL_ACTION,
    WEB_SEARCH_ACTION,
    LLMProvider,
)
from app.services import data_fetch_service
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse

DOMAIN = "searching"  # declares web_search + data_fetch

# Assign only web_search, so data_fetch is the sole grantable tool.
ASSIGNED = frozenset({WEB_SEARCH_ACTION})

REQUEST_FETCH = json.dumps(
    {
        "action": REQUEST_TOOL_ACTION,
        "tool": DATA_FETCH_ACTION,
        "justification": "the brief needs the page contents",
    }
)
REQUEST_CODE = json.dumps(
    {
        "action": REQUEST_TOOL_ACTION,
        "tool": "code_execution",  # not declared by searching → ungrantable
        "justification": "want to run code",
    }
)
FETCH_DIRECTIVE = json.dumps({"action": "data_fetch", "url": "https://example.com/x"})
FINAL = "Final answer."


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
def gatekeeper_spy(monkeypatch) -> list[str]:
    """Records each requested tool; grants everything by default."""
    seen: list[str] = []

    async def fake_review(ctx, *, domain, member, requested_tool, justification, brief):
        seen.append(requested_tool)
        return GrantDecision(grant=True, reason="ok")

    monkeypatch.setattr(main_agent, "gatekeeper_review", fake_review)
    return seen


def _deny(monkeypatch) -> None:
    async def fake_review(ctx, *, domain, member, requested_tool, justification, brief):
        return GrantDecision(grant=False, reason="not warranted")

    monkeypatch.setattr(main_agent, "gatekeeper_review", fake_review)


async def _run(adapter: LLMAdapter, *, member=None, **ctx_kwargs):
    ctx = AgentContext(adapter=adapter, **ctx_kwargs)
    member = member or get_domain_info(DOMAIN).team[0]
    return await subagent.run_subtask(
        ctx,
        domain=DOMAIN,
        member=member,
        brief="Do the thing",
        index=0,
        assigned_tools=ASSIGNED,
    )


async def test_grant_adds_tool_to_running_loop(fetch_calls, gatekeeper_spy):
    adapter = ScriptedAdapter([REQUEST_FETCH, FETCH_DIRECTIVE, FINAL])
    result = await _run(adapter)

    assert gatekeeper_spy == [DATA_FETCH_ACTION], gatekeeper_spy
    assert fetch_calls == ["https://example.com/x"], fetch_calls
    assert result.data["output"] == FINAL, result.data
    assert result.metadata["fetches_used"] == 1, result.metadata


async def test_denied_request_keeps_tool_disabled(fetch_calls, monkeypatch):
    _deny(monkeypatch)
    # After the denial the model gives up and answers.
    adapter = ScriptedAdapter([REQUEST_FETCH, FINAL])
    result = await _run(adapter)

    assert fetch_calls == [], "a denied tool must never execute"
    assert result.data["output"] == FINAL, result.data
    assert "declined" in "\n".join(m.content for c in adapter.calls for m in c), (
        "the denial reason should be fed back"
    )


async def test_ungrantable_tool_skips_gatekeeper(fetch_calls, gatekeeper_spy):
    # code_execution is not in the searching domain → refused locally, no LLM call.
    adapter = ScriptedAdapter([REQUEST_CODE, FINAL])
    result = await _run(adapter)

    assert gatekeeper_spy == [], (
        "gatekeeper must not be consulted for ungrantable tools"
    )
    assert "cannot be granted" in "\n".join(m.content for c in adapter.calls for m in c)
    assert result.data["output"] == FINAL, result.data


async def test_grant_budget_caps_requests(fetch_calls, gatekeeper_spy):
    # Two requests but only one grant allowed: the second is refused locally.
    adapter = ScriptedAdapter([REQUEST_FETCH, REQUEST_FETCH, FINAL])
    result = await _run(adapter, max_tool_grants=1)

    assert len(gatekeeper_spy) == 1, "only the first request reaches the gatekeeper"
    assert "Grant limit reached" in "\n".join(
        m.content for c in adapter.calls for m in c
    )
    assert result.data["output"] == FINAL, result.data


async def test_grant_state_is_per_run_not_per_context(fetch_calls, gatekeeper_spy):
    """Grant budget is local to a run, so siblings sharing one ctx don't share it.

    A wave of siblings shares a single AgentContext. If the grant count lived on
    ctx, the first member to spend the only allowed grant (``max_tool_grants=1``)
    would starve every later member. Because the count is local to each
    ``_run_subtask``, both members grant and both fetches run. Run sequentially
    on purpose: the property under test is that state is per-run, and a shared
    stateful scripted adapter cannot be driven by two coroutines at once.
    """
    ctx = AgentContext(adapter=None, max_tool_grants=1)
    team = get_domain_info(DOMAIN).team

    async def one(member) -> Any:
        ctx.adapter = ScriptedAdapter([REQUEST_FETCH, FETCH_DIRECTIVE, FINAL])
        return await subagent.run_subtask(
            ctx,
            domain=DOMAIN,
            member=member,
            brief="Do the thing",
            index=0,
            assigned_tools=ASSIGNED,
        )

    first = await one(team[0])
    second = await one(team[1])

    assert len(gatekeeper_spy) == 2, "both members must reach the gatekeeper"
    assert len(fetch_calls) == 2, "both members' granted fetches must run"
    assert first.metadata["fetches_used"] == 1, first.metadata
    assert second.metadata["fetches_used"] == 1, second.metadata
