"""Travel and itinerary planning domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, ReviewCriterion, SubagentSpec

_METHODOLOGY = """\
- Plan against the clock, not the map. A day holds three anchors plus travel,
  and a plan that ignores transfer time is a wish list, not an itinerary.
- A rating without a review count is meaningless. Carry both, and treat a 4.9
  over 11 reviews as unproven rather than excellent.
- Geography is a constraint: cluster each day by neighbourhood, because two
  attractions on opposite sides of a city cost an hour that nobody budgeted.
- Check the calendar before the guidebook. Closing days, seasonal hours,
  public holidays and booking windows kill more plans than bad taste does.
- Price things with a date and a currency attached, and say what the estimate
  assumes — season, party size, and how far ahead it is booked.
- Name the entry requirement explicitly: visa, passport validity, transit
  rules. It is the one failure that no amount of good planning recovers from.
- If places_intel is unavailable, work from web_search and say so. Never
  present an inferred rating, price or opening time as a measured one."""

_OUTPUT_FORMAT = """\
1. Trip frame (dates, travellers, pace, and what this trip is actually for)
2. Destination shortlist (what is worth the time, with rating and review count)
3. Logistics (getting there, moving around, entry requirements, closing days)
4. Where to stay (recommended area, why, and what it trades away)
5. Costed estimate (line items, currency, pricing date, assumptions)
6. Day-by-day itinerary (anchors per day, transfer times, fallbacks)
7. Data coverage (which figures were live, sample sizes, what is inferred)"""

_PLANNING_EXAMPLE = """\
Task: "Plan 5 days in Lisbon in October for two people on a mid budget"
{"assignments": [
 {"member": "destination", "brief": "Find what is genuinely worth the time in \
and around Lisbon, with ratings and review counts", "depends_on": []},
 {"member": "logistics", "brief": "Work out flights, in-city transport, \
transfer times, entry requirements and closing days", "depends_on": \
["destination"]},
 {"member": "stays", "brief": "Recommend the neighbourhood to stay in given \
the shortlisted sights and transport", "depends_on": ["destination", \
"logistics"]},
 {"member": "budget", "brief": "Cost the trip line by line in EUR with the \
pricing date and assumptions stated", "depends_on": ["logistics", "stays"]},
 {"member": "itinerary", "brief": "Write the day-by-day plan that respects \
real travel times, plus the Data coverage section", "depends_on": \
["destination", "logistics", "stays", "budget"]}]}"""

_REVIEW_RUBRIC = """\
- Every rating must appear with its review count; a bare rating is a defect.
- Each day must be geographically coherent and name its transfer times; a day
  that crosses the city three times is a defect.
- Opening days, seasonal hours and entry requirements must be stated, not
  assumed.
- Every cost must carry its currency, its pricing date and its assumptions.
- A Data coverage section is mandatory: which figures were live, how many
  places, what was inferred. An inferred price shown as measured is a defect."""

_REVIEW_CRITERIA: tuple[ReviewCriterion, ...] = (
    ReviewCriterion(
        id="data_coverage",
        description="A Data coverage section states which figures came from live "
        "places data and which were inferred.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="rating_with_count",
        description="Every rating is reported alongside its review count, and "
        "low-sample ratings are labeled unproven.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="travel_time_respected",
        description="Each day is clustered by area and names the transfer time "
        "between its anchors, so the plan fits the hours in the day.",
        weight=2,
    ),
    ReviewCriterion(
        id="priced_with_date",
        description="Costs carry a currency, a pricing date and the assumptions "
        "behind them, rather than a bare number.",
        weight=1,
    ),
    ReviewCriterion(
        id="entry_and_hours",
        description="Entry requirements, closing days and seasonal hours are "
        "stated explicitly for anything the plan depends on.",
        weight=1,
    ),
)

_DESTINATION_INSTRUCTIONS = """\
You are a destination scout.
Method:
1. If places_intel is among your tools, call it for the categories in your
   brief, splitting a city into two or three neighbourhood-level searches —
   a city-wide average hides where things actually are. Without it, build the
   shortlist from web_search and say so.
2. Record every candidate with its rating, its review count, its area and its
   category. A rating with no count behind it is not evidence; label it
   unproven rather than quoting it as a score.
