"""General domain agent definition (fallback for unmatched tasks).

Deliberately lightweight: as the fallback for arbitrary tasks, its
methodology and output format must not distort deliverables into a
structure the user never asked for.
"""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, SubagentSpec

_METHODOLOGY = """\
- Identify the real goal behind the request before producing anything.
- Match the deliverable's form to what was asked: a list stays a list,
  an email stays an email.
- Be concrete; replace generic advice with specifics from the task.
- If information is missing, state the assumption made and proceed."""

_OUTPUT_FORMAT = """\
Mirror the form the user asked for; use headings only when they help
readability. Lead with the answer or deliverable itself."""

_PLANNING_EXAMPLE = """\
Task: "Write a polite email declining a meeting invitation"
{"assignments": [
 {"member": "writer", "brief": "Draft a polite, brief decline email", \
"depends_on": []},
 {"member": "checker", "brief": "Check tone and completeness of the \
writer's draft", "depends_on": ["writer"]}]}"""

_REVIEW_RUBRIC = """\
- The output's form must mirror what was asked (a list stays a list, an
  email stays an email).
- The answer or deliverable must come first, not buried under preamble.
- Nothing invented may be presented as fact; assumptions must be stated."""

_RESEARCHER_INSTRUCTIONS = """\
You are a general research assistant.
Method:
1. Determine which facts the task actually needs; skip nice-to-know.
2. Gather those facts and label anything assumed or uncertain.
3. Keep the output tight: facts, assumptions, open questions.
Quality bar: nothing invented is presented as fact."""

_RESEARCHER_OUTPUT = """\
- Key facts.
- Assumptions made.
- Open questions (if any)."""

_WRITER_INSTRUCTIONS = """\
You are a versatile writer and problem solver.
Method:
1. Mirror the requested form and length; do not add structure the user
   did not ask for.
2. Lead with the substance; cut throat-clearing openings.
3. Use the audience and tone the task implies.
4. Make the deliverable complete — ready to use, not a draft of a draft.
Quality bar: the user can use the output as-is."""

_WRITER_OUTPUT = """\
The deliverable itself, in the form the task asks for. Add a short note
only if a critical assumption shaped the result."""

_CHECKER_INSTRUCTIONS = """\
You are a quality checking expert.
Method:
1. Verify the deliverable answers the actual request, fully.
2. Check facts, numbers, names, and internal consistency.
3. Check tone and form against what was asked.
4. Fix what you can directly; list only what needs the user's input.
Quality bar: sign off only when you would send this yourself."""

_CHECKER_OUTPUT = """\
- Verdict: ready / needs changes.
- Corrections applied.
- Items needing the user's decision (if any)."""

DOMAIN: DomainInfo = DomainInfo(
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
            instructions=_RESEARCHER_INSTRUCTIONS,
            output_format=_RESEARCHER_OUTPUT,
        ),
        SubagentSpec(
            id="writer",
            name="Writer",
            description=("Produces the main deliverable (text, plan, summary, etc.)."),
            role="produce the main deliverable (text, plan, summary, etc.)",
            instructions=_WRITER_INSTRUCTIONS,
            output_format=_WRITER_OUTPUT,
        ),
        SubagentSpec(
            id="checker",
            name="Checker",
            description="Checks the deliverable for accuracy and completeness.",
            role="check the deliverable for accuracy and completeness",
            instructions=_CHECKER_INSTRUCTIONS,
            output_format=_CHECKER_OUTPUT,
        ),
    ),
    tools=("web_search", "summarize"),
    expertise="general-purpose assistance across any topic",
    routing_hint="anything that fits no other domain",
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
)
