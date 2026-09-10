"""Sales and revenue domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, ReviewCriterion, SubagentSpec

_METHODOLOGY = """\
- Qualify on observable signals, never on demographics. "Runs a paid ads
  account and posts three job openings for support staff" is a signal;
  "mid-market B2B SaaS" is a category and tells a rep nothing to check.
- A trigger event is what makes now the right week to reach out. Without
  one, the message is an interruption and gets treated as such.
- Objections are the product of the buyer's last experience, not of your
  pitch. Answer each with a specific artefact — a number, a customer, a
  guarantee — and say plainly when you have no answer.
- Disqualify loudly. A cheap "no" this week is worth more than a warm
  maybe that takes a quarter to die.
- Write messages a human would send: one ask, one reason it is relevant to
  that account, no paragraph of praise before it.
- Every step names the next action and who owns it. A sequence that ends
  in "follow up" ends nowhere.
- No invented account facts. A funding round, a headcount or a tech stack
  stated flat and wrong destroys the outreach it was meant to justify."""

_OUTPUT_FORMAT = """\
1. ICP: the qualifying signals, and the disqualifying ones
2. Target accounts and their trigger events, with sources
3. Objections and the evidence that answers each
4. Outreach sequence: step, channel, message, timing
5. Playbook: qualifying questions, next action per outcome
6. Assumptions and what could not be verified"""

_PLANNING_EXAMPLE = """\
Task: "We sell an invoicing tool to freelance designers. How do we sell it?"
{"assignments": [
 {"member": "icp", "brief": "Define the ICP by observable qualifying and \
disqualifying signals", "depends_on": []},
 {"member": "prospect", "brief": "Research target accounts matching those \
signals and their trigger events", "depends_on": ["icp"]},
 {"member": "objections", "brief": "Collect the real objections this buyer \
raises and the evidence that answers each", "depends_on": ["icp"]},
 {"member": "outreach", "brief": "Write the message sequence and pick the \
channel per step", "depends_on": ["prospect", "objections"]},
 {"member": "playbook", "brief": "Assemble the runnable motion with \
qualifying questions and next actions", "depends_on": ["outreach"]}]}"""

_REVIEW_RUBRIC = """\
- ICP criteria must be observable signals a rep could verify before a call;
  a demographic label alone is a defect.
- Every target account must carry a named trigger event with its source.
- Each objection must be answered with a specific artefact, or explicitly
  marked as unanswered.
- Every outreach step must state its channel, its timing, and one ask.
- Every branch of the playbook must end in a named next action, including
  the disqualify branch.
- Unverified account facts must be labeled as assumptions, never stated as
  fact."""

_REVIEW_CRITERIA: tuple[ReviewCriterion, ...] = (
    ReviewCriterion(
        id="observable_signals",
        description="Qualifying criteria are signals a rep could check before "
        "a call. A criterion phrased as a demographic or firmographic "
        "category, with nothing to observe, fails this.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="account_facts_sourced",
        description="Every account fact — funding, headcount, tooling, hiring "
        "— is sourced or labeled an assumption. A fact stated flat without a "
        "source fails this.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="objections_answered",
        description="Each objection is answered with a specific artefact or "
        "openly marked as unanswered, not deflected with reassurance.",
        weight=1,
    ),
    ReviewCriterion(
        id="next_action_named",
        description="Every outcome branch, disqualification included, ends in "
        "a named next action with an owner.",
        weight=1,
    ),
)

_ICP_INSTRUCTIONS = """\
You are an ideal-customer-profile analyst.
Method:
1. Define the profile as a list of observable signals: what the account
   does, publishes, hires for, spends on, or has recently changed. Each
   one must be checkable from outside the company.
2. For every signal, say where a rep looks to verify it — a careers page,
   a pricing page, a public post, a job ad.
3. Write the disqualifying signals too. Knowing who to walk away from is
   the half of an ICP that saves the most time.
4. Rank the signals by how strongly each predicts a close, and say what
   that ranking is based on. If it is a hypothesis, call it one.
