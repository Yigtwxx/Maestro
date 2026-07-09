"""Reviewer: optional quality gate over subagent output (CLAUDE.md §2)."""

from __future__ import annotations

from app.agents.base import (
    AgentContext,
    ReviewResult,
    SubagentResult,
    extract_json,
    format_optional_block,
    with_current_date,
)
from app.agents.prompts import REVIEWER_SYSTEM
from app.agents.registry import SubagentSpec, get_domain_info
from app.agents.schemas import ReviewVerdict
from app.core.constants import REVIEW_MAX_TOKENS, AgentRole, EventType
from app.services.llm_service import ChatMessage, LLMError


async def review(
    ctx: AgentContext,
    *,
    domain: str = "",
    subtask: str,
    result: SubagentResult,
    member: SubagentSpec | None = None,
    index: int = 0,
) -> ReviewResult:
    """Inspect a subagent result and return structured feedback.

    ``domain`` selects the domain-specific review rubric; ``member`` tells the
    reviewer who produced the output; ``index`` scopes events to the reviewed
    subtask (subtasks may run in parallel).
    """
    await ctx.emit(
        EventType.NODE_UPDATE,
        {
            "role": AgentRole.REVIEWER.value,
            "state": "running",
            "subtask": subtask,
            "index": index,
        },
    )
    output = str(result.data.get("output", ""))
    rubric = get_domain_info(domain).review_rubric if domain else ""
    # REVIEWER_SYSTEM escapes literal JSON braces as {{...}}, so it must be
    # rendered via .format(); the rubric is replacement text, so any braces
    # inside it are not re-processed.
    system = REVIEWER_SYSTEM.format(
        rubric=format_optional_block("Domain-specific review criteria:", rubric)
    )
    producer = (
        f'Produced by "{member.name}" whose role is: {member.role}.\n\n'
        if member
        else ""
    )
    messages = [
        ChatMessage("system", with_current_date(system)),
        ChatMessage(
            "user", f"{producer}Subtask:\n{subtask}\n\nSubagent output:\n{output}"
        ),
    ]
    try:
        response = await ctx.adapter.chat(
            messages, temperature=0.0, max_tokens=REVIEW_MAX_TOKENS
        )
        verdict = ReviewVerdict.model_validate(extract_json(response.content))
        review_result = ReviewResult(
            approved=verdict.approved,
            issues=verdict.issues,
            retry_hints=verdict.retry_hints,
        )
    except (LLMError, ValueError):
        # If the reviewer itself fails, approve to avoid blocking the pipeline.
        review_result = ReviewResult(approved=True)

    await ctx.emit(
        EventType.REVIEW_RESULT,
        {
            "role": AgentRole.REVIEWER.value,
            "state": "done",
            "index": index,
            **review_result.to_dict(),
        },
    )
    return review_result
