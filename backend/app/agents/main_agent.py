"""Main Agent: briefs its fixed domain team, coordinates subagents + optional
reviewer, then synthesizes the final answer (CLAUDE.md §2).

The team roster is fixed per domain (``registry.DOMAIN_CATALOG``): the LLM
only decides which members are relevant to the task and what brief each one
gets — it can never invent members. If briefing fails (after one retry),
every member runs with a role-scoped fallback brief and can fetch the
original request on demand, so the pipeline never stalls.

Loop protection: assignment count is capped by ``max_iterations`` and each
reviewer↔subagent retry loop by ``max_review_iterations`` (CLAUDE.md §9.2).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
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
    FALLBACK_BRIEF_TEMPLATE,
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


@dataclass(slots=True)
class Assignment:
    """One team member with its task-specific brief and dependencies.

    ``depends_on`` names earlier members (in final assignment order) whose
    outputs are injected into this member's prompt — the graph is acyclic by
    construction because forward and self references are dropped.
    """

    member: SubagentSpec
    brief: str
    depends_on: tuple[str, ...] = ()


def _fallback_assignments(team: tuple[SubagentSpec, ...]) -> list[Assignment]:
    """Every member gets a role-scoped brief — the pipeline never stalls.

    The raw user message is never used as a member's own instruction; each
    member is told to fetch it via the view_original_request directive and
    execute only its role's share. Members chain in team order (each depends
    on all previous ones) so teams laid out as a pipeline — e.g. software's
    architect → coder → tester — still hand their work forward even without
    an explicit plan.
    """
    return [
        Assignment(
            member=member,
            brief=FALLBACK_BRIEF_TEMPLATE.format(role=member.role),
            depends_on=tuple(previous.id for previous in team[:index]),
        )
        for index, member in enumerate(team)
    ]


def _sanitize_depends_on(assignments: list[Assignment]) -> list[Assignment]:
    """Keep only dependencies on members that appear *earlier* in the list.

    Unknown ids, self references, and forward references are dropped silently
    (fail-open): the member still runs, just without that upstream context.
    """
    seen: set[str] = set()
    sanitized: list[Assignment] = []
    for assignment in assignments:
        deps = tuple(dict.fromkeys(dep for dep in assignment.depends_on if dep in seen))
        sanitized.append(
            Assignment(
                member=assignment.member, brief=assignment.brief, depends_on=deps
            )
        )
        seen.add(assignment.member.id)
    return sanitized


def _parse_assignments(
    proposed: list[PlanAssignment], team: tuple[SubagentSpec, ...]
) -> list[Assignment]:
    """Map LLM assignments onto the fixed team, in deterministic team order.

    Unknown member ids are dropped; duplicate assignments keep the first
    brief. Dependencies are sanitized to earlier assigned members only. An
    empty result falls back to the whole team with role-scoped briefs.
    """
    briefs: dict[str, str] = {}
    depends: dict[str, tuple[str, ...]] = {}
    for item in proposed:
        member_id = item.member.strip()
        brief = item.brief.strip()
        if member_id and brief and member_id not in briefs:
            briefs[member_id] = brief
            depends[member_id] = tuple(
                dep.strip() for dep in item.depends_on if dep.strip()
            )
    assignments = [
        Assignment(
            member=member, brief=briefs[member.id], depends_on=depends[member.id]
        )
        for member in team
        if member.id in briefs
    ]
    if not assignments:
        return _fallback_assignments(team)
    return _sanitize_depends_on(assignments)


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
    plan: PlanResult | None = None
    # One retry: local models fail strict-JSON planning often enough that a
    # second attempt is cheap insurance before the role-scoped fallback.
    for _ in range(2):
        try:
            response = await ctx.adapter.chat(
                messages, temperature=0.2, max_tokens=PLAN_MAX_TOKENS
            )
            plan = PlanResult.model_validate(extract_json(response.content))
            break
        except (LLMError, ValueError):
            continue
    if plan is None:
        return "assignments", _fallback_assignments(info.team)

    question = plan.question.strip()
    if allow_clarify and question:
        return "question", question
    return "assignments", _parse_assignments(plan.assignments, info.team)


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
        else _fallback_assignments(get_domain_info(domain).team)
    )
    # Loop protection: never exceed the configured iteration budget or the
    # hard cap, whichever is lower (teams are defined within the cap). Deps
    # are re-sanitized so nothing references a member the cap removed.
    return _sanitize_depends_on(assignments[: min(ctx.max_iterations, MAX_SUBTASKS)])


async def _run_with_review(
    ctx: AgentContext,
    *,
    domain: str,
    member: SubagentSpec,
    brief: str,
    index: int,
    reviewer_enabled: bool,
    objective: str = "",
    upstream: list[tuple[str, str]] | None = None,
) -> SubagentResult:
    """Run a brief, optionally looping with the reviewer up to the limit."""
    review_hints: list[str] = []
    result = await subagent_worker.run_subtask(
        ctx,
        domain=domain,
        member=member,
        brief=brief,
        index=index,
        objective=objective,
        upstream=upstream,
    )
    if not reviewer_enabled:
        return result

    iterations = 0
    while iterations < ctx.max_review_iterations:
        if result.status == SubagentStatus.ERROR:
            break
        feedback = await reviewer_agent.review(
            ctx, domain=domain, subtask=brief, result=result, member=member, index=index
        )
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
            objective=objective,
            upstream=upstream,
        )
    result.metadata["review_iterations"] = iterations
    return result


def _teammate_note(assignment: Assignment, result: SubagentResult) -> str:
    """Text a dependent member sees for this teammate's finished work."""
    if result.status == SubagentStatus.ERROR:
        return f"(teammate {assignment.member.name} failed; work without their input)"
    return str(result.data.get("output", ""))


