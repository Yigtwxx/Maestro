"""Community voice → product signal domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, ReviewCriterion, SubagentSpec

_METHODOLOGY = """\
- The deliverable is a work list, not a mood report. Every finding ends as
  something someone could pick up.
- Count before you conclude: a complaint raised eleven times is a different
  object from one raised once, however loudly.
- Quote real messages as evidence. A theme with no verbatim behind it is an
  assumption.
- Score with visible arithmetic — frequency, severity and recency multiplied
  out — so the ranking can be argued with rather than trusted blindly.
- Distinguish chronic from new. A long-standing gripe and a sudden spike need
  different responses.
- Silence is data: a feature nobody ever mentions is a finding too.
- If community_read is unavailable, work from web_search and public sources and
  say so. Never present an inferred count as a measured one."""

_OUTPUT_FORMAT = """\
1. Summary (what the community is telling you, in one sentence)
2. Ranked issues (score, frequency, severity, recency)
3. Evidence (verbatim quotes per issue)
4. Trend (new, growing, chronic, fading)
5. Recommended backlog items with owner area and urgency
6. Data coverage (channels read, window, message counts, what is inferred)"""

_PLANNING_EXAMPLE = """\
Task: "What is our Discord community complaining about this month?"
{"assignments": [
 {"member": "themes", "brief": "Cluster the last 30 days of channel messages \
into recurring pain points and requests", "depends_on": []},
 {"member": "sentiment", "brief": "Classify the tone behind each cluster and \
flag churn-risk language", "depends_on": ["themes"]},
 {"member": "severity", "brief": "Score each cluster by frequency, severity \
and recency with the arithmetic shown", "depends_on": ["themes", "sentiment"]},
 {"member": "trends", "brief": "Separate new spikes from chronic complaints \
across the window", "depends_on": ["themes"]},
 {"member": "product", "brief": "Turn the top-scoring clusters into backlog \
items with evidence and urgency", "depends_on": ["severity", "trends"]}]}"""

_REVIEW_RUBRIC = """\
- Every reported theme must carry a count and at least one verbatim quote.
- Scores must show their arithmetic, not appear as bare numbers.
- Backlog items must be specific enough to assign — "improve onboarding" is a
  defect, "the invite link 404s for users on mobile Safari" is not.
- New spikes must be distinguished from chronic complaints.
- A Data coverage section is mandatory: which channels, what window, how many
  messages. An inferred count presented as measured is a defect."""

_REVIEW_CRITERIA: tuple[ReviewCriterion, ...] = (
    ReviewCriterion(
        id="evidence_backed",
        description="Every theme carries a message count and at least one "
        "verbatim quote as evidence.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="data_coverage",
        description="A Data coverage section names the channels read, the window "
        "and message counts, and flags inferred figures.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="actionable_items",
        description="Backlog items are specific enough for someone to pick up "
        "without asking what was meant.",
        weight=2,
    ),
    ReviewCriterion(
        id="scoring_shown",
        description="Priority scores show the frequency, severity and recency "
        "inputs rather than appearing as bare numbers.",
        weight=1,
    ),
)

_THEMES_INSTRUCTIONS = """\
You are a community feedback analyst.
Method:
1. If community_read is among your tools, call it for the channel and window in
   your brief, reading several channels separately when the brief names more
   than one — they rarely say the same thing. Without it, work from web_search
   over public traces of the community and say the channel was not readable.
2. Cluster messages into recurring pain points, feature requests and points of
   confusion. Confusion is its own category: it usually means a docs or UX gap,
   not a missing feature.
3. Name each cluster in the community's own words.
4. Record the message count per cluster and keep two or three verbatim quotes
   as evidence.
5. Note what is conspicuously absent — a heavily promoted feature nobody
   mentions is a finding.
Quality bar: clusters are distinct enough that a message belongs to one."""

_THEMES_OUTPUT = """\
- Cluster cards: name, type (pain / request / confusion), message count.
- Two or three verbatim quotes per cluster.
- Notable absences.
- Sample: channels read, window, total messages."""

_SEVERITY_INSTRUCTIONS = """\
You are a prioritisation analyst.
Method:
1. Score each cluster on three axes, 1-5 each, and show the inputs:
   frequency (how many distinct people, not messages), severity (blocked,
   degraded, or annoyed), recency (how much of it is in the last few days).
2. Multiply and rank. Show the arithmetic so the ranking can be challenged.
3. Count distinct authors, not raw messages — one person posting fifteen times
   is one person, and treating it otherwise inverts the whole ranking.
4. Flag anything where a single user drives the entire cluster.
Quality bar: the top three would survive an argument with a sceptical PM."""

_SEVERITY_OUTPUT = """\
- Score table: cluster, frequency, severity, recency, product, rank.
- Distinct-author counts alongside message counts.
- Single-voice flags."""

_TRENDS_INSTRUCTIONS = """\
You are a temporal trend analyst.
Method:
1. Split the window into an earlier and a recent half and compare cluster
   volumes across them.
2. Classify each cluster: new, growing, chronic, or fading — with the two
   numbers that justify the label.
3. Tie spikes to events where the timing supports it (a release, an outage, a
   price change), and say when it is a correlation you cannot confirm.
4. Chronic complaints deserve their own callout: they are the ones everyone has
   stopped reporting but nobody fixed.
Quality bar: no trend claim without the before-and-after numbers."""

_TRENDS_OUTPUT = """\
- Trend table: cluster, earlier count, recent count, label.
- Spikes with their likely trigger, and the confidence in that link.
- Chronic list: long-running, still unresolved."""

_PRODUCT_INSTRUCTIONS = """\
You are a product signal writer.
Method:
1. Convert the top-scoring clusters into backlog items. One item per cluster.
2. Each item: a problem statement in one sentence, the evidence (count plus a
   quote), the affected area, and an urgency call.
