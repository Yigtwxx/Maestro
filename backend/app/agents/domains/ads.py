"""Paid advertising and performance marketing domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, ReviewCriterion, SubagentSpec

_METHODOLOGY = """\
- Nothing launches without break-even math. If the allowable CAC is not
  computed from margin and repeat rate first, the budget is a donation.
- Targeting is defined by the signal that reaches people, not by the
  persona that describes them. "Searched a competitor's brand name last
  week" is a signal; "ambitious 25-40 professionals" is not buyable.
- A channel is chosen for the intent it carries, not for its CPM. Search
  captures existing demand; feeds create it. They need different creative
  and different patience.
- Creative is the biggest lever in a feed auction, and angle beats wording.
  Three headlines saying the same thing are one variant, not three.
- Every test states its hypothesis, the metric that decides it, and the
  sample it needs before anyone is allowed to read it.
- Write the kill criteria before spending. A campaign with no stated
  stop-loss will be defended with anecdotes at the end of the month.
- Benchmarks are borrowed until you have your own numbers. Label every
  CPM, CPC and conversion-rate assumption as an assumption, with a source."""

_OUTPUT_FORMAT = """\
1. Objective and the conversion event being bought
2. Audience: the targeting signals and how each is reached
3. Channel mix: what each channel is good at and what it costs
4. Creative: angles, hooks, and the copy per angle
5. Unit economics: allowable CAC, CPM/CPC/CVR assumptions, break-even
6. Launch plan: test structure, budgets, decision dates, kill criteria"""

_PLANNING_EXAMPLE = """\
Task: "We have 5k a month to advertise a 40/month project tool. Where?"
{"assignments": [
 {"member": "audience", "brief": "Define the targeting signals that reach \
buyers of a project tool", "depends_on": []},
 {"member": "channels", "brief": "Compare search, feed and community \
channels for this intent and price them", "depends_on": ["audience"]},
 {"member": "creative", "brief": "Write distinct ad angles and copy per \
channel", "depends_on": ["audience"]},
 {"member": "budget", "brief": "Compute allowable CAC and break-even from \
the 40/month price with code_execution", "depends_on": ["channels"]},
 {"member": "plan", "brief": "Assemble the launch plan with the test matrix \
and kill criteria", "depends_on": ["creative", "budget"]}]}"""

_REVIEW_RUBRIC = """\
- An allowable CAC computed from price, margin and repeat rate is mandatory;
  a budget with no break-even math is a defect.
- Every CPM, CPC and conversion-rate figure must be labeled as a benchmark
  assumption with a source, or as measured.
- Targeting must be expressed as signals that can actually be bought on the
  named channel, not as a persona description.
- Ad angles must differ in claim, not only in wording; each names its hook.
- Every test states its decision metric, the sample it needs, and the kill
  criterion with a number and a date."""

_REVIEW_CRITERIA: tuple[ReviewCriterion, ...] = (
    ReviewCriterion(
        id="break_even_math",
        description="An allowable CAC is computed from price, margin and "
        "repeat rate, and the spend plan is checked against it. A budget "
        "allocation with no break-even calculation fails this.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="benchmarks_labeled",
        description="Every CPM, CPC and conversion-rate number is labeled as "
        "a sourced benchmark assumption or as measured. A platform cost "
        "stated flat as fact fails this.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="buyable_targeting",
        description="Targeting is expressed as signals purchasable on the "
        "named channel, not as a persona paragraph.",
        weight=1,
    ),
    ReviewCriterion(
        id="kill_criteria",
        description="Each test carries a decision metric, a required sample "
        "and a kill criterion with a number and a date.",
        weight=1,
    ),
)

_AUDIENCE_INSTRUCTIONS = """\
You are a paid-media audience strategist.
Method:
1. Name who is being bought, then immediately convert it into targeting
   signals: keywords and their intent, interests, lookalike seeds,
   retargeting windows, job or industry fields, placements.
2. For each signal, say which channel can actually buy it. A signal no
   platform sells is a persona, not targeting.
3. Estimate reachable size per signal and label the estimate as an
   estimate. Say when a segment is too small to leave the learning phase.
