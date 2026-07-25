"""An empty specialist answer must be a failure, not a hollow success.

The defect this covers: ``run_subtask`` used to return SUCCESS whenever no
exception was raised, so a model that spent its whole output budget reasoning
(or emitted only a ``<think>`` block) produced a green card, an empty string fed
into synthesis, and — worst of all — a task where *every* member came back blank
still reported ``completed``, because ``all_subtasks_failed`` counts ERROR
results and there were none.

These tests pin both halves: the subagent's own verdict, and the aggregate
signal the task layer turns into a terminal status.
"""

from __future__ import annotations

import pytest

from app.agents import main_agent, subagent
from app.agents.base import AgentContext
from app.agents.registry import get_domain_info
from app.core.constants import EMPTY_SUBAGENT_ANSWER, LLMProvider, SubagentStatus
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse
from tests.test_agents_flow import FakeAdapter

DOMAIN = "general"


class ReplyingAdapter(LLMAdapter):
    """Returns one fixed reply to every call."""

    provider = LLMProvider.OLLAMA

    def __init__(self, reply: str) -> None:
        super().__init__()
        self.reply = reply

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        return LLMResponse(content=self.reply, model="fake", tokens_used=4242)


async def _run(reply: str):
    events: list[dict] = []

    async def emit(event_type, payload):  # noqa: ANN001 - EmitFn shape
        events.append(payload)

    ctx = AgentContext(adapter=ReplyingAdapter(reply), emit=emit)
    member = get_domain_info(DOMAIN).team[0]
    result = await subagent.run_subtask(
        ctx, domain=DOMAIN, member=member, brief="Do the thing", index=0
    )
    return result, events


@pytest.mark.parametrize("reply", ["", "   ", "\n\n", "\t \n"])
async def test_a_blank_answer_is_an_error(reply):
    result, _ = await _run(reply)

    assert result.status is SubagentStatus.ERROR, (
        f"A blank answer must not be SUCCESS, got {result.status}"
    )
    assert "empty answer" in result.data["error"], (
        f"The error must name the cause: {result.data['error']}"
    )


async def test_a_blank_answer_closes_the_node_as_error():
    """Otherwise the card stays mid-run and later freezes to 'done'."""
    _, events = await _run("")

    node_states = [e.get("state") for e in events if "state" in e]
    assert node_states[-1] == "error", (
        f"The node must be closed as error, got {node_states}"
    )


async def test_a_blank_answer_still_reports_the_tokens_it_burned():
    """The spend was real; losing it would hide an expensive failure.

    Two calls, because a blank reply now earns one retry before it fails
    (``test_subagent_blank_retry``) — and that retry is billed too.
    """
    result, _ = await _run("")

    assert result.metadata.get("tokens_used") == 4242 * 2, (
        f"Both the answer and its retry must be counted: {result.metadata}"
    )


async def test_a_normal_answer_is_unaffected():
    result, _ = await _run("A real answer.")

    assert result.status is SubagentStatus.SUCCESS, "Real output must still pass"
    assert result.data["output"] == "A real answer.", "Output must be preserved"


class BlankSubagentAdapter(FakeAdapter):
    """Planner and synthesis behave; every subagent answers with whitespace.

    The real-world shape: a small model spends its output budget reasoning and
    emits no final text. Nothing raises, so this used to look like a clean run.
    """

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system = messages[0].content
        is_subagent = (
            "Main Agent, the manager" not in system and "specialist subagent" in system
        )
        if is_subagent:
            return LLMResponse(content="   \n  ", model="fake", tokens_used=900)
        return await super().chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )


async def test_every_member_blank_flags_the_task_as_all_failed():
    """The aggregate half, end to end through the Main Agent.

    ``task_engine._finalize`` maps ``all_subtasks_failed`` to
    ``TaskStatus.FAILED``, so this flag is what stops a run that produced
    nothing from reporting `completed` with a hollow answer.
    """
    ctx = AgentContext(adapter=BlankSubagentAdapter())

    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )

    statuses = {subtask["status"] for subtask in result["subtasks"]}
    assert statuses == {SubagentStatus.ERROR.value}, (
        f"Blank members must all be errors, got {statuses}"
    )
    assert result["all_subtasks_failed"] is True, (
        "A run where every member came back blank must be flagged failed"
    )
    assert result["answer"] == "No successful subtask output.", (
        f"Synthesis must be skipped, got {result['answer']!r}"
    )


async def test_the_reported_failure_reason_names_the_empty_answer():
    """The terminal log and the UI should say why, not just that it failed."""
    ctx = AgentContext(adapter=BlankSubagentAdapter())

    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )

    assert result["failure_reason"] == EMPTY_SUBAGENT_ANSWER, (
        f"Expected the empty-answer reason, got {result.get('failure_reason')!r}"
    )