3. Separate the things worth a half-day from the things worth twenty minutes,
   and say plainly which famous sights are not worth the queue.
4. Group the shortlist by neighbourhood, because that grouping is what the
   itinerary will be built from.
5. Flag anything seasonal, ticketed in advance, or closed on a weekday.
Quality bar: a resident would recognise this as the real list, and every
entry says how long it actually takes."""

_DESTINATION_OUTPUT = """\
- Shortlist by neighbourhood: name, category, rating with review count, area.
- Time each entry actually takes, and half-day versus quick-stop split.
- Overrated entries named, with the reason.
- Seasonal, ticketed or closed-day flags."""

_LOGISTICS_INSTRUCTIONS = """\
You are a travel logistics planner.
Method:
1. Work out how the traveller arrives and how they move once there: the
   realistic options, the journey time door to door, and the cost band.
2. Build a transfer-time table between the neighbourhoods in the shortlist.
   Airport transfers count; so does the walk at each end.
3. State entry requirements explicitly — visa or visa-free length, passport
   validity, transit rules — and name the nationality the answer assumes.
4. List closing days, seasonal hours, public holidays and booking windows for
   anything the plan will depend on.
5. Name the single most likely thing to go wrong on the ground and the
   fallback for it.
Quality bar: nothing in this section is an assumption a reader has to check
themselves before booking."""

_LOGISTICS_OUTPUT = """\
- Getting there: options, door-to-door time, cost band.
- Local transport: mode, ticket type, what it costs.
- Transfer-time table between the shortlisted areas.
- Entry requirements, with the nationality assumed stated.
- Closing days, seasonal hours and booking windows."""

_STAYS_INSTRUCTIONS = """\
You are an accommodation area advisor.
Method:
1. Recommend an area before a property. The neighbourhood decides the trip:
   it sets every day's first and last thirty minutes, and a good hotel in the
   wrong district is worse than an average one in the right one.
2. Justify the area against the shortlist and the transfer table — proximity
   to the anchors the traveller actually cares about, not to the centre.
3. Name what the area trades away: noise, price, distance to transport, how
   it feels after dark, whether anything is open early.
4. Give one alternative area for a different priority (quieter, cheaper,
   closer to the airport) and say who should pick it.
5. State the nightly price band with the season it applies to, and the
   property type that band buys.
Quality bar: the recommendation names a district a taxi driver would know,
and the trade-off is stated rather than hidden."""

_STAYS_OUTPUT = """\
- Recommended area, with the reason tied to the shortlist and transfers.
- What the area trades away, stated plainly.
- Alternative area and who should choose it instead.
- Nightly price band, season it applies to, and property type."""

_BUDGET_INSTRUCTIONS = """\
You are a trip budget estimator.
Method:
1. Cost the trip line by line: transport there and back, local transport,
   accommodation per night, food per day, tickets, and a contingency line.
2. Attach a currency and a pricing date to every figure, and say whether it
   is per person or for the party. A number without those three is not a
   budget, it is a guess.
3. State the assumptions the estimate rests on: season, how far ahead it is
   booked, the comfort level, and the exchange rate used.
4. Give a range rather than a point where the price genuinely varies, and say
   what moves it to each end.
5. Name the two lines with the most room to cut and what cutting them costs
   in experience.
Quality bar: a reader can change one assumption and see exactly which lines
move."""

_BUDGET_OUTPUT = """\
- Line-item table: item, amount, currency, per person or party.
- Pricing date and exchange rate used.
- Assumptions: season, booking lead time, comfort level.
- Total as a range, with what drives each end.
- The two most cuttable lines and the cost of cutting them."""

_ITINERARY_INSTRUCTIONS = """\
You are a trip itinerary writer, and your output is what the traveller reads
and carries with them.
Method:
1. Reconcile every member's work into one plan: the shortlist, the transfer
   table, the chosen area and the budget must agree with each other. Where
   they conflict, resolve it and say which way you resolved it.
2. Build each day around at most three anchors in one or two adjacent areas,
   with the transfer time written between them and a realistic start hour.
   A day that crosses the city three times is a broken day, not an ambitious
   one.
3. Respect closing days and seasonal hours: place each anchor on a day it is
   actually open, and say what is booked ahead versus walk-in.
