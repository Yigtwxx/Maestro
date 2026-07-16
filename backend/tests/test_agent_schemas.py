"""Malformed LLM output degrades gracefully via the agent Pydantic schemas."""

from __future__ import annotations

import pytest

from app.agents import main_agent, orchestrator, reviewer
from app.agents.base import AgentContext, SubagentResult
from app.agents.registry import get_domain_info
from app.core.constants import LLMProvider, SubagentStatus
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse

SOFTWARE_TEAM_SIZE = len(get_domain_info("software").team)


class RawReplyAdapter(LLMAdapter):
    """Returns a fixed raw reply for the first (planning/routing/review) call
    and a plain answer for every later call."""

    provider = LLMProvider.OLLAMA

    def __init__(self, first_reply: str) -> None:
        self._first_reply = first_reply
        self._calls = 0

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self._calls += 1
        content = self._first_reply if self._calls == 1 else "plain output"
        return LLMResponse(content=content, model="fake", tokens_used=1)


@pytest.mark.parametrize(
    "reply",
    [
        '{"assignments": "just do it"}',  # assignments is not a list
        '{"assignments": ["coder", "tester"]}',  # items are not objects
        '{"assignments": [{"member": 42, "brief": ["x"]}]}',  # wrong field types
    ],
)
async def test_plan_malformed_assignments_falls_back_to_full_team(reply: str) -> None:
    ctx = AgentContext(adapter=RawReplyAdapter(reply))
    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )
    count = result["metadata"]["subtask_count"]
    assert count == SOFTWARE_TEAM_SIZE, f"Expected full-team fallback, got {count}"


@pytest.mark.parametrize(
    "reply",
    [
        '{"domain": 123, "reason": "numeric"}',  # wrong type -> ValidationError
        '{"domain": "not_a_domain"}',  # unknown id -> normalize_domain
        '{"reason": "missing domain"}',  # empty default -> normalize_domain
        "not json at all",
    ],
)
async def test_route_malformed_decision_falls_back_to_general(reply: str) -> None:
    ctx = AgentContext(adapter=RawReplyAdapter(reply))
    domain = await orchestrator.route(ctx, "do something")
    assert domain == "general", f"Expected general fallback, got {domain}"


@pytest.mark.parametrize(
    "reply",
    [
        '{"approved": "yes-ish"}',  # not coercible to bool
        '{"approved": false, "issues": [{"nested": true}]}',  # non-string issue
        "garbage",
    ],
)
async def test_review_malformed_verdict_fails_open(reply: str) -> None:
    # Default reviewer_fail_mode is "warn": a reviewer that cannot produce a
    # verdict still passes (does not block the pipeline) but flags the skipped
    # review so the gate's silence is visible (Backend v2 §4.6/D8).
    ctx = AgentContext(adapter=RawReplyAdapter(reply))
    result = SubagentResult(
        status=SubagentStatus.SUCCESS,
        data={"output": "This is a complete answer to the subtask, long enough."},
    )
    verdict = await reviewer.review(ctx, subtask="check it", result=result)
    assert verdict.approved is True, "Reviewer must fail open (warn) when it fails"
    assert verdict.review_skipped is True, "A skipped review must be flagged"


def test_reviewer_system_prompt_renders_single_braces() -> None:
    from app.agents.prompts import REVIEWER_SYSTEM

    rendered = REVIEWER_SYSTEM.format(rubric="")
    assert '{"approved"' in rendered, "JSON schema example must render"
    assert "{{" not in rendered, "No escaped braces may leak to the LLM"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"member": "coder", "brief": "b"}, []),  # old shape stays valid
        ({"member": "coder", "brief": "b", "depends_on": None}, []),
        ({"member": "coder", "brief": "b", "depends_on": "architect"}, ["architect"]),
        ({"member": "coder", "brief": "b", "depends_on": "  "}, []),
        ({"member": "coder", "brief": "b", "depends_on": ["a", "b"]}, ["a", "b"]),
    ],
)
def test_plan_assignment_depends_on_coercion(raw: dict, expected: list[str]) -> None:
    from app.agents.schemas import PlanAssignment

    parsed = PlanAssignment.model_validate(raw)
    assert parsed.depends_on == expected, (
        f"Expected {expected}, got {parsed.depends_on}"
    )


async def test_review_valid_rejection_is_preserved() -> None:
    reply = '{"approved": false, "issues": ["wrong"], "retry_hints": ["fix it"]}'
    ctx = AgentContext(adapter=RawReplyAdapter(reply))
    result = SubagentResult(
        status=SubagentStatus.SUCCESS,
        data={"output": "This is a complete answer to the subtask, long enough."},
    )
    verdict = await reviewer.review(ctx, subtask="check it", result=result)
    assert verdict.approved is False, "Valid rejection must not be coerced to approve"
    assert verdict.retry_hints == ["fix it"], f"Got {verdict.retry_hints}"
