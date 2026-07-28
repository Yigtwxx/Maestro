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
from app.agents import tools as tool_directives
from app.agents.base import (
    AgentContext,
    SubagentResult,
    format_memory_block,
    format_optional_block,
    truncate_text,
    with_current_date,
)
from app.agents.domains.base import DomainInfo
from app.agents.prompts import (
    FALLBACK_BRIEF_TEMPLATE,
    GATEKEEPER_SYSTEM,
    MAIN_AGENT_CLARIFY_RULE,
    MAIN_AGENT_SYSTEM,
    MAIN_AGENT_TOOLS_RULE,
    MAIN_DISCOVERY_SYSTEM,
    SYNTHESIS_SYSTEM,
)
from app.agents.registry import SubagentSpec, get_domain_info
from app.agents.schemas import GrantDecision, PlanAssignment, PlanResult
from app.agents.structured import structured_call
from app.core.config import settings
from app.core.constants import (
    EXECUTABLE_TOOL_IDS,
    MAX_SUBTASKS,
    MAX_SUBTASKS_BY_COMPLEXITY,
    OBJECTIVE_MAX_CHARS,
    ORIGINAL_REQUEST_CLOSE,
    ORIGINAL_REQUEST_OPEN,
    PLAN_MAX_TOKENS,
    RAG_TOOL_IDS,
    STREAM_DELTA_FLUSH_CHARS,
    SYNTHESIS_MAX_TOKENS,
    SYNTHESIS_MEMBER_OUTPUT_MAX_CHARS,
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
    # Position in the planner's own list. Assignments execute in team order, so
    # that ordering is lost by the time the effort cap truncates — and cutting by
    # team order keeps whichever member happens to be listed first in the domain
    # module, which is the preparatory role almost everywhere. Kept so the cap
    # can drop the members the planner cared least about instead.
    rank: int = 0
    # Tools the Main Agent granted this member, or ``None`` when it named none.
    # ``None`` = unassigned: the member gets the full domain-global tool set,
    # preserving the pre-assignment behaviour byte-for-byte. A frozenset — even
    # an empty one — is an explicit grant that ``resolve_enabled_tools``
    # intersects with the domain/switch/credential universe, so it can only ever
    # narrow what the member may use, never widen it.
    assigned_tools: frozenset[str] | None = None


def _fallback_assignments(
    team: tuple[SubagentSpec, ...], prompt: str, deliverable: str = ""
) -> list[Assignment]:
    """Every member gets a role-scoped brief — the pipeline never stalls.

    The user's request is carried into the brief as delimited context so a member
    still knows what the task is. It is never the member's own instruction: the
    role sentence after the delimiters is what it is told to execute. Relying on
    the member to fetch the request itself via ``view_original_request`` was the
    previous design and it failed on small models, which simply never issued the
    directive and answered their bare role description instead.

    Members chain in team order (each depends on all previous ones) so teams laid
    out as a pipeline — e.g. software's architect → coder → tester — still hand
    their work forward even without an explicit plan.

    ``deliverable`` ranks first. There is no planner here to order the list, so
    every assignment used to share ``rank = 0`` and the effort cap's stable sort
    degraded to team-order slicing — keeping the preparatory members that lead
    almost every roster and dropping the one whose output *is* the answer. That
    is precisely the failure ``Assignment.rank`` exists to prevent, and it bites
    hardest here: this path runs when planning already failed.
    """
    request = truncate_text(prompt.strip(), OBJECTIVE_MAX_CHARS)
    ordered = [member.id for member in team if member.id != deliverable]
    ranks = {member_id: index + 1 for index, member_id in enumerate(ordered)}
    ranks[deliverable] = 0
    return [
        Assignment(
            member=member,
            brief=FALLBACK_BRIEF_TEMPLATE.format(
                open=ORIGINAL_REQUEST_OPEN,
                request=request,
                close=ORIGINAL_REQUEST_CLOSE,
                role=member.role,
            ),
            depends_on=tuple(previous.id for previous in team[:index]),
            rank=ranks[member.id],
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
                member=assignment.member,
                brief=assignment.brief,
                depends_on=deps,
                # Carried, not defaulted: this runs before the effort cap, and a
                # reset rank would put every assignment back in team order —
                # silently restoring the behaviour the rank exists to replace.
                rank=assignment.rank,
                # Carried too: this sanitizer runs last in ``_assign``, so a
                # dropped grant would silently revert every member to the
                # domain-global tool set.
                assigned_tools=assignment.assigned_tools,
            )
        )
        seen.add(assignment.member.id)
    return sanitized


def _parse_assignments(
    proposed: list[PlanAssignment],
    team: tuple[SubagentSpec, ...],
    prompt: str,
    deliverable: str = "",
) -> list[Assignment]:
    """Map LLM assignments onto the fixed team, in deterministic team order.

    Unknown member ids are dropped; duplicate assignments keep the first
    brief. Dependencies are sanitized to earlier assigned members only. An
    empty result falls back to the whole team with role-scoped briefs.
    """
    briefs: dict[str, str] = {}
    depends: dict[str, tuple[str, ...]] = {}
    ranks: dict[str, int] = {}
    tools_by_id: dict[str, frozenset[str]] = {}
    for item in proposed:
        member_id = item.member.strip()
        brief = item.brief.strip()
        if member_id and brief and member_id not in briefs:
            briefs[member_id] = brief
            depends[member_id] = tuple(
                dep.strip() for dep in item.depends_on if dep.strip()
            )
            ranks[member_id] = len(ranks)
            # Validity is not checked here — resolve_enabled_tools intersects
            # against the domain universe, so an unknown id is simply dropped.
            tools_by_id[member_id] = frozenset(
                tool.strip() for tool in item.tools if tool.strip()
            )
    assignments = [
        Assignment(
            member=member,
            brief=briefs[member.id],
            depends_on=depends[member.id],
            rank=ranks[member.id],
            # An empty list means the planner named no tools for this member,
            # which is unassigned (domain-global), not "no tools" — this is what
            # keeps every existing tools-less plan byte-identical.
            assigned_tools=tools_by_id[member.id] or None,
        )
        for member in team
        if member.id in briefs
    ]
    if not assignments:
        return _fallback_assignments(team, prompt, deliverable)
    return _sanitize_depends_on(assignments)


async def _plan(
    ctx: AgentContext,
    domain: str,
    prompt: str,
    *,
    allow_clarify: bool,
    max_members: int = MAX_SUBTASKS,
):
    """Ask the Main Agent LLM to brief its team, or a clarifying question (HITL).

    ``max_members`` is the effort cap the caller will enforce anyway. Telling the
    planner about it lets it choose which members matter; without it the planner
    briefs the whole team and the cap decides for it, by list position.

    Returns ``("assignments", list[Assignment])`` or ``("question", str)``.
    """
    info = ctx.domain_info or get_domain_info(domain)
    clarify_rule = MAIN_AGENT_CLARIFY_RULE if allow_clarify else ""
    team_lines = "\n".join(f"- {member.id}: {member.role}" for member in info.team)
    # Only the executable tools are worth naming to the planner: the native ones
    # (summarize, file_read) are performed in the member's own reasoning and are
    # never gated by an assignment, so listing them would only invite noise.
    assignable = sorted(set(info.tools) & EXECUTABLE_TOOL_IDS)
    tools_rule = (
        MAIN_AGENT_TOOLS_RULE.format(tools=", ".join(assignable)) if assignable else ""
    )
    system = MAIN_AGENT_SYSTEM.format(
        domain=domain,
        expertise=info.expertise,
        team=team_lines,
        methodology=format_optional_block("How this domain works:", info.methodology),
        planning_example=format_optional_block("Example:", info.planning_example),
        clarify_rule=clarify_rule,
        tools_rule=tools_rule,
        memory_context=format_memory_block(ctx.memory_context),
        max_members=max_members,
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
        await ctx.emit(
            EventType.AGENT_WARNING,
            {
                "role": AgentRole.MAIN.value,
                "kind": "degraded",
                "message": (
                    "Planning failed; each member fell back to its default brief."
                ),
            },
        )
        return "assignments", _fallback_assignments(
            info.team, prompt, info.deliverable_member
        )

    question = plan.question.strip()
    if allow_clarify and question:
        return "question", question
    return "assignments", _parse_assignments(
        plan.assignments, info.team, prompt, info.deliverable_member
    )


async def _assign(
    ctx: AgentContext, domain: str, prompt: str, *, max_subtasks: int = MAX_SUBTASKS
) -> list[Assignment]:
    """Brief the team, optionally asking the user one clarifying question first."""
    can_ask = ctx.allow_questions and ctx.ask_user is not None
    limit = min(ctx.max_iterations, max_subtasks, MAX_SUBTASKS)
    kind, value = await _plan(
        ctx, domain, prompt, allow_clarify=can_ask, max_members=limit
    )

    if kind == "question" and ctx.ask_user is not None:
        await ctx.emit(
            EventType.AGENT_QUESTION,
            {"role": AgentRole.MAIN.value, "question": value},
        )
        answer = await ctx.ask_user(value)
        # Re-plan once with the answer folded in; no further clarifications.
        enriched = f"{prompt}\n\nClarification — Q: {value}\nA: {answer}"
        _, value = await _plan(
            ctx, domain, enriched, allow_clarify=False, max_members=limit
        )

    info = ctx.domain_info or get_domain_info(domain)
    assignments = (
        value
        if isinstance(value, list)
        else _fallback_assignments(info.team, prompt, info.deliverable_member)
    )
    # Loop protection + effort scaling: never exceed the iteration budget or the
    # complexity-scaled cap, whichever is lower. Deps are re-sanitized so nothing
    # references a member the cap removed.
    #
    # Which members the cap drops is decided by the planner's ordering, not the
    # team's. Slicing the team-ordered list kept whichever member the domain
    # module happens to declare first, and that is the preparatory role in almost
    # every domain — general's researcher, research's collector, content's
    # planner, software's architect. A "simple" task caps at one member, so it
    # reliably returned working notes and never the deliverable the user asked
    # for. The surviving members are then put back in team order, because that is
    # what makes the dependency sanitisation below meaningful.
    #
    # The cap must also never drop the member whose output *is* the answer. A
    # planner that simply enumerates its roster in team order — which small
    # models routinely do — puts the deliverable member last, because that is
    # where a domain declares it. Truncating by that ordering left seo's
    # `standard` plan as four specialist reports with no strategist to merge
    # them: every input to the answer, and no answer. So the deliverable buys
    # back the least important surviving slot.
    if len(assignments) > limit:
        ordered = sorted(assignments, key=lambda a: a.rank)
        kept = [a.member.id for a in ordered[:limit]]
        target = info.deliverable_member
        if (
            target
            and target not in kept
            and any(a.member.id == target for a in ordered)
        ):
            kept[-1] = target
        keep = set(kept)
        assignments = [a for a in assignments if a.member.id in keep]
    # Keyed on the plan's actual size, not on the cap: a planner given a budget
    # of three that briefs only one member has still produced a single-member
    # plan, and that member's output is still the entire answer. Observed on
    # legal, which came back as one `researcher` under a standard budget.
    if len(assignments) == 1:
        assignments = [_as_deliverable(assignments[0], info)]
    # After the swap above, never before it. A lone member is better *retargeted*
    # than joined: the swap hands the deliverable the planner's own task-specific
    # brief, where appending would give it a generic role-scoped one and spend a
    # second member to say the same thing.
    assignments = _ensure_deliverable(assignments, info, prompt, limit)
    return _sanitize_depends_on(assignments)


def _ensure_deliverable(
    assignments: list[Assignment], info: DomainInfo, prompt: str, limit: int
) -> list[Assignment]:
    """Add the answer-producing member when the plan simply left it out.

    Truncation is not the only way to lose it. An `opensource` plan came back as
    three members — profiler, health, risk — with no `verdict` at all, because
    the planner never named it. Nothing was over the cap, so the promotion above
    never fired, and the run produced a report of risks with no adopt/avoid call
    and no data-coverage ledger: sections 5 and 6 of the domain's own output
    format, both missing. The one-member rule below could not help either, since
    three is not one.

    Appending is what the raised cap bought. It goes last with a dependency on
    everything already planned — which is what a deliverable is. Its brief is
    role-scoped from the original request, the same construction
    ``_fallback_assignments`` uses, because the planner wrote no brief for it.

    A plan that fills the budget exactly and still names no deliverable pays for
    it by dropping its least important member, so the effort cap is never
    exceeded either way.
    """
    target = info.deliverable_member
    if not target:
        return assignments
    if any(assignment.member.id == target for assignment in assignments):
        return assignments
    member = next((spec for spec in info.team if spec.id == target), None)
    if member is None:  # pragma: no cover - guarded by test_domain_catalog
        return assignments
    kept = assignments
    if len(kept) >= limit:
        weakest = max(kept, key=lambda assignment: assignment.rank)
        kept = [a for a in kept if a is not weakest]
    return [
        *kept,
        Assignment(
            member=member,
            brief=FALLBACK_BRIEF_TEMPLATE.format(
                open=ORIGINAL_REQUEST_OPEN,
                request=truncate_text(prompt.strip(), OBJECTIVE_MAX_CHARS),
                close=ORIGINAL_REQUEST_CLOSE,
                role=member.role,
            ),
            depends_on=tuple(assignment.member.id for assignment in kept),
            # Ahead of every planned member: the truncation above has already
            # run, so this only matters if something re-sorts later, and the
            # deliverable is never the right thing to drop.
            rank=-1,
        ),
    ]


def _as_deliverable(assignment: Assignment, info: DomainInfo) -> Assignment:
    """Point a lone assignment at the member that produces the answer.

    A one-member plan is the whole answer, so it has to come from the member
    whose output the user can read. The planner kept choosing the research
    member instead — through three successive prompt rules asking it not to —
    and the result was a search plan for "how long should a title tag be" and a
    "Key facts / Assumptions / Open questions" digest for "why do batteries wear
    out". Both were the right subject matter in the wrong shape.

    The brief is kept as written: it describes the task, and the deliverable
    member's own instructions are what turn it into prose rather than notes.
    Domains that leave ``deliverable_member`` empty keep the planner's choice.
    """
    target = info.deliverable_member
    if not target or assignment.member.id == target:
        return assignment
    member = next((m for m in info.team if m.id == target), None)
    if member is None:  # pragma: no cover - guarded by test_domain_catalog
        return assignment
    return Assignment(
        member=member,
        brief=assignment.brief,
        depends_on=(),
        rank=assignment.rank,
    )


async def _discover(ctx: AgentContext, domain: str, prompt: str) -> list[str]:
    """Read-only RAG discovery over the user's own data before planning (Phase C).

    Strictly whitelisted to the RAG tools and bounded by ``max_discovery_calls``,
    so no external or action tool can ever run at the main tier. Returns short
    context notes to fold into the planning prompt. A no-op without a user id,
    with the switch off, or when the domain grants no RAG tool. A lookup failure
    degrades to planning without discovery — it must never fail the task.
    """
    if ctx.user_id is None or not settings.main_agent_discovery_enabled:
        return []
    # Intersect with the whitelist defensively: even if resolve_enabled_tools
    # ever returned more, only the RAG tools can run in discovery.
    available = (
        await tool_directives.resolve_enabled_tools(
            ctx.domain_info or domain,
            credentials=ctx.service_credentials,
            assigned=RAG_TOOL_IDS,
        )
    ) & RAG_TOOL_IDS
    if not available:
        return []
    specs = tool_directives.specs_for(
        available, ctx.service_credentials, user_id=ctx.user_id
    )
    tool_lines = "\n".join(
        line
        for action in sorted(specs)
        if (
            line := tool_directives.rule_line_for(
                action, specs[action], ctx.max_discovery_calls
            )
        )
    )
    system = MAIN_DISCOVERY_SYSTEM.format(
        prompt=truncate_text(prompt.strip(), OBJECTIVE_MAX_CHARS),
        tool_lines=tool_lines,
    )
    messages = [
        ChatMessage("system", with_current_date(system)),
        ChatMessage("user", prompt),
    ]
    enabled = frozenset(specs)
    notes: list[str] = []
    for _ in range(max(0, ctx.max_discovery_calls)):
        try:
            response = await ctx.role_adapter("main").chat(
                messages, temperature=0.2, max_tokens=PLAN_MAX_TOKENS
            )
        except LLMError:
            logger.warning("discovery lookup failed; planning without it")
            break
        directive = tool_directives.parse_directive(response.content, enabled)
        if directive is None:  # the model replied DONE (or anything non-directive)
            break
        feedback = await specs[directive.action].executor(directive)
        notes.append(feedback)
        messages.append(ChatMessage("assistant", response.content))
        messages.append(ChatMessage("user", feedback))
    return notes


async def gatekeeper_review(
    ctx: AgentContext,
    *,
    domain: str,
    member: SubagentSpec,
    requested_tool: str,
    justification: str,
    brief: str,
) -> GrantDecision:
    """Decide, as the Main Agent, whether to grant a subagent's requested tool.

    This is the autonomous, agent-to-agent side of the ``request_tool``
    escalation (Phase B), distinct from the §8/§12 human-in-the-loop channel: no
    task pause, just one Main-Agent-persona LLM call. The member's brief and
    justification are delimited untrusted data — model text the member authored,
    never instructions. Fails safe to a denial on any provider or validation
    error, so an escalation can never *widen* access by crashing.
    """
    system = GATEKEEPER_SYSTEM.format(
        member=member.id,
        domain=domain,
        tool=requested_tool,
        brief_open="<brief>",
        brief=truncate_text(brief.strip(), OBJECTIVE_MAX_CHARS),
        brief_close="</brief>",
        just_open="<justification>",
        justification=truncate_text(justification.strip(), OBJECTIVE_MAX_CHARS),
        just_close="</justification>",
    )
    messages = [
        ChatMessage("system", with_current_date(system)),
        ChatMessage("user", f"Grant the {requested_tool} tool to {member.id}?"),
    ]
    try:
        return await structured_call(
            ctx.role_adapter("main"),
            messages,
            GrantDecision,
            temperature=0.1,
            max_attempts=2,
        )
    except (LLMError, ValueError):
        logger.warning("gatekeeper review failed; denying grant of %s", requested_tool)
        return GrantDecision(grant=False, reason="Gatekeeper unavailable.")


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
    assigned_tools: frozenset[str] | None = None,
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
        assigned_tools=assigned_tools,
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
            assigned_tools=assigned_tools,
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
                    assigned_tools=assignment.assigned_tools,
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
                # The subagent's own error path never ran, so nothing closed its
                # node. Emit here or the card hangs mid-run (see subagent.py).
                await ctx.emit(
                    EventType.NODE_UPDATE,
                    {
                        "role": AgentRole.SUBAGENT.value,
                        "index": index,
                        "state": "error",
                        "member": assignment.member.name,
                        "member_id": assignment.member.id,
                        "error": str(exc),
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
    if len(outputs) == 1 and not known_gaps:
        # A genuinely single-member plan (every "simple" task) needs no merge, and
        # forcing the domain's output_format onto one member's deliverable makes
        # the answer worse, not better: that format describes what the whole team
        # produces, so a lone member would be pushed to emit — and therefore to
        # invent — sections it never had the data for. The member's own
        # output_format already shaped this text, and GROUNDING_POLICY already put
        # the uncertainty markers and inline "Not found:" lines in it.
        #
        # ``known_gaps`` is the exception, and it is why this is not a bare
        # ``len(outputs) == 1``. One surviving output with failed siblings is a
        # partial failure: skipping synthesis there returned that member's answer
        # with no mention of what was missing, while the task was reported as
        # completed_with_warnings. The answer contradicted its own status.
        return outputs[0][1]
    # Capped per member, not in total: the synthesis prompt is the one place the
    # whole team's work meets, so it grows with team size while the model's
    # context does not. Ollama truncates an over-length prompt from the *front*,
    # which drops the system prompt — synthesis would then merge outputs with no
    # idea what shape the answer should take. Trimming the tail of one long
    # member's text is the far cheaper loss.
    joined = "\n\n".join(
        f"### {name}\n{truncate_text(text, SYNTHESIS_MEMBER_OUTPUT_MAX_CHARS)}"
        for name, text in outputs
    )
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
        await ctx.emit(
            EventType.AGENT_WARNING,
            {
                "role": AgentRole.MAIN.value,
                "kind": "degraded",
                "message": (
                    "Synthesis failed; the answer is the subtask outputs unmerged."
                ),
            },
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
    # Read-only discovery over the user's own data (Phase C): its findings join
    # the shared memory_context so planning — and the subagent waves that follow —
    # are grounded in what the user actually has.
    discovery_notes = await _discover(ctx, domain, prompt)
    if discovery_notes:
        ctx.memory_context = [*ctx.memory_context, *discovery_notes]
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
