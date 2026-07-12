"""Built-in domain agent definitions, one module per domain.

Adding a new domain = add a new module exposing a ``DOMAIN: DomainInfo``
constant and append it to ``DOMAIN_CATALOG`` below. Catalog order is
meaningful: ``GET /agents`` serializes agents in this order.
"""

from __future__ import annotations

from app.agents.domains import (
    content,
    data,
    education,
    finance,
    general,
    legal,
    marketing,
    research,
    searching,
    seo,
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
    general.DOMAIN,
)

__all__ = ["DOMAIN_CATALOG", "DomainInfo", "ReviewCriterion", "SubagentSpec"]
