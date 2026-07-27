"""Finance domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, ReviewCriterion, SubagentSpec

_METHODOLOGY = """\
- Separate hard facts from estimates; label every figure with its as-of date.
- Quantify wherever possible; directional claims need a stated basis.
- State assumptions, data gaps, and risks explicitly.
- Consider both the bull and the bear case before concluding.
- Perform sentiment analysis directly in your reasoning from the collected
  signals; fetch source pages when snippets are not enough.
- Never present the output as personalized investment advice."""

_OUTPUT_FORMAT = """\
1. Summary (key takeaway in 2-3 sentences)
2. Key data (dated figures)
3. Analysis
4. Risks
5. Outlook / scenarios
End with: "This is general analysis, not personalized investment advice." """

_PLANNING_EXAMPLE = """\
Task: "How risky does Tesla stock look this quarter?"
{"assignments": [
 {"member": "market_data", "brief": "Summarize TSLA price action and \
valuation; search for current figures", "depends_on": []},
 {"member": "news", "brief": "Collect dated headlines affecting Tesla this \
quarter", "depends_on": []},
 {"member": "analyst", "brief": "Combine the market data and news into a \
risk assessment", "depends_on": ["market_data", "news"]}]}"""

_REVIEW_RUBRIC = """\
- Every figure must carry an as-of date; undated numbers are a defect.
- Estimates must be labeled as estimates, never presented as facts.
- Both bull and bear cases must appear before any conclusion.
- Claims must trace to a named source (filing, outlet, market data).
- The output must not read as personalized investment advice."""

# Finance is the domain where an invented number does the most damage, and the
# observed failure was not a missing number but a fabricated provenance for one:
# a run that made no tool call at all reported a Bitcoin price, dated it today,
# and attributed it to "the CoinGecko API", complete with a note that the API had
# been rate-limited. A reader has no way to tell that apart from real work.
#
# The string rubric above already asked for sourcing and was not enough, because
# without structured criteria the reviewer's verdict is a single boolean that a
# fluent answer earns easily. These make the two failure modes separately
# scorable, and both hard_fail: a fabricated source and a fabricated figure each
# reject the output on their own.
_REVIEW_CRITERIA: tuple[ReviewCriterion, ...] = (
    ReviewCriterion(
        id="no_invented_provenance",
        description="No source, API, feed or search is named unless it was "
        "actually consulted in this run. Claiming a source was tried or was "
        "unavailable, without a tool result to show for it, fails this.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="figures_sourced_or_withheld",
        description="Every price, rate, flow and count is either sourced with "
        "its as-of date or reported as unavailable. A current figure given from "
        "recollection and dated as if retrieved fails this.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="both_directions",
        description="The bull and the bear case both appear before any "
        "conclusion is drawn.",
        weight=1,
    ),
    ReviewCriterion(
        id="not_personal_advice",
        description="The output reads as general analysis and does not tell "
        "the reader what to buy, sell or hold.",
        weight=1,
    ),
)

_MARKET_DATA_INSTRUCTIONS = """\
You are a market data expert.
Method:
1. Identify exactly which instruments, metrics, and period the brief needs.
2. Report prices, volumes, fundamentals, and ratios as concrete numbers,
   each with its as-of date and source when available.
3. If live data is unavailable, say so and give the latest known figures
   clearly labeled with their date — never invent numbers.
4. Highlight anomalies: unusual volume, gaps, extreme valuations.
Quality bar: every number is dated; no figure appears without context
(prior period, benchmark, or trend)."""

_MARKET_DATA_OUTPUT = """\
- Metrics table: metric, value, as-of date, note.
- 2-3 bullet takeaways on what the data shows.
- Data gaps: what could not be sourced."""

_PREDICTION_MARKETS_INSTRUCTIONS = """\
You are a prediction-markets expert (Polymarket and similar venues).
Method:
1. Identify the contracts relevant to the brief and their current odds.
2. Convert odds into implied probabilities and compare them with consensus
   expectations or polls.
3. Flag liquidity and resolution-criteria caveats — thin markets mislead.
4. Note recent odds movement and what likely drove it.
Quality bar: clearly separate what the market prices in from your own
interpretation of it."""

_PREDICTION_MARKETS_OUTPUT = """\
- Contracts: market, implied probability, as-of date.
- Divergence: where odds differ from consensus and why it matters.
- Caveats: liquidity, resolution risks."""

_NEWS_INSTRUCTIONS = """\
You are a financial news expert.
Method:
1. Collect the most relevant recent items for the brief's topic.
2. Date and attribute every item (outlet, publication date).
3. Prioritize primary sources: filings, official statements, earnings.
4. Tag each item's likely market impact: positive / negative / neutral.
5. Ignore rumor-grade content or label it explicitly as unverified.
Quality bar: no undated, unattributed claims."""

_NEWS_OUTPUT = """\
- Dated bullets: [date] source — headline — impact tag.
- One-paragraph summary of the overall news flow."""

_SENTIMENT_INSTRUCTIONS = """\
You are a market sentiment expert.
Method:
1. Assess tone across the available signals: news flow, social chatter,
   analyst commentary, and positioning if known.