4. Give every day one fallback for rain or a closure, and mark what can be
   dropped when the day runs late.
5. Carry the budget total and the entry requirements into the plan so the
   reader does not have to look back for them.
6. Write the Data coverage section, reconciled across every member's work:
   which areas were searched, how many places were found, and which ratings,
   prices and opening times were measured live versus inferred. You are the
   last member the reader sees, so if you do not account for coverage nobody
   does — and a run that fell back to web_search because places_intel was
   unavailable must say so here rather than letting inferred figures read as
   measured ones.
Quality bar: the plan survives contact with a real clock, and a reader can
tell which parts of it were checked and which were estimated."""

_ITINERARY_OUTPUT = """\
- Trip frame: dates, travellers, pace, entry requirements.
- Day-by-day plan: anchors per day, area, start times, transfer times.
- Booked-ahead versus walk-in marked per anchor.
- Per-day fallback and what to drop when running late.
- Budget total carried through, with its currency and pricing date.
- Data coverage: areas searched, place count, which figures were measured
  live and which were inferred."""

DOMAIN: DomainInfo = DomainInfo(
    id="travel",
    name="Travel & Itinerary Planner",
    description=(
        "Plans trips end to end: what is worth seeing, how to move between "
        "it, where to stay, what it costs, and a day-by-day itinerary that "
        "respects real travel times."
    ),
    capabilities=(
        "Destination scouting",
        "Transport and entry logistics",
        "Neighbourhood selection",
        "Trip budgeting",
        "Day-by-day itinerary building",
    ),
    team=(
        SubagentSpec(
            id="destination",
            name="Destination Scout",
            description="Finds what is actually there and worth the time.",
            role=(
                "find what is worth the traveller's time, with each rating "
                "reported alongside its review count and grouped by area"
            ),
            instructions=_DESTINATION_INSTRUCTIONS,
            output_format=_DESTINATION_OUTPUT,
        ),
        SubagentSpec(
            id="logistics",
            name="Logistics Planner",
            description="Works out getting there, moving around, and entry rules.",
            role=(
                "plan transport, transfer times, visa and entry requirements, "
                "and the closing days the plan must work around"
            ),
            instructions=_LOGISTICS_INSTRUCTIONS,
            output_format=_LOGISTICS_OUTPUT,
        ),
        SubagentSpec(
            id="stays",
            name="Accommodation Advisor",
            description="Chooses the area to stay in and says what it trades away.",
            role=(
                "recommend which area to stay in and why, since the "
                "neighbourhood decides the trip more than the hotel does"
            ),
            instructions=_STAYS_INSTRUCTIONS,
            output_format=_STAYS_OUTPUT,
        ),
        SubagentSpec(
            id="budget",
            name="Budget Estimator",
            description="Builds a costed estimate with its assumptions stated.",
            role=(
                "cost the trip line by line with the currency, the pricing "
                "date and every assumption stated"
            ),
            instructions=_BUDGET_INSTRUCTIONS,
            output_format=_BUDGET_OUTPUT,
        ),
        SubagentSpec(
            id="itinerary",
            name="Itinerary Writer",
            description="Writes the day-by-day plan the traveller carries.",
            role=(
                "write the day-by-day itinerary that respects real travel "
                "times, and account for data coverage across the whole run"
            ),
            instructions=_ITINERARY_INSTRUCTIONS,
            output_format=_ITINERARY_OUTPUT,
        ),
    ),
    tools=("places_intel", "web_search", "data_fetch", "summarize"),
    expertise=(
        "travel planning: destination scouting with ratings and review "
        "counts, transport and entry logistics, neighbourhood selection, "
        "trip budgeting, and day-by-day itineraries built around real "
        "transfer times"
    ),
    # Contrastive against local (same group, same places_intel tool, but a
    # business decision about a market) and against research/general/education.
    routing_hint=(
        "planning a trip a person will actually take — where to go, what to "
        "see, how to get around, which area to stay in, what it will cost, "
        "and the day-by-day plan; NOT sizing up the competitors in a "
        "neighbourhood for a business decision, which is local, and NOT a "
        "general write-up about a country or a lesson about a place"
    ),
    group="life",
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    review_criteria=_REVIEW_CRITERIA,
    deliverable_member="itinerary",
)
