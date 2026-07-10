"""Seed the first-party featured agent teams shown on the public landing page.

Run with ``python -m app.scripts.seed_marketplace`` from ``backend/``.

Idempotent: each team's ``id`` is derived from its slug with ``uuid5``, and the
document is upserted, so re-running refreshes the copy instead of duplicating
it. That makes the script safe to run against any environment, including
production — the content is Maestro's own, deliberately public.

``featured=True`` is set here and nowhere else. ``MarketplacePublish`` has no
such field and ``marketplace_service.publish`` hardcodes ``False``, so no user
can promote their own item onto the landing page.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.agents.registry import normalize_domain
from app.core.constants import (
    MARKETPLACE_FEATURED_AUTHOR,
    SECURITY_SCAN_PASSED,
    TOOL_IDS,
    MongoCollection,
)
from app.core.database import close_connections, get_mongo_db
from app.utils import prompt_guard

logger = logging.getLogger(__name__)

# Stable namespace so a slug always maps to the same document id.
_SEED_NAMESPACE = uuid.NAMESPACE_DNS
_SEED_ID_PREFIX = "maestro-seed"


@dataclass(frozen=True)
class SeedTeam:
    """A first-party agent team to publish as a featured marketplace item."""

    slug: str
    name: str
    domain: str
    description: str
    system_prompt: str
    tools: tuple[str, ...]

    @property
    def item_id(self) -> str:
        """Deterministic id — the upsert key that keeps seeding idempotent."""
        return str(uuid.uuid5(_SEED_NAMESPACE, f"{_SEED_ID_PREFIX}-{self.slug}"))


SEED_TEAMS: tuple[SeedTeam, ...] = (
    SeedTeam(
        slug="full-stack-feature-squad",
        name="Full-Stack Feature Squad",
        domain="software",
        description=(
            "Takes a feature request from spec to reviewed implementation. Plans the "
            "API contract, writes backend and frontend code, then audits its own "
            "diff for correctness and security before handing it back."
        ),
        system_prompt=(
            "You are a senior full-stack engineering team. Given a feature request, "
            "first restate the requirements and the acceptance criteria you will be "
            "measured against. Design the data model and API contract before writing "
            "any code. Implement the backend and the frontend as separate, reviewable "
            "steps. Match the conventions already present in the codebase rather than "
            "importing your own. Every code path you add must handle its failure "
            "modes explicitly. Close by listing what you changed, what you verified, "
            "and what a reviewer should look at first."
        ),
        tools=("web_search", "code_execution", "file_read"),
    ),
    SeedTeam(
        slug="market-pulse-analysts",
        name="Market Pulse Analysts",
        domain="finance",
        description=(
            "Tracks a ticker, sector or macro theme across filings, news and price "
            "action, then returns a position-neutral briefing with the bull case, the "
            "bear case, and the specific evidence behind each."
        ),
        system_prompt=(
            "You are a buy-side research desk. Given a company, sector or macro "
            "theme, gather primary sources first — filings, earnings transcripts, "
            "official releases — and treat press coverage as secondary. Separate what "
            "is reported from what is inferred, and label every inference as such. "
            "Present the bull case and the bear case with comparable rigor; never "
            "recommend a position. Quantify where the data allows and say so plainly "
            "where it does not. Flag any figure you could not corroborate against a "
            "second source. Close with the three questions a reader should resolve "
            "before acting."
        ),
        tools=("web_search", "data_fetch", "summarize"),
    ),
    SeedTeam(
        slug="launch-campaign-crew",
        name="Launch Campaign Crew",
        domain="marketing",
        description=(
            "Turns a product launch into a positioned campaign: audience research, "
            "message hierarchy, channel plan and ready-to-ship copy, checked against "
            "how the market is actually talking about the category."
        ),
        system_prompt=(
            "You are a product marketing team preparing a launch. Begin by defining "
            "the audience and the single problem the product solves for them; refuse "
            "to proceed on a vague audience. Research how competitors position "
            "themselves and how customers describe the problem in their own words, "
            "then build a message hierarchy from the strongest differentiated claim "
            "down. Draft channel-specific copy that follows that hierarchy rather "
            "than restating it. Every claim must be one the product can actually "
            "support. Close with the metric that will tell you the positioning "
            "landed, and the metric that will tell you it did not."
        ),
        tools=("web_search", "summarize", "sentiment_analysis"),
    ),
    SeedTeam(
        slug="technical-seo-auditors",
        name="Technical SEO Auditors",
        domain="seo",
        description=(
            "Crawls a site's structure, metadata and Core Web Vitals, then reports "
            "issues ranked by traffic impact rather than by how easy they are to "
            "spot — with the exact fix for each."
        ),
        system_prompt=(
            "You are a technical SEO audit team. Inspect the target site's crawl "
            "structure, indexation signals, metadata, structured data, internal "
            "linking and Core Web Vitals. Rank every finding by expected traffic "
            "impact, not by severity label or ease of detection — a slow largest "
            "contentful paint on a top landing page outranks a missing alt attribute "
            "anywhere. For each finding give the affected URLs, the measured "
            "evidence, the concrete fix, and the expected effect. Distinguish issues "
            "that block indexing from issues that merely dilute ranking. Never "
            "recommend a tactic that trades long-term crawl health for a short-term "
            "gain."
        ),
        tools=("web_search", "data_fetch", "file_read"),
    ),
    SeedTeam(
        slug="deep-research-desk",
        name="Deep Research Desk",
        domain="research",
        description=(
            "Answers an open question by sweeping the literature and the open web in "
            "parallel, cross-checking claims against their primary sources, and "
            "reporting what the evidence supports — and where it runs out."
        ),
        system_prompt=(
            "You are a research desk answering an open question. Decompose it into "
            "sub-questions and search each independently, using several framings so "
            "one vocabulary does not blind you to a whole literature. Trace every "
            "load-bearing claim back to its primary source; a citation of a citation "
            "is not evidence. When sources conflict, present the disagreement rather "
            "than resolving it silently, and say which position the stronger evidence "
            "favors. State explicitly where the evidence runs out and what a "
            "confident answer would require. Cite everything. Never present a "
            "plausible synthesis as an established finding."
        ),
        tools=("web_search", "summarize", "file_read"),
    ),
    SeedTeam(
        slug="contract-review-bench",
        name="Contract Review Bench",
        domain="legal",
        description=(
            "Reads a contract clause by clause, surfaces the obligations and the "
            "asymmetries, and flags the terms worth negotiating — as structured "
            "analysis, never as legal advice."
        ),
        system_prompt=(
            "You are a contract analysis bench. Read the document clause by clause "
            "and build a map of the obligations, rights, liabilities and termination "
            "conditions each party carries. Surface asymmetries: terms that bind one "
            "party more tightly than the other, and any clause whose plain reading "
            "differs from its apparent intent. Quote the operative language when you "
            "flag something. Rank the terms worth negotiating by the exposure they "
            "create. State clearly that this is structured analysis and not legal "
            "advice, and that a qualified attorney must review anything before it is "
            "signed."
        ),
        tools=("file_read", "summarize"),
    ),
)


def _validate(team: SeedTeam) -> None:
    """Fail loudly on a team the running system would itself reject."""
    unknown_tools = set(team.tools) - TOOL_IDS
    if unknown_tools:
        raise RuntimeError(
            f"Seed team {team.slug!r} declares unknown tools: {sorted(unknown_tools)}"
        )
    if normalize_domain(team.domain) != team.domain:
        raise RuntimeError(
            f"Seed team {team.slug!r} has unknown domain {team.domain!r}"
        )
    findings = prompt_guard.scan_prompt(team.system_prompt)
    if findings:
        raise RuntimeError(
            f"Seed team {team.slug!r} fails the security scan: {findings}"
        )


def _document(team: SeedTeam, now: datetime) -> dict[str, object]:
    """Build the mutable half of the Mongo document for a featured team."""
    return {
        "id": team.item_id,
        "name": team.name,
        "description": team.description,
        "domain": team.domain,
        "system_prompt": team.system_prompt,
        "tools": list(team.tools),
        "featured": True,
        "author_label": MARKETPLACE_FEATURED_AUTHOR,
        "security_scan": {
            "status": SECURITY_SCAN_PASSED,
            "findings": [],
            "scanned_at": now,
        },
    }


async def seed() -> int:
    """Upsert every featured team. Returns the number of teams written."""
    for team in SEED_TEAMS:
        _validate(team)

    collection = get_mongo_db()[MongoCollection.MARKETPLACE_ITEMS.value]
    now = datetime.now(UTC)
    for team in SEED_TEAMS:
        # `installs` and `created_at` are insert-only: re-seeding refreshes the
        # copy without resetting the counter or bumping the item back to the top
        # of the recency sort. `author_id` is never written — a featured team has
        # no owning user.
        await collection.update_one(
            {"id": team.item_id},
            {
                "$set": _document(team, now),
                "$setOnInsert": {"installs": 0, "created_at": now},
            },
            upsert=True,
        )
        logger.info("Seeded featured team %s", team.name)
    return len(SEED_TEAMS)


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        count = await seed()
        logger.info("Seeded %d featured agent teams.", count)
    finally:
        await close_connections()


if __name__ == "__main__":
    asyncio.run(_main())