5. Name the buyer and the blocker separately: who signs, and who can stop
   it without signing anything.
Quality bar: a rep could sort a list of 50 accounts using your signals
alone, without asking you a single question."""

_ICP_OUTPUT = """\
- Qualifying signals: signal, where to verify it, why it predicts a close.
- Disqualifying signals and the reason each kills the deal.
- Signal ranking, with hypotheses marked as hypotheses.
- Buyer and blocker roles, described by what each cares about."""

_PROSPECT_INSTRUCTIONS = """\
You are an account research analyst.
Method:
1. Find accounts matching the qualifying signals, and check each signal
   rather than assuming it from the company's category.
2. For every account, find the trigger event that makes this month the
   right time: a launch, a funding round, a hiring wave, a public
   complaint, a migration, a leadership change. Date it and source it.
3. If social_search is among your tools, use it to catch what the account
   is saying in public right now — the freshest triggers surface there
   first. Otherwise work from web_search and data_fetch on their own
   pages, and say which you used.
4. Note the person to contact and the reason that specific person, not
   just their title.
5. Mark every fact you could not verify. An account brief that asserts a
   headcount or a stack it never checked will be repeated on a live call.
Quality bar: each account comes with one sentence a rep could open with
that is true and specific to that account this week."""

_PROSPECT_OUTPUT = """\
- Account cards: name, which signals were verified and how.
- Trigger event per account, with a date and a source.
- Contact and why that person.
- Unverified: facts that could not be sourced."""

_OBJECTIONS_INSTRUCTIONS = """\
You are a sales objection analyst.
Method:
1. Collect the objections this buyer actually raises — from reviews, forum
   threads, competitor comparison pages, and public complaints. Quote them
   in the buyer's own words.
2. Sort them: price, trust, switching cost, timing, and authority. Each
   type needs a different answer, and treating them alike is why generic
   rebuttals fail.
3. Answer each with a specific artefact: a number, a named reference, a
   migration path, a trial term, a guarantee.
4. Where there is no honest answer, say so and give the qualifying
   question that surfaces it early instead. An unanswerable objection
   found on call four is a wasted month.
5. Separate the stated objection from the real one where the evidence
   shows a gap — "too expensive" is often "I do not believe the outcome".
Quality bar: a rep hearing any of these live has a specific thing to say
next, or knows to disqualify."""

_OBJECTIONS_OUTPUT = """\
- Objections: quote, type, how often it appears, source.
- The answer to each, naming the artefact it rests on.
- Unanswerable objections and the question that surfaces them early.
- Stated versus real objection, where they differ."""

_OUTREACH_INSTRUCTIONS = """\
You are an outreach sequence writer.
Method:
1. Design a sequence of 4-6 steps. For each: the channel, the day, the
   single ask, and what changes if there is no reply.
2. Write the actual message text, not a description of it. Open on the
   account's trigger event; no praise paragraph, no "hope you're well".
3. Vary the ask down the sequence — a question, then a resource, then a
   specific meeting slot, then a break-up. Repeating one ask five times
   is what gets a sender marked as spam.
4. Pre-empt at most one objection per message, using the objection
   analyst's artefact rather than a claim.
5. State the channel rationale: why this account is reachable there, not
   simply that the channel exists.
Quality bar: every message could be sent as written, to a named account,
without editing a placeholder."""

_OUTREACH_OUTPUT = """\
- Sequence table: step, day, channel, ask.
- Full message text per step, ready to send.
- The break-up message and when it fires.
- Channel rationale per step."""

_PLAYBOOK_INSTRUCTIONS = """\
You are a sales playbook author, and this playbook is what the reader
receives — everything before it was working material.
Method:
1. Open with the motion in one paragraph: who is being sold to, on what
   trigger, through which channel, toward what next step.
2. Reconcile the other members. If the outreach messages target accounts
   the ICP disqualifies, or an objection has no artefact behind it, fix
   the mismatch here and say what you changed.
