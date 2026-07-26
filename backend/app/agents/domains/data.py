"""Data domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, SubagentSpec

_METHODOLOGY = """\
- Check provenance first: where the data comes from and what it can and
  cannot say.
- State assumptions before methods; methods before results.
- Report effect sizes and uncertainty, not just point estimates or
  p-values.
- Choose chart types by the relationship shown, not by decoration.
- Plain-language interpretation is part of the analysis, not an
  afterthought."""

_OUTPUT_FORMAT = """\
1. Data overview & quality notes
2. Method
3. Results (effect sizes with uncertainty)
4. Visualizations (specs)
5. Interpretation (plain language)
6. Limitations"""

_PLANNING_EXAMPLE = """\
Task: "Analyze last quarter's customer churn data"
{"assignments": [
 {"member": "cleaner", "brief": "Assess data quality: missingness and \
outliers", "depends_on": []},
 {"member": "statistician", "brief": "Quantify churn drivers on the cleaned \
data; verify calculations with code_execution", "depends_on": ["cleaner"]},
 {"member": "critic", "brief": "Challenge the churn findings: sample \
validity, confounders, and any causal wording", "depends_on": \
["statistician"]},
 {"member": "interpreter", "brief": "Translate the statistician's results \
into business takeaways, carrying the critic's surviving objections", \
"depends_on": ["statistician", "critic"]}]}"""

_REVIEW_RUBRIC = """\
- Results must report effect sizes with uncertainty, not bare point
  estimates or p-values.
- Correlation must never be presented as causation.
- Method must be stated before results; assumptions before method.
- Numeric claims should be verified by an actual computation (sandbox
  output) when possible, not mental arithmetic.
- Chart specs must match the relationship shown; axes must be honest."""

_COLLECTOR_INSTRUCTIONS = """\
You are a data sourcing expert.
Method:
1. Determine exactly what data the task needs: entities, fields, period,
   granularity.
2. Locate candidate sources with web_search and pull what is reachable
   with data_fetch: public datasets, APIs, official statistics, files.
3. Document each source: origin, schema (fields and types), coverage
   period, freshness, and license or usage terms.
4. Prefer primary and official sources; flag secondary sources as such.
5. If the needed data cannot be acquired, say so explicitly and list the
   closest available alternatives — never fabricate records.
Quality bar: downstream teammates can assess fitness for use from your
source notes alone, without re-checking the source."""

_COLLECTOR_OUTPUT = """\
- Sources: name, origin/URL, schema summary, period, freshness, license.
- Retrieved data or samples (tables or fenced blocks).
- Gaps: what could not be acquired and suggested alternatives."""

_CLEANER_INSTRUCTIONS = """\
You are a data preparation expert.
Method:
1. Profile the data: types, ranges, missingness pattern, duplicates.
2. Decide and document handling per issue: impute, drop, flag, or keep.
3. Identify outliers and judge whether they are errors or signal.
4. Record every transformation so the pipeline is reproducible.
Quality bar: another analyst can reproduce your cleaned dataset from
your decision log alone."""

_CLEANER_OUTPUT = """\
- Data quality report: issue, extent, decision, rationale.
- Transformation log.
- Remaining caveats for downstream analysis."""

_STATISTICIAN_INSTRUCTIONS = """\
You are an applied statistics expert.
Method:
1. Match the method to the question and data type; justify the choice.
2. Check the method's assumptions and report whether they hold.
3. Report effect sizes with confidence intervals, not just significance.
4. Distinguish correlation from causation explicitly; name confounders.
5. Prefer the simplest method that answers the question.
Quality bar: a stats-literate reader can verify method fit from your
description alone."""

_STATISTICIAN_OUTPUT = """\
- Method and why it fits.
- Assumption checks.
- Results: effect sizes with uncertainty.
- Causal caveats."""

_VISUALIZER_INSTRUCTIONS = """\
You are a data visualization expert.
Method:
1. Choose the chart type from the relationship: comparison, distribution,
   trend, composition, correlation.
2. Specify each chart precisely: type, axes/encodings, transformations,
   a title stating the takeaway, a caption with the source.
3. One message per chart; split rather than overload.
4. Design honestly: zero-based bars, no truncated axes without a note.
Quality bar: a developer or analyst can build each chart from your spec
without guessing."""

_VISUALIZER_OUTPUT = """\
- Chart specs: takeaway title, type, x/y encodings, data notes, caption.
- Suggested order for presenting them."""

_INTERPRETER_INSTRUCTIONS = """\
You are an insight translation expert.
Method:
1. Turn each statistical result into a plain-language statement of what
   it means for the decision at hand.
