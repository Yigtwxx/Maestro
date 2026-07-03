"""Agent registry: the built-in domain agent catalog with fixed teams.

Each Main Agent is a domain expert described by a ``DomainInfo`` entry. All
catalog text is English so LLMs and agents consume it directly; the frontend
localizes user-facing copy (see ``frontend/src/lib/agent-locale.ts``). Every
domain owns a FIXED team of specialist subagents (``SubagentSpec``): the Main
Agent never invents team members, it only briefs the relevant ones per task.
Later this becomes a dynamic registry backed by MongoDB
(``agent_configurations``) with per-agent tools and system prompts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubagentSpec:
    """A fixed team member of a domain agent."""

    id: str
    # English display name; the frontend localizes it for the UI.
    name: str
    description: str
    # English prompt fragment: the member's specialization, injected into the
    # subagent system prompt and the Main Agent's team roster.
    role: str


@dataclass(frozen=True)
class DomainInfo:
    """A built-in domain agent (Main Agent) definition."""

    id: str
    # English display name; the frontend localizes it for the UI.
    name: str
    description: str
    capabilities: tuple[str, ...]
    # The fixed subagent team the Main Agent manages (never invented per task).
    team: tuple[SubagentSpec, ...]
    # Declared tool ids from ``TOOL_CATALOG`` (metadata only for this tier).
    tools: tuple[str, ...]
    # English prompt fragments (all system prompts are English).
    expertise: str
    routing_hint: str


DOMAIN_CATALOG: tuple[DomainInfo, ...] = (
    DomainInfo(
        id="software",
        name="Software Expert",
        description=(
            "Expert in writing code, debugging, architecture design, "
            "and API development."
        ),
        capabilities=("Coding", "Debugging", "Architecture design", "Code review"),
        team=(
            SubagentSpec(
                id="architect",
                name="Architect",
                description="Defines the solution architecture and design decisions.",
                role=(
                    "design the solution architecture: components, interfaces, "
                    "data flow, and key technical decisions"
                ),
            ),
            SubagentSpec(
                id="coder",
                name="Coder",
                description="Writes or fixes the code the task requires.",
                role="write or fix the code required by the task",
            ),
            SubagentSpec(
                id="tester",
                name="Tester",
                description="Produces test cases and edge cases.",
                role=(
                    "produce test cases and edge cases that validate the "
                    "solution's correctness"
                ),
            ),
            SubagentSpec(
                id="reviewer",
                name="Code Reviewer",
                description="Reviews the code for quality, security, and style.",
                role=(
                    "review the code for correctness, security, and style, "
                    "and suggest concrete improvements"
                ),
            ),
        ),
        tools=("code_execution", "file_read"),
        expertise=(
            "software engineering: writing code, debugging, architecture design, "
            "APIs, and code review"
        ),
        routing_hint="code, debugging, software architecture, APIs, technical builds",
    ),
    DomainInfo(
        id="finance",
        name="Finance Expert",
        description=(
            "Expert in financial analysis, budgeting, investment research, "
            "and market data interpretation."
        ),
        capabilities=(
            "Financial analysis",
            "Budgeting",
            "Investment research",
            "Market data",
        ),
        team=(
            SubagentSpec(
                id="market_data",
                name="Market Data Analyst",
                description="Gathers prices, volumes, and core market data.",
                role=(
                    "gather and interpret market data: prices, volumes, "
                    "fundamentals, and key financial metrics"
                ),
            ),
            SubagentSpec(
                id="prediction_markets",
                name="Prediction Markets Analyst",
                description=(
                    "Analyzes odds and signals from prediction markets "
                    "such as Polymarket."
                ),
                role=(
                    "analyze prediction markets such as Polymarket: odds, "
                    "implied probabilities, and market signals"
                ),
            ),
            SubagentSpec(
                id="news",
                name="News Collector",
                description="Compiles recent finance news relevant to the topic.",
                role=(
                    "collect and summarize recent news relevant to the financial topic"
                ),
            ),
            SubagentSpec(
                id="sentiment",
                name="Sentiment Analyst",
                description="Measures market and social media sentiment.",
                role=(
                    "assess market and social sentiment around the topic "
                    "(bullish/bearish signals, tone, momentum)"
                ),
            ),
            SubagentSpec(
                id="analyst",
                name="Financial Analyst & Reporter",
                description=(
                    "Turns findings into financial analysis and a clear report."
                ),
                role=(
                    "turn findings into financial analysis and a clear, "
                    "actionable report with risks and caveats"
                ),
            ),
        ),
        tools=("web_search", "data_fetch", "summarize", "sentiment_analysis"),
        expertise=(
            "finance: financial analysis, budgeting, investment research, "
            "and market data interpretation"
        ),
        routing_hint="financial analysis, budgeting, investment, markets, money",
    ),
    DomainInfo(
        id="marketing",
        name="Marketing Expert",
        description=(
            "Expert in campaign planning, brand strategy, copywriting, "
            "and growth tactics."
        ),
        capabilities=(
            "Campaign planning",
            "Brand strategy",
            "Copywriting",
            "Growth tactics",
        ),
        team=(
            SubagentSpec(
                id="audience",
                name="Audience Analyst",
                description="Analyzes the target audience, its needs, and segments.",
                role=(
                    "analyze the target audience: segments, needs, pain "
                    "points, and where to reach them"
                ),
            ),
            SubagentSpec(
                id="strategist",
                name="Strategist",
                description="Crafts the campaign and brand strategy.",
                role=(
                    "craft the campaign and brand strategy: positioning, "
                    "messaging pillars, and channel mix"
                ),
            ),
            SubagentSpec(
                id="copywriter",
                name="Copywriter",
                description="Writes persuasive marketing copy and slogans.",
                role=(
                    "write persuasive marketing copy: headlines, ad texts, "
                    "and calls to action"
                ),
            ),
            SubagentSpec(
                id="growth",
                name="Channel & Growth Expert",
                description="Recommends channels, budget, and growth tactics.",
                role=(
                    "recommend channels, budget allocation, and growth "
                    "tactics with measurable KPIs"
                ),
            ),
        ),
        tools=("web_search", "summarize", "sentiment_analysis"),
        expertise=(
            "marketing: campaign planning, brand strategy, copywriting, "
            "and growth tactics"
        ),
        routing_hint="campaigns, branding, copywriting, growth, advertising",
    ),
    DomainInfo(
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
            ),
            SubagentSpec(
                id="content_audit",
                name="Content Auditor",
                description="Audits and improves content for on-page SEO.",
                role=(
                    "audit and improve content for on-page SEO: titles, "
                    "structure, internal links, and relevance"
                ),
            ),
            SubagentSpec(
                id="technical",
                name="Technical SEO Expert",
                description=(
                    "Examines site speed, indexing, and technical SEO issues."
                ),
                role=(
                    "assess technical SEO: crawlability, indexing, site "
                    "speed, structured data, and fixes"
                ),
            ),
            SubagentSpec(
                id="backlinks",
                name="Backlink & Authority Analyst",
                description=(
                    "Builds the backlink profile and domain authority strategy."
                ),
                role=(
                    "analyze the backlink profile and propose an authority "
                    "building / link earning strategy"
                ),
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
    ),
    DomainInfo(
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
            ),
            SubagentSpec(
                id="web_searcher",
                name="Web Searcher",
                description="Runs targeted searches across general web sources.",
                role="search the general web for the requested facts and sources",
            ),
            SubagentSpec(
                id="news_searcher",
                name="News Searcher",
                description="Scans recent news sources.",
                role="search recent news coverage relevant to the request",
            ),
            SubagentSpec(
                id="deep_searcher",
                name="Deep Source Searcher",
                description=(
                    "Searches academic, official, and primary sources in depth."
                ),
                role=(
                    "search deep sources: academic, official, and primary "
                    "documents beyond surface web results"
                ),
            ),
            SubagentSpec(
                id="verifier",
                name="Verifier",
                description="Cross-checks and verifies the found information.",
                role=(
                    "cross-check and verify the found information against "
                    "independent sources; flag contradictions"
                ),
            ),
            SubagentSpec(
                id="summarizer",
                name="Summarizer",
                description="Condenses verified findings into a sourced summary.",
                role=(
                    "condense verified findings into a clear, source-attributed summary"
                ),
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
    ),
    DomainInfo(
        id="research",
        name="Research Expert",
        description=(
            "Expert in in-depth multi-source analysis, synthesis, and "
            "comprehensive report writing."
        ),
        capabilities=(
            "Deep analysis",
            "Multi-source synthesis",
            "Report writing",
            "Literature review",
        ),
        team=(
            SubagentSpec(
                id="collector",
                name="Source Collector",
                description="Collects diverse, credible sources on the topic.",
                role=(
                    "collect diverse, credible sources and raw material on the topic"
                ),
            ),
            SubagentSpec(
                id="analyst",
                name="Analyst",
                description="Analyzes the collected material in depth.",
                role=(
                    "analyze the collected material in depth: patterns, "
                    "evidence quality, and implications"
                ),
            ),
            SubagentSpec(
                id="critic",
                name="Critic",
                description="Surfaces opposing views and weak points.",
                role=(
                    "argue the counter-position: surface opposing views, "
                    "weaknesses, and open questions"
                ),
            ),
            SubagentSpec(
                id="synthesizer",
                name="Synthesizer",
                description="Merges analysis and critique into a coherent whole.",
                role=(
                    "synthesize the analysis and critique into a coherent, "
                    "balanced set of conclusions"
                ),
            ),
            SubagentSpec(
                id="writer",
                name="Report Writer",
                description="Turns the conclusions into a structured report.",
                role=(
                    "write the structured final report: findings, evidence, "
                    "and recommendations"
                ),
            ),
        ),
        tools=("web_search", "summarize", "file_read"),
        expertise=(
            "research: in-depth multi-source analysis, synthesis, and "
            "comprehensive report writing"
        ),
        routing_hint=(
            "in-depth multi-source analysis and synthesis of a topic, reports"
        ),
    ),
    DomainInfo(
        id="data",
        name="Data Expert",
        description=(
            "Expert in data analysis, statistics, visualization, "
            "and data pipeline design."
        ),
        capabilities=("Data analysis", "Statistics", "Visualization", "Data pipelines"),
        team=(
            SubagentSpec(
                id="cleaner",
                name="Data Cleaner",
                description="Cleans the data and fixes gaps and inconsistencies.",
                role=(
                    "clean and prepare the data: handle missing values, "
                    "outliers, and inconsistencies"
                ),
            ),
            SubagentSpec(
                id="statistician",
                name="Statistician",
                description="Runs statistical analysis and modeling.",
                role=(
                    "run the statistical analysis: descriptive stats, tests, "
                    "and simple models as appropriate"
                ),
            ),
            SubagentSpec(
                id="visualizer",
                name="Visualizer",
                description="Designs the right visualizations for the findings.",
                role=(
                    "design the right visualizations for the findings and "
                    "describe or specify them precisely"
                ),
            ),
            SubagentSpec(
                id="interpreter",
                name="Interpreter & Reporter",
                description="Translates the results into business language.",
                role=(
                    "interpret the results in plain business language and "
                    "report the takeaways"
                ),
            ),
        ),
        tools=("data_fetch", "code_execution", "file_read"),
        expertise=(
            "data: data analysis, statistics, visualization, and data pipelines"
        ),
        routing_hint="data analysis, statistics, visualization, datasets, pipelines",
    ),
    DomainInfo(
        id="general",
        name="General Expert",
        description=("Versatile generalist for any task that fits no specific domain."),
        capabilities=("General tasks", "Writing", "Planning", "Summarizing"),
        team=(
            SubagentSpec(
                id="researcher",
                name="Researcher",
                description="Gathers the information the task needs.",
                role="gather the information the task needs",
            ),
            SubagentSpec(
                id="writer",
                name="Writer",
                description=(
                    "Produces the main deliverable (text, plan, summary, etc.)."
                ),
                role="produce the main deliverable (text, plan, summary, etc.)",
            ),
            SubagentSpec(
                id="checker",
                name="Checker",
                description="Checks the deliverable for accuracy and completeness.",
                role="check the deliverable for accuracy and completeness",
            ),
        ),
        tools=("web_search", "summarize"),
        expertise="general-purpose assistance across any topic",
        routing_hint="anything that fits no other domain",
    ),
)

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
