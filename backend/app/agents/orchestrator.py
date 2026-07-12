"""Orchestrator: classifies the user prompt and routes to a domain.

Routing only — never produces the final work (CLAUDE.md §2).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.agents.base import AgentContext, with_current_date
from app.agents.prompts import ORCHESTRATOR_SYSTEM
from app.agents.registry import (
    CUSTOM_DOMAIN_PREFIX,
    DEFAULT_DOMAIN,
    DOMAIN_CATALOG,
    is_custom_domain,
    normalize_domain,
)
from app.agents.schemas import RouteDecision
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


async def route_decision(
    ctx: AgentContext,
    prompt: str,
    *,
    custom_agents: Sequence[dict] = (),
) -> RouteResult:
    """Classify the prompt into a domain and a complexity tier.

    ``custom_agents`` (routable custom agents owned by the caller) are merged
    into the routing catalog as ``custom:{id}`` options, so the orchestrator can
    route directly to a user's own agent (Backend v2 §4.3). A chosen custom id is
    validated against this allow-list — a hallucinated one falls back to default.
    """
    await ctx.emit(
        EventType.NODE_UPDATE,
        {"role": AgentRole.ORCHESTRATOR.value, "state": "running"},
    )
    lines = [f"- {entry.id}: {entry.routing_hint}" for entry in DOMAIN_CATALOG]
    allowed_custom: set[str] = set()
    for agent in custom_agents:
        selector = f"{CUSTOM_DOMAIN_PREFIX}{agent['id']}"
        allowed_custom.add(selector)
        hint = agent.get("routing_hint") or agent.get("name") or "custom agent"
        lines.append(f"- {selector}: {hint}")
    system = with_current_date(ORCHESTRATOR_SYSTEM.format(domains="\n".join(lines)))
    messages = [
        ChatMessage("system", system),
        ChatMessage("user", prompt),
    ]
    complexity = DEFAULT_TASK_COMPLEXITY
    try:
        decision = await structured_call(
            ctx.role_adapter("orchestrator"),
            messages,
            RouteDecision,
            temperature=0.0,
            max_tokens=ROUTE_MAX_TOKENS,
        )
        chosen = (decision.domain or "").strip().lower()
        if is_custom_domain(chosen):
            # Only a custom agent the caller actually owns is honoured.
            domain = chosen if chosen in allowed_custom else DEFAULT_DOMAIN
        else:
            domain = normalize_domain(chosen)
        reason = decision.reason
        complexity = decision.complexity
    except (LLMError, ValueError):
        # Fall back to a safe default rather than failing the whole task.
        # WARNING, not ERROR: expected degradation, must not flood Sentry.
        logger.warning(
            "orchestrator classification failed; using default domain",
            exc_info=True,
        )
        domain, reason = DEFAULT_DOMAIN, "fallback: could not classify"

    await ctx.emit(
        EventType.NODE_UPDATE,
        {
            "role": AgentRole.ORCHESTRATOR.value,
            "state": "done",
            "domain": domain,
            "reason": reason,
            "complexity": complexity,
            "source": "orchestrator",
        },
    )
    return RouteResult(domain=domain, complexity=complexity)


async def route(ctx: AgentContext, prompt: str) -> str:
    """Return the domain the task should be routed to (compatibility wrapper)."""
    return (await route_decision(ctx, prompt)).domain
