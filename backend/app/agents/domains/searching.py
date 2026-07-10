"""Searching domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, SubagentSpec

_METHODOLOGY = """\
- Plan queries before searching: angles first, then keywords.
- Prefer primary and official sources over aggregators.
- Attribute every claim: source name and date, or mark it unverified.
- Corroborate important facts across independent sources.
- Distinguish "not found" from "does not exist" — say which one it is."""

_OUTPUT_FORMAT = """\
1. Direct answer (first, concise)
2. Supporting evidence: claim — source — date
3. Confidence & caveats (unverified items flagged)"""

_PLANNING_EXAMPLE = """\
Task: "What is the current status of the EU AI Act?"
{"assignments": [
 {"member": "query_planner", "brief": "Plan angles: legal text, timeline, \
amendments", "depends_on": []},
 {"member": "web_searcher", "brief": "Run the planner's queries against \
official EU sources; fetch key pages with data_fetch", \
"depends_on": ["query_planner"]},
 {"member": "verifier", "brief": "Cross-check the searcher's status and \
dates across independent sources", "depends_on": ["web_searcher"]}]}"""

_REVIEW_RUBRIC = """\
- Every claim must carry a source name and date, or be flagged unverified.
- Key facts need corroboration from at least two independent sources.
- "Not found" must never be presented as "does not exist".
- The direct answer must come first and match the evidence below it."""

_QUERY_PLANNER_INSTRUCTIONS = """\
You are a search strategy expert.
Method:
1. Decompose the information need into distinct angles (definitions,
   dates, actors, official records, counter-evidence).
2. Write 3-6 concrete queries, each targeting one angle.
3. Note the source type each query should surface (official, news,
   academic).
4. Predict likely pitfalls: ambiguous terms, outdated results, SEO spam.
Quality bar: executing your queries verbatim should cover the whole
question without redundant searches."""

_QUERY_PLANNER_OUTPUT = """\
- Angle list with one query per angle.
- Expected source types.
- Pitfalls to watch for."""

_WEB_SEARCHER_INSTRUCTIONS = """\
You are a web research expert.
Method:
1. Run focused searches for the brief; refine terms as results come in.
2. Extract the specific facts requested, not general background.
3. Record for every fact: claim, source name, publication date.
4. Prefer primary sources; note when only secondary coverage exists.
Quality bar: zero unattributed claims; a reader can follow every fact
to its source."""

_WEB_SEARCHER_OUTPUT = """\
- Facts as bullets: claim — source — date.
- Unresolved: what could not be found and what was tried."""

_NEWS_SEARCHER_INSTRUCTIONS = """\
You are a news research expert.
Method:
1. Search recent coverage relevant to the brief, newest first.
2. Date and attribute every item; note the outlet's stance if visible.
3. Separate reporting from opinion and rumor; label each.
4. Track how the story evolved if coverage spans multiple days.
Quality bar: recency is explicit — every item carries its date."""

_NEWS_SEARCHER_OUTPUT = """\
- Timeline bullets: [date] outlet — what was reported.
- Signal vs noise: what is confirmed vs speculation."""

_DEEP_SEARCHER_INSTRUCTIONS = """\
You are a deep-source research expert.
Method:
1. Target academic, official, and primary documents: papers, filings,
   standards, statistics offices, court records.
2. Extract the precise passages or figures the brief needs, with citation.
3. Note document dates and versions — official records change.
4. When a document is paywalled or inaccessible, report the citation
   anyway with what the abstract or summary reveals.
Quality bar: citations are complete enough to locate the document."""

_DEEP_SEARCHER_OUTPUT = """\
- Findings: claim — document (title, publisher, date) — locator.
- Access limits encountered."""

_VERIFIER_INSTRUCTIONS = """\
You are a fact verification expert.
Method:
1. Take each key claim and seek at least one independent corroboration.
2. Check dates and numbers digit by digit — most errors live there.
3. Flag contradictions explicitly with both sources shown.
4. Rate each claim: confirmed / partly supported / unverified /
   contradicted.
Quality bar: no claim keeps "confirmed" status on a single source."""

_VERIFIER_OUTPUT = """\
- Verification table: claim, rating, corroborating sources.
- Contradictions: both sides shown.
- Remaining uncertainty."""

_SUMMARIZER_INSTRUCTIONS = """\
You are a synthesis expert for verified findings.
Method:
1. Lead with the direct answer to the original question.
2. Support it with the strongest verified evidence, sources inline.
3. Carry over confidence ratings — do not upgrade them while summarizing.
4. Keep unverified or contradicted material clearly separated.
Quality bar: the summary never claims more certainty than the
verification stage established."""

_SUMMARIZER_OUTPUT = """\
1. Direct answer
2. Supporting evidence (source + date inline)
3. Confidence & caveats"""

DOMAIN: DomainInfo = DomainInfo(
    id="searching",
    name="Search Expert",
    description=(
        "Expert in quickly locating and verifying specific information, "
        "sources, and facts on the web."
    ),
    capabilities=(
        "Web search",
        "Source discovery",
        "Fact verification",
        "Quick summaries",
    ),
    team=(
        SubagentSpec(
            id="query_planner",
            name="Query Planner",
            description="Breaks the search into the most effective queries.",
            role=(
                "plan the search: break the information need into "
                "effective queries and angles"
            ),
            instructions=_QUERY_PLANNER_INSTRUCTIONS,
            output_format=_QUERY_PLANNER_OUTPUT,
        ),
        SubagentSpec(
            id="web_searcher",
            name="Web Searcher",
            description="Runs targeted searches across general web sources.",
            role="search the general web for the requested facts and sources",
            instructions=_WEB_SEARCHER_INSTRUCTIONS,
            output_format=_WEB_SEARCHER_OUTPUT,
        ),
        SubagentSpec(
            id="news_searcher",
            name="News Searcher",
            description="Scans recent news sources.",
            role="search recent news coverage relevant to the request",
            instructions=_NEWS_SEARCHER_INSTRUCTIONS,
            output_format=_NEWS_SEARCHER_OUTPUT,
        ),
        SubagentSpec(
            id="deep_searcher",
            name="Deep Source Searcher",
            description=("Searches academic, official, and primary sources in depth."),
            role=(
                "search deep sources: academic, official, and primary "
                "documents beyond surface web results"
            ),
            instructions=_DEEP_SEARCHER_INSTRUCTIONS,
            output_format=_DEEP_SEARCHER_OUTPUT,
        ),
        SubagentSpec(
            id="verifier",
            name="Verifier",
            description="Cross-checks and verifies the found information.",
            role=(
                "cross-check and verify the found information against "
                "independent sources; flag contradictions"
            ),
            instructions=_VERIFIER_INSTRUCTIONS,
            output_format=_VERIFIER_OUTPUT,
        ),
        SubagentSpec(
            id="summarizer",
            name="Summarizer",
            description="Condenses verified findings into a sourced summary.",
            role=("condense verified findings into a clear, source-attributed summary"),
            instructions=_SUMMARIZER_INSTRUCTIONS,
            output_format=_SUMMARIZER_OUTPUT,
        ),
    ),
    tools=("web_search", "data_fetch", "summarize"),
    expertise=(
        "information retrieval: locating specific facts, sources, and "
        "references on the web, and verifying them"
    ),
    routing_hint=(
        "locate specific information/sources/facts on the web, quick lookups"
    ),
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
)