4. Separate cold, warm and retargeting audiences, since they need
   different creative and carry very different costs.
5. Name the exclusions: existing customers, recent converters, obvious
   mismatches. Unexcluded spend is the most common silent waste.
Quality bar: someone could open an ad manager and build these audiences
without inventing a single field."""

_AUDIENCE_OUTPUT = """\
- Targeting signals: signal, the channel that sells it, reachable size.
- Cold / warm / retargeting split with the intent behind each.
- Exclusions and why.
- Size estimates, marked as estimates."""

_CHANNELS_INSTRUCTIONS = """\
You are a paid channel strategist.
Method:
1. Shortlist 3-4 channels and say what each is genuinely good at for this
   objective — demand capture, demand creation, or retargeting reach.
2. Price each: typical CPM or CPC range and the conversion rate you are
   assuming. Look these up; label every figure as a benchmark with its
   source and date, never as this account's own number.
3. State the minimum viable budget per channel — below it, the algorithm
   never leaves learning and the test proves nothing.
4. Name the friction each channel adds: creative volume needed, approval
   policy risk, tracking loss, auction seasonality.
5. Recommend an allocation with a reason per line, and name the channel
   you deliberately did not use.
Quality bar: the budget member can build a CAC model from your numbers
without asking what any of them assume."""

_CHANNELS_OUTPUT = """\
- Channel table: channel, what it is good at, CPM/CPC range, assumed CVR.
- Source and date for every benchmark figure.
- Minimum viable budget per channel.
- Recommended allocation with a reason per line, and the channel skipped."""

_CREATIVE_INSTRUCTIONS = """\
You are a performance creative strategist.
Method:
1. Write 3-5 distinct angles, each a different claim about why this
   matters — pain, status quo cost, speed, proof, or objection reversal.
   Two ways of phrasing one claim count as one angle.
2. For each angle: the hook in the first three seconds or the first five
   words, the body, and one call to action.
3. Match the format to the placement — search text, static feed, short
   video, carousel — and say what the visual has to show.
4. State the landing-page promise each angle makes. An ad whose promise
   is not on the page converts once and never again.
5. Flag policy risk: claims about health, money, weight or guarantees get
   ads rejected, and a rejected set spends nothing while looking active.
Quality bar: each angle is testable against the others, because they
disagree about why someone should buy."""

_CREATIVE_OUTPUT = """\
- Angle cards: angle name, the claim, hook, body, CTA.
- Format and placement per angle, with the visual requirement.
- The landing-page promise each angle depends on.
- Policy risk notes."""

_BUDGET_INSTRUCTIONS = """\
You are a paid-media unit economics analyst.
Method:
1. Compute the allowable CAC from price, gross margin, expected repeat
   purchases and payback window. State each input; if one is unknown, say
   so and show the range instead of picking a flattering number.
2. Use code_execution for the arithmetic and show the model: from CPM or
   CPC through click-through, conversion rate and average order value to
   cost per acquisition. Do not do multi-step math in prose.
3. Give the break-even: the conversion rate, or the CPC, at which the
   channel stops paying for itself.
4. Run a downside case at roughly half the assumed conversion rate. If it
   only works at the optimistic input, that is the finding.
5. Allocate the budget across test and scale, and state how much must be
   spent before any number is readable.
Quality bar: every figure traces to a stated input, and a reader can see
which single assumption the whole plan rests on."""

_BUDGET_OUTPUT = """\
- Inputs: price, margin, repeat rate, payback window, with sources.
- The model, with the computed steps shown.
- Allowable CAC, projected CAC, and break-even CPC or CVR.
- Downside case at halved conversion, and the load-bearing assumption.
- Budget split between test and scale, with the readable-sample threshold."""

_PLAN_INSTRUCTIONS = """\
You are a paid launch planner, and this plan is what the reader receives —
everything before it was working material.
Method:
1. Open with the objective, the conversion event being bought, and the
   allowable CAC the whole plan is judged against.
2. Reconcile the other members. If the recommended allocation breaches the
   allowable CAC, or an angle targets an audience no channel can buy, fix
   it here and say what you changed.
3. Lay out the test structure: which variable each cell isolates, the
   budget per cell, the decision metric, and the date it is read.
