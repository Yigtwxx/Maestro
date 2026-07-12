"""Hierarchical token-budget helpers (Backend v2 §4.6/D19).

The task's token cap lives on :class:`~app.agents.base.AgentContext` as
``token_budget``; the running spend is read off the wrapping ``TokenMeter``. The
Main Agent checks this at wave boundaries and each subagent checks it before
every LLM turn, so a runaway is cut off promptly instead of at the next barrier.
"""

from __future__ import annotations

from app.agents.base import AgentContext


def tokens_used(ctx: AgentContext) -> int:
    """Tokens metered so far this task (0 for a plain, uncounted adapter)."""
    return getattr(ctx.adapter, "total_tokens", 0)


def budget_exceeded(ctx: AgentContext) -> bool:
    """True once the metered spend has crossed the task's token budget.

    An unset budget (``None``) or an adapter with no counter never trips, so a
    direct caller / test with a plain adapter is unaffected.
    """
    return ctx.token_budget is not None and tokens_used(ctx) >= ctx.token_budget