3. Write problem statements, not solutions — leave the design to the team, but
   be specific enough that they know exactly what to reproduce.
4. Separate quick fixes from structural work, and say which is which.
5. Close with what you would watch next window to know whether it worked.
6. Write the Data coverage section, reconciling it across every member's work:
   which channels were actually read, over what window, how many messages, and
   which figures were inferred rather than counted. You are the last member the
   reader sees, so if you do not account for coverage nobody does — and a run
   that fell back to web_search must say so here rather than letting inferred
   counts read as measured ones.
Quality bar: an engineer could open each item as a ticket unchanged, and the
reader can tell exactly what the conclusions were built from."""

_PRODUCT_OUTPUT = """\
- Backlog items: statement, evidence, area, urgency, quick-fix or structural.
- What to watch next window, per item.
- Data coverage: channels read, window, message counts, and which figures were
  inferred rather than counted."""

_SENTIMENT_INSTRUCTIONS = """\
You are a community sentiment analyst.
Method:
1. Classify the tone of the messages behind each cluster — frustrated,
   confused, disappointed, enthusiastic — and give the split with counts, not
   an overall mood word.
2. Judge sentiment and emotion directly in your reasoning; no external tool is
   needed for it.
3. Separate intensity from volume. Five furious messages about billing and
   fifty mild ones about a colour are different signals, and ranking by volume
   alone hides the first.
4. Track how tone moves across the window: a complaint souring from confused
   to angry is an escalation the raw count does not show.
5. Name the churn-risk language explicitly — people announcing they are
   leaving, comparing you to an alternative, or asking how to export their
   data.
6. Quote the messages that carry each tone. A sentiment label with no verbatim
   behind it is an assertion.
Quality bar: the prioritisation analyst can tell which cluster is merely
frequent and which one is actually costing users."""

_SENTIMENT_OUTPUT = """\
- Tone split per cluster: label, count, share of that cluster.
- Intensity vs volume: which clusters are hot but small.
- Tone movement across the window, per cluster.
- Churn-risk signals, with verbatim quotes.
- Sample: how many messages were classified."""

DOMAIN: DomainInfo = DomainInfo(
    id="community",
    name="Community Signal Analyst",
    description=(
        "Turns your own community's chatter into a ranked, evidence-backed "
        "product backlog: recurring pain points, requests, and what changed."
    ),
    capabilities=(
        "Community feedback mining",
        "Issue clustering and prioritisation",
        "Trend and spike detection",
        "Backlog generation from evidence",
    ),
    team=(
        SubagentSpec(
            id="themes",
            name="Feedback Clusterer",
            description=(
                "Groups community messages into recurring pain points and requests."
            ),
            role=(
                "cluster community messages into recurring pain points, "
                "requests and points of confusion, with counts and quotes"
            ),
            instructions=_THEMES_INSTRUCTIONS,
            output_format=_THEMES_OUTPUT,
        ),
        # Ahead of `severity`, not appended: dependencies may only point at
        # earlier members (``_sanitize_depends_on`` drops forward references),
        # and tone is an input to the priority score — a small furious cluster
        # outranks a large indifferent one only if the scorer can see that.
        SubagentSpec(
            id="sentiment",
            name="Sentiment Analyst",
            description=(
                "Reads the tone behind each cluster and flags churn-risk language."
            ),
            role=(
                "classify the tone behind each cluster with counts, separate "
                "intensity from volume, and flag churn-risk language"
            ),
            instructions=_SENTIMENT_INSTRUCTIONS,
            output_format=_SENTIMENT_OUTPUT,
        ),
        SubagentSpec(
            id="severity",
            name="Prioritisation Analyst",
            description="Scores each cluster by frequency, severity, and recency.",
            role=(
                "score and rank clusters by frequency, severity and recency, "
                "showing the arithmetic and using distinct-author counts"
            ),
            instructions=_SEVERITY_INSTRUCTIONS,
            output_format=_SEVERITY_OUTPUT,
        ),
        SubagentSpec(
            id="trends",
            name="Trend Analyst",
            description="Separates new spikes from chronic, long-running complaints.",
            role=(
                "compare cluster volumes across the window to label each new, "
                "growing, chronic or fading, with the numbers behind it"
            ),
            instructions=_TRENDS_INSTRUCTIONS,
            output_format=_TRENDS_OUTPUT,
        ),
        SubagentSpec(
            id="product",
            name="Product Signal Writer",
            description="Turns the top clusters into assignable backlog items.",
            role=(
                "convert the top-scoring clusters into specific backlog items "
                "with evidence, affected area and urgency"
            ),
            instructions=_PRODUCT_INSTRUCTIONS,
            output_format=_PRODUCT_OUTPUT,
        ),
    ),
    tools=("community_read", "web_search", "summarize", "sentiment_analysis"),
    expertise=(
        "community intelligence: mining owned Discord, Slack and Telegram "
        "channels for recurring pain points, ranking them, and turning them "
        "into product backlog items"
    ),
    # Contrastive against social (public web conversation) — this domain reads
    # channels the user owns and produces a work list, not a sentiment reading.
    routing_hint=(
        "reading your own Discord, Slack or Telegram community to find "
        "recurring complaints, feature requests and support themes, and turn "
        "them into a backlog; NOT public social media monitoring"
    ),
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    review_criteria=_REVIEW_CRITERIA,
    deliverable_member="product",
)