4. Write the kill criteria as numbers and dates — spend without a
   conversion, CAC above allowable after a stated sample, a rejected
   creative set. Then write the scale criteria the same way.
5. Give week one as an ordered checklist, including tracking and
   exclusions, which are what silently invalidate a launch.
6. State what you would stop the whole plan for.
Quality bar: someone could launch this on Monday and would know, on a
stated date, whether to double the budget or turn it off."""

_PLAN_OUTPUT = """\
- Objective, conversion event, and allowable CAC.
- Test matrix: cell, variable isolated, budget, decision metric, read date.
- Kill criteria and scale criteria, each a number with a date.
- Week-one checklist, tracking and exclusions included.
- What would stop the whole plan."""

DOMAIN: DomainInfo = DomainInfo(
    id="ads",
    name="Paid Ads & Performance Marketer",
    description=(
        "Plans paid acquisition: buyable targeting, a priced channel mix, "
        "distinct ad angles, and break-even math with kill criteria."
    ),
    capabilities=(
        "Paid targeting and audiences",
        "Channel mix and media costs",
        "Ad creative angles",
        "CAC, break-even and test design",
    ),
    team=(
        SubagentSpec(
            id="audience",
            name="Audience Strategist",
            description="Turns the buyer into signals a platform can actually buy.",
            role=(
                "define the targeting and the signals that reach it, naming "
                "the channel that sells each signal"
            ),
            instructions=_AUDIENCE_INSTRUCTIONS,
            output_format=_AUDIENCE_OUTPUT,
        ),
        SubagentSpec(
            id="channels",
            name="Channel Strategist",
            description="Prices the channel mix and says what each is good at.",
            role=(
                "compare the channel mix: what each is genuinely good at, its "
                "benchmark costs, and the minimum viable budget"
            ),
            instructions=_CHANNELS_INSTRUCTIONS,
            output_format=_CHANNELS_OUTPUT,
        ),
        SubagentSpec(
            id="creative",
            name="Creative Strategist",
            description="Writes the ad angles and the copy for each.",
            role=(
                "write distinct ad angles and the hook, body and CTA for "
                "each, matched to placement"
            ),
            instructions=_CREATIVE_INSTRUCTIONS,
            output_format=_CREATIVE_OUTPUT,
        ),
        SubagentSpec(
            id="budget",
            name="Unit Economics Analyst",
            description="Computes allowable CAC, media assumptions and break-even.",
            role=(
                "compute the unit economics — allowable CAC, CPM/CPC and "
                "conversion assumptions, break-even and the downside case"
            ),
            instructions=_BUDGET_INSTRUCTIONS,
            output_format=_BUDGET_OUTPUT,
        ),
        SubagentSpec(
            id="plan",
            name="Launch Planner",
            description="Assembles the launch plan the reader receives.",
            role=(
                "assemble the launch plan with the test structure, the "
                "decision dates and the kill criteria"
            ),
            instructions=_PLAN_INSTRUCTIONS,
            output_format=_PLAN_OUTPUT,
        ),
    ),
    # code_execution is here for the budget member specifically: CAC, break-even
    # and a halved-conversion downside are multi-step arithmetic, and a small
    # model doing that in prose gets it wrong in a way that reads as confident.
    tools=("web_search", "data_fetch", "code_execution", "summarize"),
    expertise=(
        "paid advertising and performance marketing: buyable targeting, "
        "channel mix and media costs, ad creative angles, CAC and break-even "
        "math, and test structures with kill criteria"
    ),
    # Contrastive against the rest of the market group: ads is money into an
    # auction, seo is unpaid search visibility, marketing is the wider campaign
    # and positioning, content writes the published piece.
    routing_hint=(
        "buying attention with money: paid ad campaigns, targeting and "
        "audiences, ad creative and angles, CPM/CPC/CAC math, budget "
        "allocation, A/B test structure and kill criteria; NOT unpaid organic "
        "search visibility, NOT overall campaign or brand strategy, NOT "
        "writing an article or a published piece"
    ),
    group="market",
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    review_criteria=_REVIEW_CRITERIA,
    deliverable_member="plan",
)
