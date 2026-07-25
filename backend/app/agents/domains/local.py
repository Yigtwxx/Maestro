"""Local and place intelligence domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, ReviewCriterion, SubagentSpec

_METHODOLOGY = """\
- Report the distribution, never the winner. "The median competitor holds 4.2
  over 180 reviews" tells you where to aim; "the best one has 4.8" does not.
- A rating without a review count is meaningless. Always carry both, and treat
  a 5.0 over 6 reviews as unproven rather than excellent.
- Mine review text for the recurring specific complaint, not the average
  adjective. "Parking" beats "service could be better".
- Geography is a constraint, not a footnote: state the area you actually
  searched, because the answer changes two streets over.
- Separate what the market lacks from what the market has already rejected.
- If places_intel is unavailable, work from web_search and say so. Never
  present an inferred rating or count as a measured one."""

_OUTPUT_FORMAT = """\
1. Market snapshot (area searched, how many competitors found)
2. Competitor table (rating, review count, price level, category)
3. Distribution (median rating, spread, review-volume leaders)
4. Review themes (recurring praise and recurring complaints)
5. Gaps and opportunities, ranked
6. Data coverage (which figures were live, sample sizes, what is inferred)"""

_PLANNING_EXAMPLE = """\
Task: "Is there room for a specialty coffee shop in Kadikoy?"
{"assignments": [
 {"member": "mapper", "brief": "Find the specialty coffee competitors in \
Kadikoy", "depends_on": []},
 {"member": "metrics", "brief": "Compute the rating, review-volume and price \
distribution across the competitors found", "depends_on": ["mapper"]},
 {"member": "reviews", "brief": "Mine competitor reviews for recurring \
complaints and praise themes", "depends_on": ["mapper"]},
 {"member": "gap", "brief": "Rank the unmet-demand and positioning gaps from \
the metrics and review themes", "depends_on": ["metrics", "reviews"]}]}"""

_REVIEW_RUBRIC = """\
- Every rating must be reported with its review count; a rating alone is a defect.
- The area actually searched must be stated explicitly.
- Findings must describe the distribution, not just the top-rated place.
- Review themes must be specific and recurring, with the count behind each.
- A Data coverage section is mandatory: how many places, which figures were
  live. An inferred rating presented as measured is a defect."""

_REVIEW_CRITERIA: tuple[ReviewCriterion, ...] = (
    ReviewCriterion(
        id="rating_with_count",
        description="Every rating is reported alongside its review count, and "
        "low-sample ratings are labeled unproven.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="data_coverage",
        description="A Data coverage section states the area searched, how many "
        "places were found, and which figures were inferred.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="distribution_reported",
        description="The analysis describes the spread across competitors, not "
        "only the best or worst one.",
        weight=1,
    ),
    ReviewCriterion(
        id="specific_themes",
        description="Review themes are specific recurring complaints with counts, "
        "not generic adjectives.",
        weight=1,
    ),
)

_MAPPER_INSTRUCTIONS = """\
You are a local market mapper.
Method:
1. If places_intel is among your tools, call it with aspect "search" for the
   category and area in your brief, splitting a broad area into two or three
   narrower searches — local markets do not average well across a city.
   Without it, assemble the competitor set from web_search and say so.
2. List every competitor found with its category and address, and say how many
   came back versus how many you asked for.
3. Flag places that are permanently closed or of a different category — they
   inflate a count without competing.
4. State the exact area string you searched. A reader must be able to reproduce it.
Quality bar: the competitor set is one a local would recognise as the real one."""

_MAPPER_OUTPUT = """\
- Area searched, exactly as queried.
- Competitor list: name, category, address.
- Count found, and anything excluded with the reason."""

_METRICS_INSTRUCTIONS = """\
You are a local market metrics analyst.
Method:
1. For every competitor, record rating, review count and price level together.
2. Compute the distribution: median rating, the range, and how many sit above
   and below the median. Do the same for review volume.
3. Treat a high rating on very few reviews as unproven and say so — it is the
   most common way a local market read goes wrong.
4. Identify the review-volume leaders separately from the rating leaders. The
   busiest place and the best-rated place are usually different, and that gap
   is itself the finding.
