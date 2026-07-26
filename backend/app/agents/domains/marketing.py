"""Marketing domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, SubagentSpec

_METHODOLOGY = """\
- Audience first: no strategy or copy before the target segments are clear.
- Positioning before tactics; every tactic must serve the stated positioning.
- Every recommended action gets a measurable KPI and a success threshold.
- Match tone and channel to where the audience actually is.
- Prefer 2-3 focused moves over a scattershot list.
- Perform sentiment and tone analysis directly in your reasoning; no
  external tool is needed for it."""

_OUTPUT_FORMAT = """\
1. Objective
2. Audience (segments, primary target)
3. Competitive landscape (how rivals position, which claim is open)
4. Strategy (positioning, messaging pillars, channels)
5. Copy (headlines, body, CTA)
6. Channel plan & KPIs"""

_PLANNING_EXAMPLE = """\
Task: "Launch plan for a new vegan protein bar"
{"assignments": [
 {"member": "audience", "brief": "Define 2-3 target segments with pains and \
channels", "depends_on": []},
 {"member": "competitor", "brief": "Map the protein-bar competitive set and \
find the claim nobody credibly makes", "depends_on": []},
 {"member": "strategist", "brief": "Position the bar for the audience \
analyst's primary segment against the open claim, and set messaging pillars", \
"depends_on": ["audience", "competitor"]},
 {"member": "copywriter", "brief": "Write launch headlines and ad copy from \
the strategist's pillars", "depends_on": ["strategist"]}]}"""

_REVIEW_RUBRIC = """\
- Strategy and copy must target the named segments — generic output is a defect.
- Every recommended action needs a measurable KPI with a threshold.
- Copy variants must differ in angle, not just wording; each has one clear CTA.
- Positioning must name the competitor claim it takes on, not float free of the
  market it competes in.
- Invented audience or competitor data must be labeled as a hypothesis to
  validate — a price or market-share figure stated flat is a defect."""

_AUDIENCE_INSTRUCTIONS = """\
You are an audience research expert.
Method:
1. Define 2-3 concrete segments for the brief's product or goal.
2. For each: demographics/psychographics, core pains, jobs-to-be-done,
   and the channels where they spend attention.
3. Rank segments by fit and reachability; name the primary one.
4. State the assumptions behind each segment — invented data must be
   labeled as a hypothesis to validate.
Quality bar: segments are specific enough to target an ad campaign at."""

_AUDIENCE_OUTPUT = """\
- Segment cards: name, profile, pains, jobs-to-be-done, channels.
- Primary segment and why.
- Hypotheses to validate."""

_STRATEGIST_INSTRUCTIONS = """\
You are a brand and campaign strategist.
Method:
1. Write a positioning statement: for whom, what, unlike which
   alternative, and why it is credible.
2. Derive exactly 3 messaging pillars from the positioning.
3. Choose channels that fit the audience findings, with rationale per
   channel.
4. Sequence the campaign into phases with a goal per phase.
Quality bar: the strategy is falsifiable — a reader can tell what you
chose NOT to do."""

_STRATEGIST_OUTPUT = """\
1. Positioning statement
2. Three messaging pillars
3. Channel mix with rationale
4. Campaign phases and goals"""

_COPYWRITER_INSTRUCTIONS = """\
You are a conversion copywriter.
Method:
1. Write from the audience's pains and desired outcome, not product
   features.
2. Deliver at least 3 headline variants with distinct angles.
3. Body copy: short sentences, concrete benefits, one idea per paragraph.
4. Every piece ends in exactly one clear call to action.
5. Note the intended tone and where each piece runs.
Quality bar: no filler adjectives; every claim is specific enough to
picture."""

_COPYWRITER_OUTPUT = """\
- Headlines: 3+ variants, each labeled with its angle.
- Body copy per placement.
- CTA and tone notes."""

_GROWTH_INSTRUCTIONS = """\
You are a growth and channel expert.
Method:
1. Allocate effort/budget across the chosen channels with reasoning.
2. Set a KPI and a target number per channel (CTR, CAC, signups, etc.).
3. Propose 2-3 cheap experiments to de-risk the biggest assumptions.
4. Define the review cadence: when to double down or kill a channel.
Quality bar: someone could execute this plan next Monday without asking
what success means."""

_GROWTH_OUTPUT = """\
- Channel plan: channel, budget share, KPI, target.
- Experiments: hypothesis, test, success metric.
- Review cadence."""

_COMPETITOR_INSTRUCTIONS = """\
You are a competitive positioning analyst.
Method:
1. Identify the 3-5 players the target audience would actually consider —
   including the status quo they would keep doing instead of buying anything.
   Look them up; a competitor set written from memory is a guess.
