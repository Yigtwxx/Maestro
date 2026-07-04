"""Agent registry: the built-in domain agent catalog with fixed teams.

Each Main Agent is a domain expert described by a ``DomainInfo`` entry. All
catalog text is English so LLMs and agents consume it directly; the frontend
localizes user-facing copy (see ``frontend/src/lib/agent-locale.ts``). Every
domain owns a FIXED team of specialist subagents (``SubagentSpec``): the Main
Agent never invents team members, it only briefs the relevant ones per task.
Domain definitions live one-per-module under ``app.agents.domains``; this
module assembles them and exposes the stable public API. Later this becomes
a dynamic registry backed by MongoDB (``agent_configurations``) with
per-agent tools and system prompts.
"""

from __future__ import annotations

from app.agents.domains import DOMAIN_CATALOG, DomainInfo, SubagentSpec

__all__ = [
    "DEFAULT_DOMAIN",
    "DOMAIN_CATALOG",
    "DOMAINS",
    "DomainInfo",
    "SubagentSpec",
    "get_domain_info",
    "normalize_domain",
]

# Supported domains the orchestrator can route to (derived from the catalog).
DOMAINS: tuple[str, ...] = tuple(entry.id for entry in DOMAIN_CATALOG)

DEFAULT_DOMAIN = "general"

_CATALOG_BY_ID: dict[str, DomainInfo] = {entry.id: entry for entry in DOMAIN_CATALOG}


def get_domain_info(domain: str) -> DomainInfo:
    """Return the catalog entry for a domain, falling back to ``general``."""
    return _CATALOG_BY_ID.get(normalize_domain(domain), _CATALOG_BY_ID[DEFAULT_DOMAIN])


def normalize_domain(candidate: str) -> str:
    """Map an LLM-proposed domain to a known one, defaulting to ``general``."""
    candidate = (candidate or "").strip().lower()
    return candidate if candidate in DOMAINS else DEFAULT_DOMAIN
