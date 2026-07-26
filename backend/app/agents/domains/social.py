"""Social listening and sentiment domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, ReviewCriterion, SubagentSpec

_METHODOLOGY = """\
- Measure the conversation, do not characterise it. Counts, shares and rates
  first; adjectives only after a number justifies them.
- Every figure states its sample size and window. "Mostly positive" is worthless
  without "of 47 posts in the last 7 days".
- Engagement-weight before concluding: 3 posts with 40,000 likes matter more
  than 300 with none, and the reverse is also a finding.
- Separate what people say from who is saying it. A spike driven by one account
  is a different phenomenon from the same volume across hundreds.
- Sentiment without drivers is noise. Always name the specific claims moving it.
- If social_search is unavailable, work from web_search and say so explicitly.
  Never present an estimate as a measurement."""

_OUTPUT_FORMAT = """\
1. Headline (what the conversation is, in one sentence)
2. Volume and trend (counts, window, direction)
3. Sentiment breakdown with drivers
4. Themes and how they shifted
5. Who is driving it
6. Data coverage (which sources were live, sample sizes, what is inferred)"""

_PLANNING_EXAMPLE = """\
Task: "What are people saying about our new pricing?"
{"assignments": [
 {"member": "pulse", "brief": "Measure volume and engagement distribution for \
the pricing conversation over 7 days", "depends_on": []},
 {"member": "sentiment", "brief": "Classify sentiment and name the specific \
claims driving each side", "depends_on": []},
 {"member": "narrative", "brief": "Cluster the conversation into themes and \
track how they shifted across the window", "depends_on": []},
 {"member": "brief", "brief": "Synthesize a decision-ready read with \
confidence and data coverage", "depends_on": ["pulse", "sentiment", "narrative"]}]}"""

_REVIEW_RUBRIC = """\
- Every claim about volume or sentiment must carry a count and a window.
- Sentiment must name the specific drivers, not just a polarity split.
- Engagement weighting must be applied — raw post counts alone are not a
  measure of reach.
- A Data coverage section is mandatory: sample sizes, and which figures came
  from live platform data versus inference. An inferred number presented as
  measured is a defect.
- Conclusions drawn from fewer than a handful of posts must be labeled as
  anecdotal, not as a trend."""

_REVIEW_CRITERIA: tuple[ReviewCriterion, ...] = (
    ReviewCriterion(
        id="quantified",
        description="Every volume or sentiment claim carries a count, a window "
        "and a sample size.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="data_coverage",
        description="A Data coverage section states which figures came from live "
        "platform data and which were inferred.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="drivers_named",
        description="Sentiment findings name the specific claims driving them, "
        "not only a positive/negative split.",
        weight=1,
    ),
    ReviewCriterion(
        id="thin_sample_labeled",
        description="Conclusions from a small sample are labeled anecdotal "
        "rather than presented as a trend.",
        weight=1,
    ),
)

_PULSE_INSTRUCTIONS = """\
You are a social volume and engagement analyst.
Method:
1. If social_search is among your tools, run it for the topic and then one or
   two narrower variants — the sample is capped per call, so several sharp
   queries beat one broad one. If it is not, gather what you can with
   web_search and label the sample as indicative rather than measured.
2. Count posts per day across the window and state the direction: rising,
   flat, or falling, with the numbers.
3. Compute the engagement distribution: total likes/reposts/replies, the share
   held by the top few posts, and the median. A long tail and a single viral
   post are opposite situations.
4. Flag anomalies against the rest of the window — a day at several times the
   baseline is the finding, not a footnote.
5. Always state the sample size behind every number.
Quality bar: someone could redraw your chart from the numbers you reported."""

_PULSE_OUTPUT = """\
- Volume: posts per day across the window, with the total and direction.
- Engagement: total, median, and the top posts' share.
- Anomalies: days that broke the baseline, and by how much.
- Sample: how many posts, from how many queries."""

_SENTIMENT_INSTRUCTIONS = """\
You are a sentiment and emotion analyst.
Method:
1. Retrieve posts with social_search when you have it, otherwise with
   web_search, then classify each as positive, negative, neutral or mixed and
   report the split as counts and percentages.
2. Name the emotion behind the polarity where it is clear — frustration,
   excitement, confusion, betrayal — since each implies a different response.
3. For each side, quote the specific recurring claim that drives it. "Negative
   because people say the new tier removed a feature they paid for" is useful;
   "negative sentiment" is not.
4. Weight by engagement as well as by count, and report both when they disagree.
5. Note ambiguity honestly: sarcasm and jokes are common and often misread.
Quality bar: a reader knows what to fix, not merely that people are unhappy."""

_SENTIMENT_OUTPUT = """\
- Split: positive/negative/neutral/mixed as counts and percentages.
- Engagement-weighted split, when it differs from the raw one.
- Drivers: the recurring claim behind each side, with a representative quote.
- Ambiguity notes: what could not be classified confidently, and why."""

_NARRATIVE_INSTRUCTIONS = """\
You are a narrative and theme analyst.
Method:
1. Cluster retrieved posts into 3-6 recurring themes; name each in the
   audience's own words rather than in corporate language.
