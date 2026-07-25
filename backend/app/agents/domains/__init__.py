"""Built-in domain agent definitions, one module per domain.

Adding a new domain = add a new module exposing a ``DOMAIN: DomainInfo``
constant and append it to ``DOMAIN_CATALOG`` below. Catalog order is
meaningful: ``GET /agents`` serializes agents in this order.
"""

from __future__ import annotations

from app.agents.domains import (
    community,
    content,
    data,
    education,
    finance,
    general,
    legal,
    local,
    marketing,
    opensource,
    research,
    searching,
    seo,
    social,
    software,
)
from app.agents.domains.base import DomainInfo, ReviewCriterion, SubagentSpec

DOMAIN_CATALOG: tuple[DomainInfo, ...] = (
    software.DOMAIN,
    finance.DOMAIN,
    marketing.DOMAIN,
    seo.DOMAIN,
    searching.DOMAIN,
    research.DOMAIN,
    data.DOMAIN,
    content.DOMAIN,
    legal.DOMAIN,
    education.DOMAIN,
    # Connected-API squads: each is powered by a BYOK service key and degrades
    # to web_search without one. Placed before `general`, which must stay last
    # as the routing fallback.
    social.DOMAIN,
    community.DOMAIN,
    opensource.DOMAIN,
    local.DOMAIN,
    general.DOMAIN,
)

__all__ = ["DOMAIN_CATALOG", "DomainInfo", "ReviewCriterion", "SubagentSpec"]
