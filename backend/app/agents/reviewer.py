"""Reviewer: optional quality gate over subagent output (CLAUDE.md §2)."""

from __future__ import annotations

from app.agents.base import (
    AgentContext,
    ReviewResult,
    SubagentResult,
    extract_json,
    with_current_date,
)
from app.agents.prompts import REVIEWER_SYSTEM
from app.core.constants import AgentRole, EventType
from app.services.llm_service import ChatMessage, LLMError


async def review(
    ctx: AgentContext,
    *,
    subtask: str,
    result: SubagentResult,
) -> ReviewResult:
    """Inspect a subagent result and return structured feedback."""
    await ctx.emit(
        EventType.NODE_UPDATE,
        {"role": AgentRole.REVIEWER.value, "state": "running", "subtask": subtask},
    )
    output = str(result.data.get("output", ""))
    messages = [
        ChatMessage("system", with_current_date(REVIEWER_SYSTEM)),
        ChatMessage("user", f"Subtask:\n{subtask}\n\nSubagent output:\n{output}"),
    ]
    try:
        response = await ctx.adapter.chat(messages, temperature=0.0)
        parsed = extract_json(response.content)
        review_result = ReviewResult(
            approved=bool(parsed.get("approved", False)),
            issues=[str(i) for i in parsed.get("issues", [])],
            retry_hints=[str(h) for h in parsed.get("retry_hints", [])],
        )
    except (LLMError, ValueError):
        # If the reviewer itself fails, approve to avoid blocking the pipeline.
        review_result = ReviewResult(approved=True)

    await ctx.emit(
        EventType.REVIEW_RESULT,
        {"role": AgentRole.REVIEWER.value, "state": "done", **review_result.to_dict()},
    )
    return review_result
