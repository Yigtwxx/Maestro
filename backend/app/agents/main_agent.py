"""Main Agent: briefs its fixed domain team, coordinates subagents + optional
reviewer, then synthesizes the final answer (CLAUDE.md §2).

The team roster is fixed per domain (``registry.DOMAIN_CATALOG``): the LLM
only decides which members are relevant to the task and what brief each one
gets — it can never invent members. If briefing fails, every member runs with
the raw prompt so the pipeline never stalls.

Loop protection: assignment count is capped by ``max_iterations`` and each
reviewer↔subagent retry loop by ``max_review_iterations`` (CLAUDE.md §9.2).
"""

from __future__ import annotations

from typing import Any

from app.agents import reviewer as reviewer_agent
from app.agents import subagent as subagent_worker
from app.agents.base import (
    AgentContext,
    SubagentResult,
    extract_json,
    format_memory_block,
    format_optional_block,
    with_current_date,
)
from app.agents.prompts import (
    MAIN_AGENT_CLARIFY_RULE,
    MAIN_AGENT_SYSTEM,
    SYNTHESIS_SYSTEM,
)
from app.agents.registry import SubagentSpec, get_domain_info
from app.agents.schemas import PlanAssignment, PlanResult
from app.core.constants import (
    MAX_SUBTASKS,
    PLAN_MAX_TOKENS,
    SYNTHESIS_MAX_TOKENS,
    AgentRole,
    EventType,
    SubagentStatus,
)
from app.services.llm_service import ChatMessage, LLMError

# One team member with its task-specific brief.
Assignment = tuple[SubagentSpec, str]


def _fallback_assignments(
    team: tuple[SubagentSpec, ...], prompt: str
) -> list[Assignment]:
    """Every team member gets the raw prompt — the pipeline never stalls."""
    return [(member, prompt) for member in team]


def _parse_assignments(
    proposed: list[PlanAssignment], team: tuple[SubagentSpec, ...], prompt: str
) -> list[Assignment]:
    """Map LLM assignments onto the fixed team, in deterministic team order.

    Unknown member ids are dropped; duplicate assignments keep the first
    brief. An empty result falls back to the whole team with the raw prompt.
    """
    briefs: dict[str, str] = {}
    for item in proposed:
        member_id = item.member.strip()
        brief = item.brief.strip()
        if member_id and brief and member_id not in briefs:
            briefs[member_id] = brief
    assignments = [
        (member, briefs[member.id]) for member in team if member.id in briefs
    ]
    return assignments or _fallback_assignments(team, prompt)


async def _plan(ctx: AgentContext, domain: str, prompt: str, *, allow_clarify: bool):
    """Ask the Main Agent LLM to brief its team, or a clarifying question (HITL).

    Returns ``("assignments", list[Assignment])`` or ``("question", str)``.
    """
    info = get_domain_info(domain)
    clarify_rule = MAIN_AGENT_CLARIFY_RULE if allow_clarify else ""
    team_lines = "\n".join(f"- {member.id}: {member.role}" for member in info.team)
    system = MAIN_AGENT_SYSTEM.format(
        domain=domain,
        expertise=info.expertise,
        team=team_lines,
        methodology=format_optional_block("How this domain works:", info.methodology),
        planning_example=format_optional_block("Example:", info.planning_example),
        clarify_rule=clarify_rule,
        memory_context=format_memory_block(ctx.memory_context),
    )
    messages = [
        ChatMessage("system", with_current_date(system)),
        ChatMessage("user", prompt),
    ]
    try:
        response = await ctx.adapter.chat(
            messages, temperature=0.2, max_tokens=PLAN_MAX_TOKENS
        )
        plan = PlanResult.model_validate(extract_json(response.content))
    except (LLMError, ValueError):
        return "assignments", _fallback_assignments(info.team, prompt)

    question = plan.question.strip()
    if allow_clarify and question:
        return "question", question
    return "assignments", _parse_assignments(plan.assignments, info.team, prompt)


