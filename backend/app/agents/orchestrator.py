"""Orchestrator: classifies the user prompt and routes to a domain.

Routing only — never produces the final work (CLAUDE.md §2).

Classification is **two-stage**: the prompt is placed in a ``DomainGroup``
first, then in one of the handful of domains inside that group. One flat call
over the whole catalog was fine at a dozen domains and stops being fine well
before forty — a small local model asked to pick one of forty near-synonymous
hint lines picks by surface wording, and the contrastive "NOT ..." clauses that
separate neighbouring domains only work when the neighbours are actually in
front of it. Splitting the decision keeps every classification down to a single
digit number of options, and the second call sees only genuinely adjacent
choices, which is where those clauses earn their keep.

The cost is one extra call. Both are ``temperature=0`` with a small token cap,
and neither carries the conversation, so the extra latency is the smaller half
of what one misroute costs: a misroute spends a whole task on the wrong team.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.agents.base import AgentContext, with_current_date
from app.agents.prompts import ORCHESTRATOR_DOMAIN_SYSTEM, ORCHESTRATOR_GROUP_SYSTEM
from app.agents.registry import (
    CUSTOM_DOMAIN_PREFIX,
    DEFAULT_DOMAIN,
    DOMAIN_GROUP_CATALOG,
    DomainGroup,
    domains_in_group,
    get_group_info,
    is_custom_domain,
)
from app.agents.schemas import GroupDecision, RouteDecision
from app.agents.structured import structured_call
from app.core.constants import (
    DEFAULT_TASK_COMPLEXITY,
    ROUTE_MAX_TOKENS,
    AgentRole,
    EventType,
)
from app.services.llm_service import ChatMessage, LLMError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RouteResult:
    """The orchestrator's decision: which domain, and how much effort to spend."""

    domain: str
    complexity: str = DEFAULT_TASK_COMPLEXITY
    group: str = ""


async def _degraded(ctx: AgentContext, message: str) -> None:
    """Emit the routing-degraded warning.

    WARNING rather than ERROR at the log level: this is expected degradation on
    a small model and must not flood Sentry.
    """
    await ctx.emit(
        EventType.AGENT_WARNING,
        {
            "role": AgentRole.ORCHESTRATOR.value,
            "kind": "degraded",
            "message": message,
        },
    )


async def _classify_group(
    ctx: AgentContext,
    prompt: str,
    custom_agents: Sequence[dict],
) -> tuple[str | None, str, str]:
    """Stage one: pick a group, or a custom agent directly.

    Returns ``(custom_selector_or_None, group_id, complexity)``. A custom agent
    short-circuits stage two — it is a one-member team of its own and there is
    nothing to narrow.
    """
    lines = [f"- {group.id}: {group.routing_hint}" for group in DOMAIN_GROUP_CATALOG]
    allowed_custom: set[str] = set()
    for agent in custom_agents:
        selector = f"{CUSTOM_DOMAIN_PREFIX}{agent['id']}"
        allowed_custom.add(selector)
        hint = agent.get("routing_hint") or agent.get("name") or "custom agent"
        lines.append(f"- {selector}: {hint}")

    system = with_current_date(
        ORCHESTRATOR_GROUP_SYSTEM.format(groups="\n".join(lines))
    )
    decision = await structured_call(
        ctx.role_adapter("orchestrator"),
        [ChatMessage("system", system), ChatMessage("user", prompt)],
        GroupDecision,
        temperature=0.0,
        max_tokens=ROUTE_MAX_TOKENS,
    )
    chosen = (decision.group or "").strip().lower()
    if is_custom_domain(chosen):
        # Only a custom agent the caller actually owns is honoured.
        if chosen in allowed_custom:
            return chosen, "", decision.complexity
        return None, get_group_info("").id, decision.complexity
    return None, get_group_info(chosen).id, decision.complexity


