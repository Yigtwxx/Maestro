"""A blank specialist answer gets one push before it is failed.

An empty answer stays an error (see ``test_empty_subagent_answer``) — that
signal is what keeps a run where every member came back blank from reporting
``completed``. But a single blank reply is often recoverable: a small model
spends its output budget reasoning, or comes back from a fruitless search
judging it has nothing worth writing, and answers fine when asked once more.
These tests pin the retry and, just as importantly, its bounds: exactly one
extra call, never past the token cap, and a second blank still fails.
"""

from __future__ import annotations

import pytest

from app.agents import budget, subagent
from app.agents.base import AgentContext
from app.agents.prompts import SUBAGENT_EMPTY_ANSWER_NUDGE
from app.agents.registry import get_domain_info
from app.core.constants import EMPTY_SUBAGENT_ANSWER, LLMProvider, SubagentStatus
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse

DOMAIN = "general"
REAL_ANSWER = "Bitcoin traded near X on 2026-07-24. Data gaps: no Polymarket odds."


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
        return LLMResponse(
            content=self.replies[min(len(self.calls) - 1, len(self.replies) - 1)],
            model="fake",
            tokens_used=100,
        )


async def _run(adapter: LLMAdapter, **ctx_kwargs):
    ctx = AgentContext(adapter=adapter, **ctx_kwargs)
    member = get_domain_info(DOMAIN).team[0]
    return await subagent.run_subtask(
        ctx, domain=DOMAIN, member=member, brief="Analyze BTC", index=0
    )


@pytest.mark.parametrize("blank", ["", "   ", "\n\n", "\t \n"])
async def test_a_blank_first_reply_is_retried_once(blank: str):
    adapter = ScriptedAdapter([blank, REAL_ANSWER])
    result = await _run(adapter)

    assert result.status is SubagentStatus.SUCCESS, (
        f"A recovered answer must not fail: {result.data}"
    )
    assert result.data["output"] == REAL_ANSWER, result.data
    assert len(adapter.calls) == 2, (
        f"Expected exactly one retry, got {len(adapter.calls)}"
    )


async def test_the_retry_carries_the_nudge_and_the_original_transcript():
    adapter = ScriptedAdapter(["", REAL_ANSWER])
    await _run(adapter)

    retry_messages = adapter.calls[1]
    assert retry_messages[-1].content == SUBAGENT_EMPTY_ANSWER_NUDGE, retry_messages[-1]
    assert retry_messages[0] == adapter.calls[0][0], (
        "The system prompt must survive into the retry"
    )


async def test_the_retry_call_is_paid_for():
    """An expensive recovery must not be billed as if it were one call."""
    adapter = ScriptedAdapter(["", REAL_ANSWER])
    result = await _run(adapter)

    assert result.metadata["tokens_used"] == 200, (
        f"Both calls must be counted: {result.metadata}"
    )


async def test_two_blanks_in_a_row_still_fail():
    adapter = ScriptedAdapter(["", "   "])
    result = await _run(adapter)

    assert result.status is SubagentStatus.ERROR, (
        f"A member that never answers must fail: {result.data}"
    )
    assert result.data["error"] == EMPTY_SUBAGENT_ANSWER, result.data
    assert len(adapter.calls) == 2, (
        f"Only one retry is allowed, got {len(adapter.calls)}"
    )


async def test_a_normal_answer_never_triggers_a_retry():
    adapter = ScriptedAdapter([REAL_ANSWER])
    result = await _run(adapter)

    assert result.status is SubagentStatus.SUCCESS
    assert len(adapter.calls) == 1, f"Expected no extra call, got {len(adapter.calls)}"


async def test_an_exhausted_token_budget_skips_the_retry(monkeypatch):
    """The loop already forced a final answer; nudging past the cap is spend
    the task never authorized."""
    monkeypatch.setattr(budget, "budget_exceeded", lambda ctx: True)
    adapter = ScriptedAdapter(["", REAL_ANSWER])
    result = await _run(adapter)

    assert result.status is SubagentStatus.ERROR, (
        "Over budget, a blank answer must fail straight away"
    )
    assert len(adapter.calls) == 1, (
        f"No call may be made past the cap, got {len(adapter.calls)}"
    )
