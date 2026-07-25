"""Reviewer: optional quality gate over subagent output (CLAUDE.md §2)."""

from __future__ import annotations

import logging

from app.agents import validators
from app.agents.base import (
    AgentContext,
    ReviewResult,
    SubagentResult,
    format_optional_block,
    with_current_date,
)
from app.agents.domains.base import UNIVERSAL_CRITERIA, ReviewCriterion
from app.agents.prompts import REVIEWER_SYSTEM
from app.agents.registry import SubagentSpec, get_domain_info
from app.agents.schemas import ReviewVerdict
from app.agents.structured import structured_call
from app.core.config import settings
from app.core.constants import (
    REVIEW_APPROVAL_THRESHOLD,
    REVIEW_MAX_TOKENS,
    AgentRole,
    EventType,
)
from app.services.llm_service import ChatMessage, LLMError

logger = logging.getLogger(__name__)


def _criteria_block(criteria: tuple[ReviewCriterion, ...]) -> str:
    """Render structured criteria as a scored checklist for the reviewer prompt."""
    if not criteria:
        return ""
    lines = [
        f"{i + 1}. [{c.id}] {c.description}" + (" (must pass)" if c.hard_fail else "")
        for i, c in enumerate(criteria)
    ]
    return (
        "\n\nScore each criterion 0 (fails), 1 (partial), or 2 (meets) and return a "
        '"scores" object mapping each criterion id to its score:\n' + "\n".join(lines)
    )


def _weighted_approved(
    verdict_approved: bool,
    scores: dict[str, int],
    criteria: tuple[ReviewCriterion, ...],
) -> bool:
    """Weighted-threshold approval over structured scores.

    Falls back to the model's boolean ``approved`` when there are no criteria or
    the model returned no scores (small models often omit them) — so the
    structured path never makes the gate *stricter* by accident.
    """
    if not criteria or not scores:
        return verdict_approved
    max_total = sum(c.weight for c in criteria) * 2
    got = 0
    for c in criteria:
        score = max(0, min(2, int(scores.get(c.id, 0))))
        if c.hard_fail and score == 0:
            return False
        got += score * c.weight
    return max_total > 0 and got / max_total >= REVIEW_APPROVAL_THRESHOLD


def _on_reviewer_failure(index: int) -> ReviewResult:
    """Map a reviewer self-failure to a verdict per ``reviewer_fail_mode`` (D8)."""
    mode = settings.reviewer_fail_mode
    logger.warning(
        "reviewer failed (fail_mode=%s)",
        mode,
        exc_info=True,
        extra={"subtask_index": index},
    )
    if mode == "reject":
        return ReviewResult(
            approved=False,
            issues=["The reviewer could not evaluate this output."],
            retry_hints=["The reviewer was unavailable; re-run the subtask."],
        )
    if mode == "approve":
        return ReviewResult(approved=True)
    # "warn" (default): pass, but make the un-reviewed output visible.
    return ReviewResult(
        approved=True,
        issues=["Reviewer unavailable; auto-approved without review."],
        review_skipped=True,
    )


async def review(
    ctx: AgentContext,
    *,
    domain: str = "",
    subtask: str,
    result: SubagentResult,
    member: SubagentSpec | None = None,
    index: int = 0,
) -> ReviewResult:
    """Inspect a subagent result and return structured feedback, wrapped in a
    ``review`` trace span (Backend v2 §4.5)."""
    from app.core.constants import SpanKind
    from app.utils import tracing

    async with tracing.tracer.span(
        "review", SpanKind.AGENT, **{"maestro.role": AgentRole.REVIEWER.value}
    ) as span:
        verdict = await _review(
            ctx,
            domain=domain,
            subtask=subtask,
            result=result,
            member=member,
            index=index,
        )
        span.set_attribute("maestro.review.approved", verdict.approved)
        span.set_attribute("maestro.review.skipped", verdict.review_skipped)
        return verdict


async def _review(
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

    # Deterministic checks run first: an obvious miss is rejected here without
    # spending the reviewer's LLM call (Backend v2 §4.6).
    validation_hints = validators.validate(domain, member, output)
    if validation_hints:
        review_result = ReviewResult(
            approved=False, issues=validation_hints, retry_hints=validation_hints
        )
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

    info = ctx.domain_info or (get_domain_info(domain) if domain else None)
    rubric = info.review_rubric if info else ""
    # Grounding is judged everywhere, so the universal criteria lead and the
    # domain's own follow.
    #
    # This does change the gate for the domains that declare no criteria of their
    # own: they used to take the ``not criteria`` branch of _weighted_approved and
    # ride on the model's boolean ``approved``, and now they go through the
    # weighted threshold like everyone else. That is the point of the change, and
    # it is bounded — the model returning no ``scores`` still falls back to the
    # boolean, so a reviewer that cannot score never makes the gate stricter.
    criteria = UNIVERSAL_CRITERIA + (info.review_criteria if info else ())
    # Structured criteria render as a scored checklist appended to the string
    # rubric; a domain with only a string rubric keeps that rubric verbatim.
    rubric_body = rubric + _criteria_block(criteria)
    # REVIEWER_SYSTEM escapes literal JSON braces as {{...}}, so it must be
    # rendered via .format(); the rubric is replacement text, so any braces
    # inside it are not re-processed.
    system = REVIEWER_SYSTEM.format(
        rubric=format_optional_block("Acceptance criteria:", rubric_body)
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
        verdict = await structured_call(
            ctx.role_adapter("reviewer"),
            messages,
            ReviewVerdict,
            temperature=0.0,
            max_tokens=REVIEW_MAX_TOKENS,
        )
        review_result = ReviewResult(
            approved=_weighted_approved(verdict.approved, verdict.scores, criteria),
            issues=verdict.issues,
            retry_hints=verdict.retry_hints,
        )
    except (LLMError, ValueError):
        # The reviewer itself failed. What that means is configurable so a flaky
        # model can't silently turn the quality gate into a no-op (D8).
        review_result = _on_reviewer_failure(index)
        # Emitted here rather than inside `_on_reviewer_failure` to keep that a
        # pure verdict mapper. The fail mode is named because it tells the user
        # which way the quality gate swung when it could not evaluate.
        await ctx.emit(
            EventType.AGENT_WARNING,
            {
                "role": AgentRole.REVIEWER.value,
                "index": index,
                "kind": "degraded",
                "message": (
                    "Reviewer could not evaluate this output "
                    f"(fail mode: {settings.reviewer_fail_mode})."
                ),
            },
        )

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
