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
issues on the fetched pages", "depends_on": []},
 {"member": "strategist", "brief": "Merge the findings into one prioritized \
action plan for the bakery site", "depends_on": ["keywords", "content_audit", \
"technical"]}]}"""

_REVIEW_RUBRIC = """\
- Every recommendation must name the metric it should move.
- Advice must be white-hat only; reject link schemes or keyword stuffing.
- Page-level findings must reference actually inspected content, not guesses.
- The action plan must be prioritized by impact vs effort, as one ranked list
  across all areas — four separate per-area lists are not a plan.
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

_STRATEGIST_INSTRUCTIONS = """\
You are the SEO strategist who turns the specialists' findings into one plan.
Method:
1. Read the keyword, on-page, technical and authority findings together and
   name the single constraint holding the site back. A site that cannot be
   crawled does not have a keyword problem yet.
2. Rank every recommendation across all four areas on one list — impact vs
   effort — rather than leaving four separate lists the reader must merge.
   Estimate impact as the metric it moves and by roughly how much.
3. Sequence the plan: what to do this week, this quarter, and what is only
   worth doing once the earlier items have landed.
4. State what would change the plan: the measurement that would reorder it.
5. Where a specialist could not inspect something live, carry that limitation
   into the plan rather than quietly presenting an estimate as a finding.
Quality bar: a site owner can start on Monday knowing exactly what to do
first and which number tells them it worked."""

_STRATEGIST_OUTPUT = """\
- Executive summary: the constraint, and the one action that matters most.
- Prioritized plan: action, area, impact (named metric), effort, sequence.
- This week / this quarter / later.
- What would change this plan, and what could not be verified live."""

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
        SubagentSpec(
            id="strategist",
            name="SEO Strategist",
            description=(
                "Merges the specialists' findings into one prioritized, "
                "sequenced action plan."
            ),
            role=(
                "merge the keyword, on-page, technical and authority findings "
                "into one impact-vs-effort prioritized action plan with an "
                "executive summary"
            ),
            instructions=_STRATEGIST_INSTRUCTIONS,
            output_format=_STRATEGIST_OUTPUT,
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
    # Left empty until this round, which is why a one-member SEO run answered
    # "how long should a title tag be" with a keyword cluster table: the planner
    # kept choosing `keywords`, the first member declared. `strategist` is the
    # only member whose output is the answer rather than an input to it.
    deliverable_member="strategist",
)
