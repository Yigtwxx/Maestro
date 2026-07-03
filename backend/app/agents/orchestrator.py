"""Orchestrator: classifies the user prompt and routes to a domain.

Routing only — never produces the final work (CLAUDE.md §2).
"""

from __future__ import annotations

from app.agents.base import AgentContext, extract_json, with_current_date
from app.agents.prompts import ORCHESTRATOR_SYSTEM
from app.agents.registry import DEFAULT_DOMAIN, DOMAIN_CATALOG, normalize_domain
from app.core.constants import AgentRole, EventType
from app.services.llm_service import ChatMessage, LLMError


async def route(ctx: AgentContext, prompt: str) -> str:
    """Return the domain the task should be routed to."""
    await ctx.emit(
        EventType.NODE_UPDATE,
        {"role": AgentRole.ORCHESTRATOR.value, "state": "running"},
    )
    domain_lines = "\n".join(
        f"- {entry.id}: {entry.routing_hint}" for entry in DOMAIN_CATALOG
    )
    system = with_current_date(ORCHESTRATOR_SYSTEM.format(domains=domain_lines))
    messages = [
        ChatMessage("system", system),
        ChatMessage("user", prompt),
    ]
    try:
        response = await ctx.adapter.chat(messages, temperature=0.0)
        parsed = extract_json(response.content)
        domain = normalize_domain(str(parsed.get("domain", DEFAULT_DOMAIN)))
        reason = str(parsed.get("reason", ""))
    except (LLMError, ValueError):
        # Fall back to a safe default rather than failing the whole task.
        domain, reason = DEFAULT_DOMAIN, "fallback: could not classify"

    await ctx.emit(
        EventType.NODE_UPDATE,
        {
            "role": AgentRole.ORCHESTRATOR.value,
            "state": "done",
            "domain": domain,
            "reason": reason,
            "source": "orchestrator",
        },
    )
    return domain
