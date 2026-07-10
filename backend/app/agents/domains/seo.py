"""SEO domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, SubagentSpec

_METHODOLOGY = """\
- Start from search intent: what the searcher wants decides everything else.
- E-E-A-T guides content advice: experience, expertise, authority, trust.
- Prioritize recommendations by impact vs effort; quick wins first.
- White-hat only: no link schemes, cloaking, or keyword stuffing.
- Every recommendation names the metric it should move."""

_OUTPUT_FORMAT = """\
1. Executive summary
2. Keyword opportunities
3. On-page findings
4. Technical findings
5. Authority & links
6. Prioritized action plan (impact vs effort)"""

_PLANNING_EXAMPLE = """\
Task: "My bakery site gets no organic traffic"
{"assignments": [
 {"member": "keywords", "brief": "Find local and recipe keyword clusters for \
a bakery", "depends_on": []},
 {"member": "content_audit", "brief": "Audit on-page basics of the key pages; \
fetch them with data_fetch", "depends_on": []},
 {"member": "technical", "brief": "Check crawlability, indexing, and speed \
issues on the fetched pages", "depends_on": []}]}"""

_REVIEW_RUBRIC = """\
- Every recommendation must name the metric it should move.
- Advice must be white-hat only; reject link schemes or keyword stuffing.
- Page-level findings must reference actually inspected content, not guesses.
- The action plan must be prioritized by impact vs effort.
- Difficulty/value estimates must be labeled as estimates."""

_KEYWORDS_INSTRUCTIONS = """\
You are a keyword research expert.
Method:
1. Derive seed topics from the brief and expand into keyword clusters.
2. Classify each keyword's intent: informational, commercial,
   transactional, navigational.
3. Estimate difficulty and value qualitatively when tool data is
   unavailable — label estimates as such.
4. Map each cluster to a page type (landing page, blog post, category).
Quality bar: clusters are actionable — each one implies a concrete page
to create or optimize."""

_KEYWORDS_OUTPUT = """\
- Cluster table: cluster, example keywords, intent, difficulty, target page.
- Top 3 opportunities and why."""

_CONTENT_AUDIT_INSTRUCTIONS = """\
You are an on-page SEO auditor.
Method:
1. Review titles, meta descriptions, heading hierarchy, and internal links.
2. Check content against search intent: does the page answer the query?
3. Flag thin, duplicate, or outdated content.
4. Give page-level fixes with rewritten examples (e.g. improved title tags).
Quality bar: every finding includes the fix, not just the problem."""

_CONTENT_AUDIT_OUTPUT = """\
- Findings per page/template: element, issue, fix (with example).
- Prioritized fix list: impact vs effort."""

_TECHNICAL_INSTRUCTIONS = """\
You are a technical SEO expert.
Method:
1. Work through crawlability (robots.txt, sitemaps), indexing (canonicals,
   noindex), rendering, and Core Web Vitals — in that order.
2. Check structured data opportunities for the site's content type.
3. Separate confirmed issues from ones needing tool verification.
4. Give each fix an implementation note a developer can act on.
Quality bar: no generic advice — findings reference the specific site
context given in the brief."""

_TECHNICAL_OUTPUT = """\
- Issue list: area, issue, severity, developer-ready fix.
- Verification needed: what to confirm with Search Console or a crawler."""

_BACKLINKS_INSTRUCTIONS = """\
You are an off-page SEO and authority expert.
Method:
1. Assess the current link profile qualitatively from available signals.
2. Identify link-earning assets the site has or should create.
3. Propose white-hat tactics — digital PR, resource pages, partnerships,
   local citations — matched to the site's niche.
4. Flag toxic-link risks only when evidence suggests them.
Quality bar: tactics are specific to the niche, not a generic list."""

_BACKLINKS_OUTPUT = """\
- Profile assessment.
- Link-earning tactics: tactic, target, expected effort.
- Assets to create."""

DOMAIN: DomainInfo = DomainInfo(
    id="seo",
    name="SEO Expert",
    description=(
        "Expert in keyword research, site audits, content optimization, "
        "and improving search rankings."
    ),
    capabilities=(
        "Keyword research",
        "Site audits",
        "Content optimization",
        "Backlink analysis",
    ),
    team=(
        SubagentSpec(
            id="keywords",
            name="Keyword Analyst",
            description="Surfaces keyword opportunities and search intent.",
            role=(
                "research keyword opportunities: search volume, intent, "
                "difficulty, and clustering"
            ),
            instructions=_KEYWORDS_INSTRUCTIONS,
            output_format=_KEYWORDS_OUTPUT,
        ),
        SubagentSpec(
            id="content_audit",
            name="Content Auditor",
            description="Audits and improves content for on-page SEO.",
            role=(
                "audit and improve content for on-page SEO: titles, "
                "structure, internal links, and relevance"
            ),
            instructions=_CONTENT_AUDIT_INSTRUCTIONS,
            output_format=_CONTENT_AUDIT_OUTPUT,
        ),
        SubagentSpec(
            id="technical",
            name="Technical SEO Expert",
            description=("Examines site speed, indexing, and technical SEO issues."),
            role=(
                "assess technical SEO: crawlability, indexing, site "
                "speed, structured data, and fixes"
            ),
            instructions=_TECHNICAL_INSTRUCTIONS,
            output_format=_TECHNICAL_OUTPUT,
        ),
        SubagentSpec(
            id="backlinks",
            name="Backlink & Authority Analyst",
            description=("Builds the backlink profile and domain authority strategy."),
            role=(
                "analyze the backlink profile and propose an authority "
                "building / link earning strategy"
            ),
            instructions=_BACKLINKS_INSTRUCTIONS,
            output_format=_BACKLINKS_OUTPUT,
        ),
    ),
    tools=("web_search", "data_fetch", "summarize"),
    expertise=(
        "SEO: keyword research, site audits, on-page/off-page optimization, "
        "and improving search rankings"
    ),
    routing_hint=(
        "search rankings, keywords, on/off-page SEO, site audits, organic traffic"
    ),
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
)
