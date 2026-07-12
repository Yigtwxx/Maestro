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
import logging
from dataclasses import dataclass
from typing import Any

from app.agents import budget
from app.agents import reviewer as reviewer_agent
from app.agents import subagent as subagent_worker
from app.agents.base import (
    AgentContext,
    SubagentResult,
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
from app.agents.structured import structured_call
from app.core.constants import (
    MAX_SUBTASKS,
    MAX_SUBTASKS_BY_COMPLEXITY,
    PLAN_MAX_TOKENS,
    STREAM_DELTA_FLUSH_CHARS,
    SYNTHESIS_MAX_TOKENS,
    UPSTREAM_OUTPUT_MAX_CHARS,
    AgentRole,
    EventType,
    SubagentStatus,
)
from app.services.llm_service import ChatMessage, LLMError

logger = logging.getLogger(__name__)


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
    info = ctx.domain_info or get_domain_info(domain)
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
    # One retry with validation feedback: local models fail strict-JSON planning
    # often enough that a second attempt is cheap insurance before the
    # role-scoped fallback.
    try:
        plan = await structured_call(
            ctx.role_adapter("main"),
            messages,
            PlanResult,
            temperature=0.2,
            max_tokens=PLAN_MAX_TOKENS,
            max_attempts=2,
        )
    except (LLMError, ValueError):
        logger.warning("planning failed twice; using role-scoped fallback briefs")
        return "assignments", _fallback_assignments(info.team)

    question = plan.question.strip()
    if allow_clarify and question:
        return "question", question
    return "assignments", _parse_assignments(plan.assignments, info.team)


async def _assign(
    ctx: AgentContext, domain: str, prompt: str, *, max_subtasks: int = MAX_SUBTASKS
) -> list[Assignment]:
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
        else _fallback_assignments((ctx.domain_info or get_domain_info(domain)).team)
    )
    # Loop protection + effort scaling: never exceed the iteration budget or the
    # complexity-scaled cap, whichever is lower. Deps are re-sanitized so nothing
    # references a member the cap removed.
    limit = min(ctx.max_iterations, max_subtasks, MAX_SUBTASKS)
    return _sanitize_depends_on(assignments[:limit])


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


def _skipped_over_budget(assignment: Assignment) -> SubagentResult:
    """A subagent skipped because the task ran out of budget (surfaced as a
    warning by the partial-failure path, not a hard error)."""
    return SubagentResult(
        status=SubagentStatus.ERROR,
        data={
            "error": "Task token budget exhausted; subtask skipped.",
            "subtask": assignment.brief,
            "member": assignment.member.id,
        },
    )


def _teammate_note(assignment: Assignment, result: SubagentResult) -> str:
    """Text a dependent member sees for this teammate's finished work.

    A large deliverable is handed on as its concise ``summary`` (Backend v2
    §4.6) so a downstream member's prompt is not flooded; short outputs pass
    through in full.
    """
    if result.status == SubagentStatus.ERROR:
        return f"(teammate {assignment.member.name} failed; work without their input)"
    output = str(result.data.get("output", ""))
    if len(output) > UPSTREAM_OUTPUT_MAX_CHARS:
        return str(result.data.get("summary", "")) or output
    return output


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
                logger.warning(
                    "subtask crashed; sibling subtasks continue",
                    exc_info=True,
                    extra={
                        "subtask_index": index,
                        "member": assignment.member.id,
                    },
                )
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
        # Budget guard (D19): once the task's token cap is crossed, skip every
        # remaining member instead of launching another wave. Skipped members
        # surface as warnings and the engine goes straight to synthesis.
        if budget.budget_exceeded(ctx):
            logger.warning(
                "task token budget exhausted; skipping %d remaining subtask(s)",
                len(remaining),
            )
            for index, assignment in remaining:
                results[index] = _skipped_over_budget(assignment)
            break
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
    ctx: AgentContext,
    domain: str,
    prompt: str,
    outputs: list[tuple[str, str]],
    known_gaps: list[str] | None = None,
) -> str:
    """Combine labeled subtask outputs into a single, domain-shaped answer.

    Each output is ``(member_name, text)`` — authorship labels measurably help
    the synthesis model weigh and merge multi-member results. ``known_gaps`` names
    subtasks that failed so the answer acknowledges holes instead of papering
    over them (D7).
    """
    if len(outputs) == 1:
        return outputs[0][1]
    joined = "\n\n".join(f"### {name}\n{text}" for name, text in outputs)
    system = SYNTHESIS_SYSTEM.format(
        domain=domain,
        output_format=format_optional_block(
            "Structure the final answer as:",
            (ctx.domain_info or get_domain_info(domain)).output_format,
        ),
    )
    gaps_block = ""
    if known_gaps:
        listed = "\n".join(f"- {gap}" for gap in known_gaps)
        gaps_block = (
            "\n\nKnown gaps (these subtasks did not complete — acknowledge their "
            f"absence, do not fabricate their results):\n{listed}"
        )
    messages = [
        ChatMessage("system", with_current_date(system)),
        ChatMessage(
            "user",
            f"Original task:\n{prompt}\n\nSubtask results:\n{joined}{gaps_block}",
        ),
    ]
    try:
        # Stream the final answer so the UI fills in token-by-token; the default
        # chat_stream degrades a non-streaming provider to a single delta, so this
        # is safe for every adapter and leaves token accounting unchanged.
        chunks: list[str] = []
        buffer = ""
        async for event in ctx.role_adapter("synthesis").chat_stream(
            messages, temperature=0.3, max_tokens=SYNTHESIS_MAX_TOKENS
        ):
            if event.kind == "text_delta" and event.text:
                chunks.append(event.text)
                buffer += event.text
                if len(buffer) >= STREAM_DELTA_FLUSH_CHARS:
                    await ctx.emit(
                        EventType.AGENT_DELTA,
                        {"role": AgentRole.MAIN.value, "text": buffer},
                    )
                    buffer = ""
        if buffer:
            await ctx.emit(
                EventType.AGENT_DELTA, {"role": AgentRole.MAIN.value, "text": buffer}
            )
        return "".join(chunks) or joined
    except LLMError:
        logger.warning(
            "synthesis failed; returning joined subtask outputs", exc_info=True
        )
        return joined