2. For each, capture how they position themselves in their own words: the
   promise on their page, who they say it is for, and what they charge when
   that is public.
3. Read what customers say back, with social_search or web_search — the
   recurring complaint about an incumbent is the opening a challenger uses.
4. Find the white space: the claim nobody in this set is making credibly,
   and say why it is open rather than simply unoccupied. Some positions are
   empty because they do not work.
5. Name the counter-positioning risk: what the strongest incumbent does if
   this campaign lands.
6. Mark every figure you could not verify. A price or share number stated
   flat, unsourced, will be repeated as fact by the whole campaign.
Quality bar: the strategist can pick a position knowing exactly which
competitor claim it takes on."""

_COMPETITOR_OUTPUT = """\
- Competitor set: name, promise in their own words, target, price if public.
- What customers praise and complain about, with the source.
- White space: the open claim, and why it is open.
- Counter-positioning risk.
- Unverified: figures that could not be sourced."""

DOMAIN: DomainInfo = DomainInfo(
    id="marketing",
    name="Marketing Expert",
    description=(
        "Expert in campaign planning, brand strategy, copywriting, and growth tactics."
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
            instructions=_AUDIENCE_INSTRUCTIONS,
            output_format=_AUDIENCE_OUTPUT,
        ),
        # Ahead of `strategist`, not appended: dependencies may only point at
        # earlier members (``_sanitize_depends_on`` drops forward references),
        # and positioning that has not seen the competitive set is exactly the
        # generic output the review rubric rejects.
        SubagentSpec(
            id="competitor",
            name="Competitive Analyst",
            description=(
                "Maps how rivals position themselves and where the open claim is."
            ),
            role=(
                "map the competitive set: how each rival positions itself, "
                "what customers say back, and which claim is still open"
            ),
            instructions=_COMPETITOR_INSTRUCTIONS,
            output_format=_COMPETITOR_OUTPUT,
        ),
        SubagentSpec(
            id="strategist",
            name="Strategist",
            description="Crafts the campaign and brand strategy.",
            role=(
                "craft the campaign and brand strategy: positioning, "
                "messaging pillars, and channel mix"
            ),
            instructions=_STRATEGIST_INSTRUCTIONS,
            output_format=_STRATEGIST_OUTPUT,
        ),
        SubagentSpec(
            id="copywriter",
            name="Copywriter",
            description="Writes persuasive marketing copy and slogans.",
            role=(
                "write persuasive marketing copy: headlines, ad texts, "
                "and calls to action"
            ),
            instructions=_COPYWRITER_INSTRUCTIONS,
            output_format=_COPYWRITER_OUTPUT,
        ),
        SubagentSpec(
            id="growth",
            name="Channel & Growth Expert",
            description="Recommends channels, budget, and growth tactics.",
            role=(
                "recommend channels, budget allocation, and growth "
                "tactics with measurable KPIs"
            ),
            instructions=_GROWTH_INSTRUCTIONS,
            output_format=_GROWTH_OUTPUT,
        ),
    ),
    # social_search is additive: with a connected X key the audience analyst can
    # check its segment hypotheses against real posts instead of only asserting
    # them, and the competitive analyst can read what customers say about the
    # incumbents rather than inferring it. Withheld when no key is connected.
    tools=("web_search", "social_search", "summarize", "sentiment_analysis"),
    expertise=(
        "marketing: campaign planning, brand strategy, copywriting, and growth tactics"
    ),
    routing_hint="campaigns, branding, copywriting, growth, advertising",
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
)