async def _run_assignments(
    ctx: AgentContext,
    *,
    domain: str,
    prompt: str,
    assignments: list[Assignment],
    reviewer_enabled: bool,
) -> list[SubagentResult]:
    """Execute assignments in dependency waves, independents in parallel.

    Members whose dependencies are all completed form a wave and run
    concurrently (bounded by ``ctx.max_parallel_subagents``); dependents wait
    for the next wave and receive their teammates' outputs. Results keep the
    original assignment order regardless of completion order.
    """
    semaphore = asyncio.Semaphore(max(1, ctx.max_parallel_subagents))
    names_by_id = {a.member.id: a.member.name for a in assignments}
    completed: dict[str, str] = {}
    results: dict[int, SubagentResult] = {}

    async def run_one(index: int, assignment: Assignment) -> None:
        # ``completed.get`` skips any dependency not yet finished (fail-open):
        # the member still runs, just without that upstream context.
        upstream = [
            (names_by_id[dep], completed[dep])
            for dep in assignment.depends_on
            if dep in completed
        ]
        async with semaphore:
            try:
                result = await _run_with_review(
                    ctx,
                    domain=domain,
                    member=assignment.member,
                    brief=assignment.brief,
                    index=index,
                    reviewer_enabled=reviewer_enabled,
                    objective=prompt,
                    upstream=upstream,
                )
            except Exception as exc:  # noqa: BLE001 — sibling subtasks must survive
                result = SubagentResult(
                    status=SubagentStatus.ERROR,
                    data={
                        "error": str(exc),
                        "subtask": assignment.brief,
                        "member": assignment.member.id,
                    },
                )
        results[index] = result
        completed[assignment.member.id] = _teammate_note(assignment, result)

    remaining = list(enumerate(assignments))
    while remaining:
        wave = [
            (index, a)
            for index, a in remaining
            if all(dep in completed for dep in a.depends_on)
        ]
        if not wave:
            # Deps only ever point at earlier members, so this cannot happen;
            # if it somehow does, run the rest sequentially (fail-open).
            wave = remaining[:1]
        await asyncio.gather(*(run_one(index, a) for index, a in wave))
        wave_indexes = {index for index, _ in wave}
        remaining = [(i, a) for i, a in remaining if i not in wave_indexes]

    return [results[index] for index in range(len(assignments))]


async def _synthesize(
    ctx: AgentContext, domain: str, prompt: str, outputs: list[tuple[str, str]]
) -> str:
    """Combine labeled subtask outputs into a single, domain-shaped answer.

    Each output is ``(member_name, text)`` — authorship labels measurably help
    the synthesis model weigh and merge multi-member results.
    """
    if len(outputs) == 1:
        return outputs[0][1]
    joined = "\n\n".join(f"### {name}\n{text}" for name, text in outputs)
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
            "subtasks": [a.brief for a in assignments],
            "assignments": [
                {
                    "member_id": a.member.id,
                    "member_name": a.member.name,
                    "brief": a.brief,
                    "depends_on": list(a.depends_on),
                }
                for a in assignments
            ],
        },
    )

    results = await _run_assignments(
        ctx,
        domain=domain,
        prompt=prompt,
        assignments=assignments,
        reviewer_enabled=reviewer_enabled,
    )

    successful = [
        (a.member.name, str(r.data.get("output", "")))
        for a, r in zip(assignments, results, strict=True)
        if r.status != SubagentStatus.ERROR
    ]
    # Every subtask erroring (e.g. the chat model is unreachable) is a task
    # failure, not a success with an empty answer -- the caller marks the task
    # FAILED on this signal. Skip the synthesis call: with no output to merge it
    # would only waste another (doomed) LLM round-trip.
    all_failed = not successful
    if all_failed:
        final_answer = "No successful subtask output."
    else:
        final_answer = await _synthesize(ctx, domain, prompt, successful)

    await ctx.emit(
        EventType.NODE_UPDATE, {"role": AgentRole.MAIN.value, "state": "done"}
    )
    # total_tokens is filled in by task_service from the TokenMeter: summing the
    # subagents here would miss routing, planning, synthesis and review calls.
    return {
        "domain": domain,
        "answer": final_answer,
        "subtasks": [r.to_dict() for r in results],
        "metadata": {"subtask_count": len(results)},
        "all_subtasks_failed": all_failed,
    }