async def _classify_domain(ctx: AgentContext, prompt: str, group: DomainGroup) -> str:
    """Stage two: pick one domain from inside ``group``."""
    members = domains_in_group(group.id)
    if not members:  # pragma: no cover - a group with no domains fails a test
        return group.default_domain
    if len(members) == 1:
        return members[0].id

    lines = [f"- {entry.id}: {entry.routing_hint}" for entry in members]
    system = with_current_date(
        ORCHESTRATOR_DOMAIN_SYSTEM.format(
            group=group.name,
            group_description=group.description,
            domains="\n".join(lines),
        )
    )
    decision = await structured_call(
        ctx.role_adapter("orchestrator"),
        [ChatMessage("system", system), ChatMessage("user", prompt)],
        RouteDecision,
        temperature=0.0,
        max_tokens=ROUTE_MAX_TOKENS,
    )
    chosen = (decision.domain or "").strip().lower()
    # Deliberately narrower than ``normalize_domain``: a domain from a *different*
    # group is not a usable answer here, because stage one already ruled that
    # group out. Falling back inside the group keeps the two stages consistent.
    allowed = {entry.id for entry in members}
    return chosen if chosen in allowed else group.default_domain


async def route_decision(
    ctx: AgentContext,
    prompt: str,
    *,
    custom_agents: Sequence[dict] = (),
) -> RouteResult:
    """Classify the prompt into a domain and a complexity tier.

    ``custom_agents`` (routable custom agents owned by the caller) are merged
    into the stage-one options as ``custom:{id}`` selectors, so the orchestrator
    can route directly to a user's own agent (Backend v2 §4.3). A chosen custom
    id is validated against this allow-list — a hallucinated one falls back to
    the default group.

    Both stages fail soft. A stage-one failure routes to ``general``; a
    stage-two failure keeps the group and takes its ``default_domain``, so a
    task classified as, say, finance work still reaches a finance team rather
    than the generalist one.
    """
    await ctx.emit(
        EventType.NODE_UPDATE,
        {"role": AgentRole.ORCHESTRATOR.value, "state": "running"},
    )

    complexity = DEFAULT_TASK_COMPLEXITY
    try:
        custom, group_id, complexity = await _classify_group(ctx, prompt, custom_agents)
    except (LLMError, ValueError):
        logger.warning(
            "orchestrator group classification failed; using default domain",
            exc_info=True,
        )
        await _degraded(
            ctx, f"Could not classify the task; routed to '{DEFAULT_DOMAIN}'."
        )
        await _emit_done(
            ctx, DEFAULT_DOMAIN, "", "fallback: could not classify", complexity
        )
        return RouteResult(domain=DEFAULT_DOMAIN, complexity=complexity)

    if custom is not None:
        await _emit_done(ctx, custom, "", "routed to a custom agent", complexity)
        return RouteResult(domain=custom, complexity=complexity)

    group = get_group_info(group_id)
    # Surfaced so the Architect event log shows routing as the two steps it is.
    await ctx.emit(
        EventType.NODE_UPDATE,
        {
            "role": AgentRole.ORCHESTRATOR.value,
            "state": "running",
            "group": group.id,
            "complexity": complexity,
        },
    )

    try:
        domain = await _classify_domain(ctx, prompt, group)
        reason = f"{group.name} > {domain}"
    except (LLMError, ValueError):
        logger.warning(
            "orchestrator domain classification failed; using the group default",
            exc_info=True,
        )
        domain = group.default_domain
        reason = f"fallback: could not narrow within '{group.id}'"
        await _degraded(
            ctx,
            f"Could not pick an expert inside '{group.name}'; routed to '{domain}'.",
        )

    await _emit_done(ctx, domain, group.id, reason, complexity)
    return RouteResult(domain=domain, complexity=complexity, group=group.id)


async def _emit_done(
    ctx: AgentContext, domain: str, group: str, reason: str, complexity: str
) -> None:
    """Emit the terminal orchestrator node update."""
    await ctx.emit(
        EventType.NODE_UPDATE,
        {
            "role": AgentRole.ORCHESTRATOR.value,
            "state": "done",
            "domain": domain,
            "group": group,
            "reason": reason,
            "complexity": complexity,
            "source": "orchestrator",
        },
    )


async def route(ctx: AgentContext, prompt: str) -> str:
    """Return the domain the task should be routed to (compatibility wrapper)."""
    return (await route_decision(ctx, prompt)).domain