2. Size each theme: how many posts, what share of the total.
3. Track movement across the window — which themes are new, growing, fading.
   Compare an early slice against a recent one rather than asserting a trend.
4. Identify the framing: what story is being told about the subject, and what
   competing story exists.
Quality bar: the themes are distinct enough that a post belongs to exactly one."""

_NARRATIVE_OUTPUT = """\
- Theme cards: name, share of posts, representative quote.
- Movement: new / growing / fading, with the comparison behind the label.
- Dominant framing and the competing one."""

_VOICES_INSTRUCTIONS = """\
You are a network and amplification analyst.
Method:
1. From retrieved posts, identify which accounts appear repeatedly and which
   carry the engagement — they are often not the same accounts.
2. Distinguish organic spread from amplification: many small accounts saying
   similar things independently versus a few large accounts driving the reach.
3. Note follower scale for the accounts that matter, and whether the
   conversation is concentrated in one community or spread across several.
4. Say plainly when the sample is too small to judge the network structure.
Quality bar: a reader knows who to talk to, and whether this is a broad mood
or a few loud accounts."""

_VOICES_OUTPUT = """\
- Key accounts: handle, follower scale, why they matter.
- Concentration: share of engagement held by the top accounts.
- Organic vs amplified, with the evidence for the call.
- Communities involved."""

_BRIEF_INSTRUCTIONS = """\
You are the synthesis lead for a listening report.
Method:
1. Open with one sentence a decision-maker could act on.
2. Reconcile the other members' findings; where they disagree, say so and
   explain which evidence you weighted more.
3. State an explicit confidence level and what drove it — sample size, window,
   and whether live platform data was available.
4. Write the Data coverage section: which sources were live, which figures are
   inferred, and what a connected API key would have added.
5. Recommend at most three actions, each tied to a finding.
Quality bar: the reader never has to guess how solid the evidence is."""

_BRIEF_OUTPUT = """\
- Headline: one actionable sentence.
- Key findings: 3-5 bullets, each with its number.
- Confidence: level and what would raise it.
- Data coverage: live sources, sample sizes, inferred figures.
- Recommended actions: at most three, each tied to a finding."""

DOMAIN: DomainInfo = DomainInfo(
    id="social",
    name="Social Listening Analyst",
    description=(
        "Measures what people are actually saying about a brand, product, or "
        "topic: volume, sentiment drivers, themes, and who drives the conversation."
    ),
    capabilities=(
        "Social listening",
        "Sentiment and emotion analysis",
        "Theme and narrative tracking",
        "Influencer and amplification mapping",
    ),
    team=(
        SubagentSpec(
            id="pulse",
            name="Volume & Engagement Analyst",
            description="Measures how much is being said and how far it travels.",
            role=(
                "measure conversation volume, trend direction, and the "
                "engagement distribution, with sample sizes"
            ),
            instructions=_PULSE_INSTRUCTIONS,
            output_format=_PULSE_OUTPUT,
        ),
        SubagentSpec(
            id="sentiment",
            name="Sentiment Analyst",
            description="Classifies sentiment and names what is actually driving it.",
            role=(
                "classify sentiment and emotion, and name the specific "
                "recurring claims driving each side"
            ),
            instructions=_SENTIMENT_INSTRUCTIONS,
            output_format=_SENTIMENT_OUTPUT,
        ),
        SubagentSpec(
            id="narrative",
            name="Theme & Narrative Analyst",
            description=(
                "Clusters the conversation into themes and tracks how they move."
            ),
            role=(
                "cluster the conversation into themes and track which are "
                "growing or fading across the window"
            ),
            instructions=_NARRATIVE_INSTRUCTIONS,
            output_format=_NARRATIVE_OUTPUT,
        ),
        SubagentSpec(
            id="voices",
            name="Voices & Amplification Analyst",
            description=(
                "Identifies who carries the conversation and whether it is organic."
            ),
            role=(
                "identify the accounts and communities carrying the "
                "conversation, and separate organic spread from amplification"
            ),
            instructions=_VOICES_INSTRUCTIONS,
            output_format=_VOICES_OUTPUT,
        ),
        SubagentSpec(
            id="brief",
            name="Listening Brief Writer",
            description="Synthesizes a decision-ready read with explicit confidence.",
            role=(
                "synthesize the findings into a decision-ready brief with an "
                "explicit confidence level and data coverage"
            ),
            instructions=_BRIEF_INSTRUCTIONS,
            output_format=_BRIEF_OUTPUT,
        ),
    ),
    tools=(
        "social_search",
        "web_search",
        "data_fetch",
        "summarize",
        "sentiment_analysis",
    ),
    expertise=(
        "social listening: conversation volume and velocity, sentiment and its "
        "drivers, theme tracking, and amplification analysis"
    ),
    # Contrastive against marketing (which plans against an assumed audience)
    # and community (which reads owned, private channels).
    routing_hint=(
        "what people are publicly saying right now about a brand, product or "
        "topic — social media monitoring, sentiment, buzz, trending reaction; "
        "NOT planning a campaign, and NOT reading your own private channels"
    ),
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    review_criteria=_REVIEW_CRITERIA,
    deliverable_member="brief",
)
