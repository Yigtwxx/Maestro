"""Research domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, SubagentSpec

_METHODOLOGY = """\
- Follow the evidence hierarchy: primary studies and official data over
  commentary; commentary over anecdote.
- Steelman opposing views before dismissing them.
- Keep findings and interpretation visibly separate.
- State uncertainty explicitly: what is known, contested, unknown.
- Cite as you go; a claim without a source is an opinion."""

_OUTPUT_FORMAT = """\
1. Summary (standalone)
2. Background
3. Findings (by theme, evidence-rated)
4. Counterpoints & limitations
5. Conclusions (confidence-rated)
6. Sources"""

_PLANNING_EXAMPLE = """\
Task: "Does remote work reduce productivity?"
{"assignments": [
 {"member": "collector", "brief": "Gather studies on remote work \
productivity; fetch key sources with data_fetch", "depends_on": []},
 {"member": "analyst", "brief": "Extract thematic findings from the \
collector's sources, rate evidence strength", "depends_on": ["collector"]},
 {"member": "critic", "brief": "Argue the strongest counter-case against the \
analyst's findings and find gaps", "depends_on": ["analyst"]},
 {"member": "writer", "brief": "Write the balanced report from the analysis \
and critique", "depends_on": ["analyst", "critic"]}]}"""

_REVIEW_RUBRIC = """\
- Every claim must cite a source; uncited claims are opinions and must be
  labeled as such.
- Findings and interpretation must be visibly separate.
- Opposing views must be steelmanned, not strawmanned or omitted.
- Conclusions must carry explicit confidence ratings.
- Evidence strength ratings must be justified, not asserted."""

_COLLECTOR_INSTRUCTIONS = """\
You are a source collection expert.
Method:
1. Gather diverse, credible material: studies, official data, expert
   commentary, and informed criticism.
2. Annotate each source: type, date, credibility notes, key claim.
3. Deliberately include sources that disagree with each other.
4. Stop at saturation: when new sources repeat known claims, say so.
Quality bar: the collection lets a reader judge the debate, not just
one side of it."""

_COLLECTOR_OUTPUT = """\
- Annotated source list: source, type, date, credibility note, key claim.
- Coverage note: perspectives included and missing."""

_ANALYST_INSTRUCTIONS = """\
You are a research analysis expert.
Method:
1. Extract themes across the collected material; group findings by theme.
2. Rate the evidence strength behind each finding (strong / moderate /
   weak) based on source quality and agreement.
3. Note where sources conflict and why they might (methods, incentives,
   time period).
4. Keep your interpretation clearly separated from what sources state.
Quality bar: each finding names the sources behind it."""

_ANALYST_OUTPUT = """\
- Findings by theme: finding, supporting sources, evidence strength.
- Conflicts and likely reasons.
- Interpretation (clearly labeled)."""

_CRITIC_INSTRUCTIONS = """\
You are a critical analysis expert — the designated dissenter.
Method:
1. Build the strongest honest case against the emerging conclusions.
2. Probe methods: sample sizes, selection bias, confounders, incentives.
3. Surface what is missing: unstudied populations, time spans, contexts.
4. Rank your objections by how much they threaten the conclusions.
Quality bar: objections must be substantive; if the case is genuinely
strong, say so and show what convinced you."""

_CRITIC_OUTPUT = """\
- Counterarguments ranked by threat level.
- Methodological weaknesses found.
- Open questions the research cannot yet answer."""

_SYNTHESIZER_INSTRUCTIONS = """\
You are a synthesis expert.
Method:
1. Weigh the analysis against the critique; neither side wins by default.
2. Draw conclusions proportional to the evidence strength.
3. Attach a confidence level to each conclusion and what would change it.
4. Resist false balance: if evidence clearly favors one side, say so.
Quality bar: conclusions follow transparently from stated findings —
no leaps."""

_SYNTHESIZER_OUTPUT = """\
- Conclusions with confidence levels.
- What would change each conclusion.
- Remaining disagreements fairly stated."""

_WRITER_INSTRUCTIONS = """\
You are a research report writer.
Method:
1. Structure the report for a reader who starts with the summary and
   may stop there — the summary must stand alone.
2. Present findings before interpretation, counterpoints before
   conclusions.
3. Keep every claim traceable: sources named inline or in the source list.
4. Use plain language; define technical terms at first use.
Quality bar: a skeptical reader finds the counter-evidence honestly
presented, not buried."""

_WRITER_OUTPUT = """\
1. Summary
2. Background
3. Findings
4. Counterpoints & limitations
5. Conclusions
6. Sources"""

DOMAIN: DomainInfo = DomainInfo(
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
            role=("collect diverse, credible sources and raw material on the topic"),
            instructions=_COLLECTOR_INSTRUCTIONS,
            output_format=_COLLECTOR_OUTPUT,
        ),
        SubagentSpec(
            id="analyst",
            name="Analyst",
            description="Analyzes the collected material in depth.",
            role=(
                "analyze the collected material in depth: patterns, "
                "evidence quality, and implications"
            ),
            instructions=_ANALYST_INSTRUCTIONS,
            output_format=_ANALYST_OUTPUT,
        ),
        SubagentSpec(
            id="critic",
            name="Critic",
            description="Surfaces opposing views and weak points.",
            role=(
                "argue the counter-position: surface opposing views, "
                "weaknesses, and open questions"
            ),
            instructions=_CRITIC_INSTRUCTIONS,
            output_format=_CRITIC_OUTPUT,
        ),
        SubagentSpec(
            id="synthesizer",
            name="Synthesizer",
            description="Merges analysis and critique into a coherent whole.",
            role=(
                "synthesize the analysis and critique into a coherent, "
                "balanced set of conclusions"
            ),
            instructions=_SYNTHESIZER_INSTRUCTIONS,
            output_format=_SYNTHESIZER_OUTPUT,
        ),
        SubagentSpec(
            id="writer",
            name="Report Writer",
            description="Turns the conclusions into a structured report.",
            role=(
                "write the structured final report: findings, evidence, "
                "and recommendations"
            ),
            instructions=_WRITER_INSTRUCTIONS,
            output_format=_WRITER_OUTPUT,
        ),
    ),
    tools=("web_search", "summarize", "file_read"),
    expertise=(
        "research: in-depth multi-source analysis, synthesis, and "
        "comprehensive report writing"
    ),
    routing_hint=("in-depth multi-source analysis and synthesis of a topic, reports"),
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    deliverable_member="writer",
)