async def run(
    ctx: AgentContext,
    *,
    domain: str,
    prompt: str,
    reviewer_enabled: bool,
    complexity: str = "complex",
) -> dict[str, Any]:
    """Execute the full main-agent workflow and return a result payload.

    ``complexity`` scales the effort (Backend v2 §4.6/D15): the team size is
    capped per tier and a ``simple`` task skips the reviewer entirely. The
    default is ``complex`` (no reduction) so a direct caller or a user who
    picked the domain explicitly still gets the full team — only an actual
    orchestrator classification narrows the effort.
    """
    max_subtasks = MAX_SUBTASKS_BY_COMPLEXITY.get(complexity, MAX_SUBTASKS)
    if complexity == "simple":
        reviewer_enabled = False
    await ctx.emit(
        EventType.NODE_UPDATE,
        {"role": AgentRole.MAIN.value, "state": "running", "domain": domain},
    )
    assignments = await _assign(ctx, domain, prompt, max_subtasks=max_subtasks)
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

    per_subtask = list(zip(assignments, results, strict=True))
    successful = [
        (a.member.name, str(r.data.get("output", "")))
        for a, r in per_subtask
        if r.status != SubagentStatus.ERROR
    ]
    # Failed members are surfaced (not silently dropped): the task layer maps a
    # partial failure to ``completed_with_warnings`` and the synthesis prompt
    # acknowledges the gaps (D7).
    failed_subtasks = [
        {
            "member_id": a.member.id,
            "member_name": a.member.name,
            "brief": a.brief,
            "error": str(r.data.get("error", "")).strip(),
        }
        for a, r in per_subtask
        if r.status == SubagentStatus.ERROR
    ]
    # Every subtask erroring (e.g. the chat model is unreachable) is a task
    # failure, not a success with an empty answer -- the caller marks the task
    # FAILED on this signal. Skip the synthesis call: with no output to merge it
    # would only waste another (doomed) LLM round-trip.
    all_failed = not successful
    failure_reason: str | None = None
    if all_failed:
        final_answer = "No successful subtask output."
        # Carry the real cause (e.g. "gemini chat failed: HTTP 404 ...") up to the
        # task layer so the terminal log and the UI error say why, not just that
        # everything failed. Subtasks share one adapter, so the first is
        # representative.
        reasons = [f["error"] for f in failed_subtasks if f["error"]]
        if reasons:
            failure_reason = reasons[0]
    else:
        known_gaps = [f"{f['member_name']}: {f['brief']}" for f in failed_subtasks]
        final_answer = await _synthesize(
            ctx, domain, prompt, successful, known_gaps=known_gaps
        )

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
        "failed_subtasks": failed_subtasks,
        "failure_reason": failure_reason,
    }