5. Report price-level spread where the data carries it.
Quality bar: a reader knows what "good" means in this specific market."""

_METRICS_OUTPUT = """\
- Table: competitor, rating, review count, price level.
- Distribution: median rating, range, above/below counts.
- Volume leaders vs rating leaders.
- Low-sample entries explicitly flagged."""

_REVIEWS_INSTRUCTIONS = """\
You are a review mining analyst.
Method:
1. Call places_intel with aspect "reviews" for the competitor set when the tool
   is available; otherwise mine whatever review text web_search surfaces and
   state that the sample is partial.
2. Cluster review text into recurring praise themes and recurring complaint
   themes; count how many reviews carry each.
3. Keep the specifics. "Slow at weekends", "no parking", "loud music" are
   findings; "poor service" is not.
4. Separate complaints that are fixable by a newcomer from those inherent to
   the location or the category.
5. Note where the review text contradicts the star rating.
Quality bar: each theme names something a competitor could act on tomorrow."""

_REVIEWS_OUTPUT = """\
- Praise themes: theme, count, representative quote.
- Complaint themes: theme, count, representative quote.
- Fixable versus inherent split.
- Contradictions between text and rating."""

_GAP_INSTRUCTIONS = """\
You are a market gap analyst.
Method:
1. Combine the distribution with the review themes to name unmet demand: what
   customers repeatedly complain about that nobody in the set solves.
2. Rank the gaps by how much evidence supports them, not by how appealing they
   sound.
3. Distinguish an unmet need from a rejected one — if several competitors tried
   something and rate poorly for it, that is a warning, not an opening.
4. Give a positioning recommendation with the rating and review-volume target a
   newcomer would need to hit to be credible.
5. State plainly what would change the conclusion.
Quality bar: the recommendation is specific to this area, not generic advice."""

_GAP_OUTPUT = """\
- Ranked gaps: gap, supporting evidence, confidence.
- Rejected-approach warnings.
- Positioning recommendation with a credible rating/volume target.
- What would change this conclusion."""

DOMAIN: DomainInfo = DomainInfo(
    id="local",
    name="Local Market Analyst",
    description=(
        "Maps the competitors in a physical area and mines their reviews to "
        "find rating distributions, recurring complaints, and market gaps."
    ),
    capabilities=(
        "Local competitor mapping",
        "Rating and review distribution",
        "Review theme mining",
        "Market gap analysis",
    ),
    team=(
        SubagentSpec(
            id="mapper",
            name="Market Mapper",
            description="Finds the real competitor set in a specific area.",
            role=(
                "find the competitors in the stated area and state exactly "
                "what geography was searched"
            ),
            instructions=_MAPPER_INSTRUCTIONS,
            output_format=_MAPPER_OUTPUT,
        ),
        SubagentSpec(
            id="metrics",
            name="Market Metrics Analyst",
            description="Computes the rating, review-volume, and price distribution.",
            role=(
                "compute the rating, review-volume and price distribution "
                "across the competitor set, flagging low-sample ratings"
            ),
            instructions=_METRICS_INSTRUCTIONS,
            output_format=_METRICS_OUTPUT,
        ),
        SubagentSpec(
            id="reviews",
            name="Review Miner",
            description="Extracts recurring praise and complaint themes from reviews.",
            role=(
                "mine competitor reviews for specific recurring praise and "
                "complaint themes, with counts"
            ),
            instructions=_REVIEWS_INSTRUCTIONS,
            output_format=_REVIEWS_OUTPUT,
        ),
        SubagentSpec(
            id="gap",
            name="Gap Analyst",
            description="Ranks unmet demand and recommends a positioning.",
            role=(
                "rank the unmet-demand and positioning gaps, separating unmet "
                "needs from approaches the market has already rejected"
            ),
            instructions=_GAP_INSTRUCTIONS,
            output_format=_GAP_OUTPUT,
        ),
    ),
    tools=("places_intel", "web_search", "data_fetch", "summarize"),
    expertise=(
        "local market intelligence: competitor mapping in a physical area, "
        "rating and review-volume distributions, review theme mining, and "
        "positioning gaps"
    ),
    # Contrastive against marketing and research: the defining feature is a
    # physical geography and a competitor set with ratings.
    routing_hint=(
        "physical businesses in a specific city, district or neighbourhood — "
        "local competitors, their ratings and reviews, where to open, foot "
        "traffic; NOT online-only markets or campaign planning"
    ),
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    review_criteria=_REVIEW_CRITERIA,
)