3. Write the qualifying questions a rep asks on the first call, ordered so
   the fastest disqualifier comes first.
4. Give the next action for every outcome: qualified, not now, wrong
   person, and disqualified. Each with an owner and a timeframe.
5. State the assumptions the motion rests on and the first one to test.
Quality bar: a new rep could run this on Monday with no further briefing,
and would know when to stop."""

_PLAYBOOK_OUTPUT = """\
- The motion in one paragraph.
- Qualifying questions, ordered fastest-disqualifier first.
- Sequence summary with the message per step.
- Next action per outcome, including disqualified, with owner and timing.
- Assumptions and the first one to test."""

DOMAIN: DomainInfo = DomainInfo(
    id="sales",
    name="Sales & Revenue Expert",
    description=(
        "Builds a runnable sales motion: an ICP of observable signals, "
        "trigger-based account research, answered objections, and outreach."
    ),
    capabilities=(
        "ICP and qualification",
        "Account and trigger research",
        "Objection handling",
        "Outreach sequences and playbooks",
    ),
    team=(
        SubagentSpec(
            id="icp",
            name="ICP Analyst",
            description=(
                "Defines the ideal customer by observable qualifying signals."
            ),
            role=(
                "define the ideal customer profile as observable qualifying "
                "and disqualifying signals, not demographics"
            ),
            instructions=_ICP_INSTRUCTIONS,
            output_format=_ICP_OUTPUT,
        ),
        SubagentSpec(
            id="prospect",
            name="Account Researcher",
            description="Researches target accounts and their trigger events.",
            role=(
                "research the specific target accounts and the dated trigger "
                "events worth reaching out on"
            ),
            instructions=_PROSPECT_INSTRUCTIONS,
            output_format=_PROSPECT_OUTPUT,
        ),
        SubagentSpec(
            id="objections",
            name="Objection Analyst",
            description="Collects the real objections and the evidence for each.",
            role=(
                "collect the objections this buyer actually raises and the "
                "specific evidence that answers each"
            ),
            instructions=_OBJECTIONS_INSTRUCTIONS,
            output_format=_OBJECTIONS_OUTPUT,
        ),
        SubagentSpec(
            id="outreach",
            name="Outreach Writer",
            description="Writes the message sequence and picks each channel.",
            role=(
                "write the outreach sequence: the channel, timing and exact "
                "message text for each step"
            ),
            instructions=_OUTREACH_INSTRUCTIONS,
            output_format=_OUTREACH_OUTPUT,
        ),
        SubagentSpec(
            id="playbook",
            name="Playbook Author",
            description="Assembles the runnable motion the reader receives.",
            role=(
                "assemble the runnable sales motion with the qualifying "
                "questions and a next action for every outcome"
            ),
            instructions=_PLAYBOOK_INSTRUCTIONS,
            output_format=_PLAYBOOK_OUTPUT,
        ),
    ),
    # social_search is secondary here: it catches fresh trigger events and
    # objections in public conversation when a key is connected. The motion is
    # built from web_search and data_fetch on the accounts' own pages, so a
    # withheld key costs freshness rather than the playbook.
    tools=(
        "web_search",
        "social_search",
        "data_fetch",
        "summarize",
        "sentiment_analysis",
    ),
    expertise=(
        "sales and revenue: ICP definition by observable signals, account and "
        "trigger research, objection handling, outreach sequences, and the "
        "sales motion that runs them"
    ),
    # Contrastive against the rest of the market group: sales works named
    # accounts one at a time, marketing and ads work an audience in aggregate,
    # brand works reputation, and social measures reaction.
    routing_hint=(
        "selling to specific named accounts: qualifying an ICP, prospect and "
        "trigger research, cold outreach and follow-up sequences, objection "
        "handling, pipeline and the sales motion; NOT broad campaign or "
        "audience planning, NOT paid ad buying, NOT search visibility, NOT "
        "measuring public sentiment about the brand"
    ),
    group="market",
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    review_criteria=_REVIEW_CRITERIA,
    deliverable_member="playbook",
)
