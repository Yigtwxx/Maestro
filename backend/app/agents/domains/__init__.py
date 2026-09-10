"""Built-in domain agent definitions, one module per domain.

Adding a new domain = add a new module exposing a ``DOMAIN: DomainInfo``
constant and append it to ``DOMAIN_CATALOG`` below, inside its group's block.
Catalog order is meaningful twice over: ``GET /agents`` serializes agents in
this order, and the frontend's ``AGENT_DOMAINS`` must list the same ids in the
same order (``tests/test_domain_frontend_parity.py``).

Domains are partitioned into ``DOMAIN_GROUP_CATALOG`` families. The grouping is
load-bearing rather than cosmetic — see ``DomainGroup`` in ``base.py`` for the
three things (routing, colour, motifs) that stopped scaling one-per-domain.
"""

from __future__ import annotations

from app.agents.domains import (
    ads,
    apidesign,
    brand,
    career,
    climate,
    cloud,
    community,
    content,
    crypto,
    data,
    devops,
    ecommerce,
    econ,
    education,
    finance,
    food,
    gamedev,
    general,
    health,
    hr,
    journalism,
    legal,
    local,
    marketing,
    mobile,
    opensource,
    personalfinance,
    procurement,
    product,
    project,
    qa,
    research,
    sales,
    scholar,
    searching,
    security,
    seo,
    social,
    software,
    support,
    tax,
    translation,
    travel,
)
from app.agents.domains.base import (
    DomainGroup,
    DomainInfo,
    ReviewCriterion,
    SubagentSpec,
)

# Stage-one routing options. Order is the order the catalog and the Architect
# catalog tabs are rendered in; ``knowledge`` sits last because it holds the
# `general` fallback.
DOMAIN_GROUP_CATALOG: tuple[DomainGroup, ...] = (
    DomainGroup(
        id="build",
        name="Engineering & Build",
        description=(
            "Writing, running, testing, shipping and operating software, and "
            "judging software someone else wrote."
        ),
        routing_hint=(
            "building, running and operating software and the infrastructure "
            "under it: writing and debugging code, testing, deployment "
            "pipelines, containers, monitoring, incidents and rollbacks, cloud "
            "and API design, security review, analysing data with code, "
            "evaluating a library or repository; NOT deciding what to build in "
            "the first place, and NOT looking up a fact about a tool"
        ),
        default_domain="software",
    ),
    DomainGroup(
        id="market",
        name="Growth & Market",
        description=(
            "Reaching an audience and getting it to act: positioning, "
            "channels, content, advertising and what people are saying."
        ),
        routing_hint=(
            "deciding what a product should be, and reaching the audience for "
            "it: requirements, MVP scope and what to cut, campaigns, "
            "positioning, search visibility, written and published content, "
            "paid advertising, brand and press, selling, online store "
            "operations, measuring public reaction; NOT building or operating "
            "the software itself, and NOT the financial modelling behind a "
            "decision"
        ),
        default_domain="marketing",
    ),
    DomainGroup(
        id="money",
        name="Finance & Markets",
        description=(
            "Money: markets and instruments, macroeconomic data, personal "
            "planning and tax."
        ),
        routing_hint=(
            "money and markets: instruments and valuations, crypto and "
            "on-chain assets, macroeconomic and public statistics, personal "
            "budgeting and saving, tax and accounting treatment; NOT pricing a "
            "product for a campaign"
        ),
        default_domain="finance",
    ),
    DomainGroup(
        id="operate",
        name="Business Operations",
        description=(
            "Running the organisation: contracts and compliance, people, "
            "customers, delivery and suppliers."
        ),
        routing_hint=(
            "running an organisation and serving the people it deals with: "
            "contracts, licensing and regulatory compliance, hiring and people "
            "policy as the employer, what your customers are reporting and how "
            "support answers them, project planning and delivery, choosing and "
            "negotiating with vendors; NOT building, running or operating your "
            "own systems and infrastructure, NOT the product decisions behind "
            "them, and NOT one person's own career, CV or job search, which is "
            "a personal decision"
        ),
        default_domain="legal",
    ),
    DomainGroup(
        id="life",
        name="Life & Local",
        description=(
            "Decisions a person makes for themselves, and anything anchored to "
            "a physical place."
        ),
        routing_hint=(
            "personal and place-anchored decisions: a physical neighbourhood "
            "and the businesses in it, trips and itineraries, someone's career "
            "and CV, health and medical information, food and nutrition; NOT "
            "company strategy"
        ),
        default_domain="local",
    ),
    DomainGroup(
        id="knowledge",
        name="Research & Knowledge",
        description=(
            "Finding out what is true and explaining it: lookups, deep "
            "research, academic literature, teaching, reporting and language."
        ),
        routing_hint=(
            "finding out and explaining: looking up a current fact, "
            "multi-source research, academic and scientific literature, "
            "teaching materials, verifying a claim or reporting a story, "
            "translation and localisation, climate and sustainability "
            "assessment, and anything no other group fits"
        ),
        default_domain="general",
    ),
)

DOMAIN_CATALOG: tuple[DomainInfo, ...] = (
    # --- build -------------------------------------------------------------
    software.DOMAIN,
    devops.DOMAIN,
    security.DOMAIN,
    qa.DOMAIN,
    cloud.DOMAIN,
    apidesign.DOMAIN,
    mobile.DOMAIN,
    gamedev.DOMAIN,
    data.DOMAIN,
    opensource.DOMAIN,
    # --- market ------------------------------------------------------------
    marketing.DOMAIN,
    seo.DOMAIN,
    content.DOMAIN,
    product.DOMAIN,
    sales.DOMAIN,
    ads.DOMAIN,
    brand.DOMAIN,
    ecommerce.DOMAIN,
    social.DOMAIN,
    # --- money -------------------------------------------------------------
    finance.DOMAIN,
    crypto.DOMAIN,
    econ.DOMAIN,
    personalfinance.DOMAIN,
    tax.DOMAIN,
    # --- operate -----------------------------------------------------------
    legal.DOMAIN,
    hr.DOMAIN,
    project.DOMAIN,
    procurement.DOMAIN,
    support.DOMAIN,
    community.DOMAIN,
    # --- life --------------------------------------------------------------
    local.DOMAIN,
    travel.DOMAIN,
    career.DOMAIN,
    health.DOMAIN,
    food.DOMAIN,
    # --- knowledge ---------------------------------------------------------
    searching.DOMAIN,
    research.DOMAIN,
    scholar.DOMAIN,
    education.DOMAIN,
    journalism.DOMAIN,
    translation.DOMAIN,
    climate.DOMAIN,
    # `general` must stay last: it is the routing fallback.
    general.DOMAIN,
)

__all__ = [
    "DOMAIN_CATALOG",
    "DOMAIN_GROUP_CATALOG",
    "DomainGroup",
    "DomainInfo",
    "ReviewCriterion",
    "SubagentSpec",
]