async def _assign(ctx: AgentContext, domain: str, prompt: str) -> list[Assignment]:
    """Brief the team, optionally asking the user one clarifying question first."""
    can_ask = ctx.allow_questions and ctx.ask_user is not None
    kind, value = await _plan(ctx, domain, prompt, allow_clarify=can_ask)

    if kind == "question" and ctx.ask_user is not None:
        await ctx.emit(
            EventType.AGENT_QUESTION,
            {"role": AgentRole.MAIN.value, "question": value},
        )
        answer = await ctx.ask_user(value)
        # Re-plan once with the answer folded in; no further clarifications.
        enriched = f"{prompt}\n\nClarification — Q: {value}\nA: {answer}"
        _, value = await _plan(ctx, domain, enriched, allow_clarify=False)

    assignments = (
        value
        if isinstance(value, list)
        else _fallback_assignments(get_domain_info(domain).team, prompt)
    )
    # Loop protection: never exceed the configured iteration budget or the
    # hard cap, whichever is lower (teams are defined within the cap).
    return assignments[: min(ctx.max_iterations, MAX_SUBTASKS)]


async def _run_with_review(
    ctx: AgentContext,
    *,
    domain: str,
    member: SubagentSpec,
    brief: str,
    index: int,
    reviewer_enabled: bool,
) -> SubagentResult:
    """Run a brief, optionally looping with the reviewer up to the limit."""
    review_hints: list[str] = []
    result = await subagent_worker.run_subtask(
        ctx, domain=domain, member=member, brief=brief, index=index
    )
    if not reviewer_enabled:
        return result

    iterations = 0
    while iterations < ctx.max_review_iterations:
        if result.status == SubagentStatus.ERROR:
            break
        feedback = await reviewer_agent.review(ctx, subtask=brief, result=result)
        if feedback.approved:
            break
        review_hints = feedback.retry_hints or feedback.issues
        iterations += 1
        result = await subagent_worker.run_subtask(
            ctx,
            domain=domain,
            member=member,
            brief=brief,
            index=index,
            review_hints=review_hints,
        )
    result.metadata["review_iterations"] = iterations
    return result


async def _synthesize(
    ctx: AgentContext, domain: str, prompt: str, outputs: list[str]
) -> str:
    """Combine subtask outputs into a single, domain-shaped final answer."""
    if len(outputs) == 1:
        return outputs[0]
    joined = "\n\n".join(f"- {o}" for o in outputs)
    system = SYNTHESIS_SYSTEM.format(
        domain=domain,
        output_format=format_optional_block(
            "Structure the final answer as:", get_domain_info(domain).output_format
        ),
    )
    messages = [
        ChatMessage("system", with_current_date(system)),
        ChatMessage("user", f"Original task:\n{prompt}\n\nSubtask results:\n{joined}"),
    ]
    try:
        response = await ctx.adapter.chat(
            messages, temperature=0.3, max_tokens=SYNTHESIS_MAX_TOKENS
        )
        return response.content
    except LLMError:
        return joined


async def run(
    ctx: AgentContext,
    *,
    domain: str,
    prompt: str,
    reviewer_enabled: bool,
) -> dict[str, Any]:
    """Execute the full main-agent workflow and return a result payload."""
    await ctx.emit(
        EventType.NODE_UPDATE,
        {"role": AgentRole.MAIN.value, "state": "running", "domain": domain},
    )
    assignments = await _assign(ctx, domain, prompt)
    await ctx.emit(
        EventType.AGENT_MESSAGE,
        {
            "role": AgentRole.MAIN.value,
            # Kept for backward compatibility with older event consumers.
            "subtasks": [brief for _, brief in assignments],
            "assignments": [
                {"member_id": member.id, "member_name": member.name, "brief": brief}
                for member, brief in assignments
            ],
        },
    )

    results: list[SubagentResult] = []
    for index, (member, brief) in enumerate(assignments):
        result = await _run_with_review(
            ctx,
            domain=domain,
            member=member,
            brief=brief,
            index=index,
            reviewer_enabled=reviewer_enabled,
        )
        results.append(result)

    outputs = [
        str(r.data.get("output", r.data.get("error", "")))
        for r in results
        if r.status != SubagentStatus.ERROR
    ] or ["No successful subtask output."]

    final_answer = await _synthesize(ctx, domain, prompt, outputs)
    total_tokens = sum(int(r.metadata.get("tokens_used", 0)) for r in results)

    await ctx.emit(
        EventType.NODE_UPDATE, {"role": AgentRole.MAIN.value, "state": "done"}
    )
    return {
        "domain": domain,
        "answer": final_answer,
        "subtasks": [r.to_dict() for r in results],
        "metadata": {"total_tokens": total_tokens, "subtask_count": len(results)},
    }