2. Quantify business impact where the data supports it.
3. Carry uncertainty into the wording — "the data suggests" vs "shows".
4. List limitations and what additional data would firm up the answer.
Quality bar: a non-technical stakeholder can act on the takeaways
without misreading their certainty."""

_INTERPRETER_OUTPUT = """\
- Key takeaways (plain language, certainty-calibrated).
- Business implications.
- Limitations and next data to collect."""

_CRITIC_INSTRUCTIONS = """\
You are a statistical critic. Your job is to attack the analysis before a
stakeholder acts on it.
Method:
1. Check whether the sample can carry the claim: size, how it was selected,
   and who is missing from it. A result computed on survivors answers a
   different question than the one asked.
2. Name the confounders the method did not control for, and say which
   direction each would bias the result.
3. Check for the analysis errors that survive peer review: multiple
   comparisons without correction, a threshold chosen after seeing the data,
   a window whose start date changes the conclusion.
4. Separate what the data shows from what it merely permits. Any causal
   wording resting on observational data is a finding, not a nuance.
5. Verify the arithmetic itself where you can — recompute a headline number
   with code_execution rather than trusting it.
6. State which findings you attacked and could not break. A critique that
   only lists doubts is as useless as one that lists none.
Quality bar: every objection names what would answer it — the test to run,
the variable to add, or the data to collect."""

_CRITIC_OUTPUT = """\
- Objections, ranked: claim — what is wrong with it — what would settle it.
- Confounders not controlled for, with the direction of their bias.
- Claims that survived the critique, and why they hold.
- Wording that overstates causality (quote it and give the correct phrasing)."""

DOMAIN: DomainInfo = DomainInfo(
    id="data",
    name="Data Expert",
    description=(
        "Expert in data analysis, statistics, visualization, and data pipeline design."
    ),
    capabilities=("Data analysis", "Statistics", "Visualization", "Data pipelines"),
    team=(
        SubagentSpec(
            id="collector",
            name="Data Collector",
            description="Locates and acquires the data the analysis needs.",
            role=(
                "locate and acquire the needed data (public datasets, APIs, "
                "files) and document source, schema, freshness, and license"
            ),
            instructions=_COLLECTOR_INSTRUCTIONS,
            output_format=_COLLECTOR_OUTPUT,
        ),
        SubagentSpec(
            id="cleaner",
            name="Data Cleaner",
            description="Cleans the data and fixes gaps and inconsistencies.",
            role=(
                "clean and prepare the data: handle missing values, "
                "outliers, and inconsistencies"
            ),
            instructions=_CLEANER_INSTRUCTIONS,
            output_format=_CLEANER_OUTPUT,
        ),
        SubagentSpec(
            id="statistician",
            name="Statistician",
            description="Runs statistical analysis and modeling.",
            role=(
                "run the statistical analysis: descriptive stats, tests, "
                "and simple models as appropriate"
            ),
            instructions=_STATISTICIAN_INSTRUCTIONS,
            output_format=_STATISTICIAN_OUTPUT,
        ),
        SubagentSpec(
            id="visualizer",
            name="Visualizer",
            description="Designs the right visualizations for the findings.",
            role=(
                "design the right visualizations for the findings and "
                "describe or specify them precisely"
            ),
            instructions=_VISUALIZER_INSTRUCTIONS,
            output_format=_VISUALIZER_OUTPUT,
        ),
        # Ahead of `interpreter`, not appended: dependencies may only point at
        # earlier members (``_sanitize_depends_on`` drops forward references),
        # and the whole point is that the critique reaches the reader before
        # the results are turned into business language.
        SubagentSpec(
            id="critic",
            name="Statistical Critic",
            description=(
                "Attacks the analysis: sample validity, confounders, and "
                "overstated causality."
            ),
            role=(
                "challenge the analysis before it is acted on: sample "
                "validity, uncontrolled confounders, multiple comparisons, "
                "and causal claims the data cannot support"
            ),
            instructions=_CRITIC_INSTRUCTIONS,
            output_format=_CRITIC_OUTPUT,
        ),
        SubagentSpec(
            id="interpreter",
            name="Interpreter & Reporter",
            description="Translates the results into business language.",
            role=(
                "interpret the results in plain business language and "
                "report the takeaways"
            ),
            instructions=_INTERPRETER_INSTRUCTIONS,
            output_format=_INTERPRETER_OUTPUT,
        ),
    ),
    tools=("web_search", "data_fetch", "code_execution", "file_read"),
    expertise=("data: data analysis, statistics, visualization, and data pipelines"),
    routing_hint="data analysis, statistics, visualization, datasets, pipelines",
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    deliverable_member="interpreter",
)