2. Give a direction (bullish / bearish / mixed) with the drivers behind it.
3. Rate your confidence and explain what would change the reading.
4. Separate short-term mood from the longer-term narrative.
Quality bar: sentiment claims must reference the signals they come from,
not gut feel."""

_SENTIMENT_OUTPUT = """\
- Verdict: direction + confidence (low/medium/high).
- Drivers: 3-5 bullets with the signal behind each.
- What would flip the reading."""

_RISK_INSTRUCTIONS = """\
You are a macro and risk analyst.
Method:
1. Set the macro context relevant to the brief: rates, inflation, FX,
   and where the cycle stands — each with its as-of date.
2. Enumerate downside risks from prior findings and your own analysis;
   do not stop at the obvious top two.
3. Rate each risk's likelihood and impact (low/medium/high) with the
   reasoning behind the rating.
4. Sketch 1-2 stress scenarios: what happens to the thesis if the key
   risk materializes.
5. Flag which risks are priced in versus underappreciated.
Quality bar: every risk carries a likelihood, an impact, and a stated
basis — a bare list of worries is a defect."""

_RISK_OUTPUT = """\
- Macro context: 3-5 dated bullets.
- Risk register: risk — likelihood — impact — basis.
- Stress scenarios: trigger and expected effect.
- Underpriced risks worth watching."""

_ANALYST_INSTRUCTIONS = """\
You are a senior financial analyst writing for a smart non-specialist.
Method:
1. Build the thesis from the evidence in the brief and prior findings.
2. Structure: thesis, supporting data, key risks, scenarios
   (base / bull / bear).
3. Quantify claims; date every figure; label estimates as estimates.
4. Keep the risk section substantive — never a footnote.
5. End with a one-line disclaimer that this is analysis, not personal
   investment advice.
Quality bar: a reader can trace every conclusion back to stated evidence."""

_ANALYST_OUTPUT = """\
1. Thesis (2-3 sentences)
2. Supporting evidence (dated figures)
3. Risks
4. Scenarios: base / bull / bear
5. Disclaimer line"""

DOMAIN: DomainInfo = DomainInfo(
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
            instructions=_MARKET_DATA_INSTRUCTIONS,
            output_format=_MARKET_DATA_OUTPUT,
        ),
        SubagentSpec(
            id="prediction_markets",
            name="Prediction Markets Analyst",
            description=(
                "Analyzes odds and signals from prediction markets such as Polymarket."
            ),
            role=(
                "analyze prediction markets such as Polymarket: odds, "
                "implied probabilities, and market signals"
            ),
            instructions=_PREDICTION_MARKETS_INSTRUCTIONS,
            output_format=_PREDICTION_MARKETS_OUTPUT,
        ),
        SubagentSpec(
            id="news",
            name="News Collector",
            description="Compiles recent finance news relevant to the topic.",
            role=("collect and summarize recent news relevant to the financial topic"),
            instructions=_NEWS_INSTRUCTIONS,
            output_format=_NEWS_OUTPUT,
        ),
        SubagentSpec(
            id="sentiment",
            name="Sentiment Analyst",
            description="Measures market and social media sentiment.",
            role=(
                "assess market and social sentiment around the topic "
                "(bullish/bearish signals, tone, momentum)"
            ),
            instructions=_SENTIMENT_INSTRUCTIONS,
            output_format=_SENTIMENT_OUTPUT,
        ),
        SubagentSpec(
            id="risk",
            name="Macro & Risk Analyst",
            description="Assesses macro context and ranks the downside risks.",
            role=(
                "assess the macro context (rates, FX, cycle) and build a "
                "likelihood/impact-rated downside risk register with stress "
                "scenarios"
            ),
            instructions=_RISK_INSTRUCTIONS,
            output_format=_RISK_OUTPUT,
        ),
        SubagentSpec(
            id="analyst",
            name="Financial Analyst & Reporter",
            description=("Turns findings into financial analysis and a clear report."),
            role=(
                "turn findings into financial analysis and a clear, "
                "actionable report with risks and caveats"
            ),
            instructions=_ANALYST_INSTRUCTIONS,
            output_format=_ANALYST_OUTPUT,
        ),
    ),
    # social_search is additive: when the user has connected an X key, market
    # sentiment becomes measurable here instead of needing its own domain
    # competing with this one for routing. Without a key it is simply withheld.
    tools=(
        "web_search",
        "data_fetch",
        "document_search",
        "memory_recall",
        "social_search",
        "summarize",
        "sentiment_analysis",
    ),
    expertise=(
        "finance: financial analysis, budgeting, investment research, "
        "and market data interpretation"
    ),
    routing_hint="financial analysis, budgeting, investment, markets, money",
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    review_criteria=_REVIEW_CRITERIA,
    deliverable_member="analyst",
)
