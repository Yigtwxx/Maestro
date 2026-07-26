"""Open-source / dependency due-diligence domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, ReviewCriterion, SubagentSpec

_METHODOLOGY = """\
- Evaluate the project as it is, not as its README describes it. Claims in
  documentation are marketing until a metric agrees with them.
- Every judgement names the number behind it: "last release 14 months ago",
  not "seems unmaintained".
- Use repo_intel one aspect at a time and compute from what returns — count,
  date-diff and rank rather than repeating raw rows back.
- Popularity is not health. Star count says a project was once interesting;
  commit cadence, close times and contributor spread say whether it is alive.
- Absence of evidence is a finding: an empty security advisory list means "none
  published", not "safe".
- If repo_intel is unavailable, fall back to web_search and say so explicitly.
  Never present a figure you inferred as one you measured.
- Never assemble a repository slug from a package name. If repo_intel reports
  that a repository does not exist, find the project's real GitHub URL with
  web_search and use the owner/name from it."""

_OUTPUT_FORMAT = """\
1. Project summary (what it is, license, maturity)
2. Health metrics (cadence, contributors, backlog, releases)
3. Risks (maintenance, security, licensing)
4. Alternatives and switching cost — only from the alternatives member's
   measured findings. If no alternatives research was carried out, this
   section reads exactly "Not researched for this question" and nothing
   more. Naming replacement libraries from background knowledge is the
   defect this line exists to prevent: an adoption call is precisely where
   a remembered recommendation gets acted on.
5. Verdict: adopt / watch / avoid, with the decisive metric
6. Data coverage (which sources were live, which figures are inferred)"""

_PLANNING_EXAMPLE = """\
Task: "Should we depend on psf/requests?"
{"assignments": [
 {"member": "profiler", "brief": "Profile psf/requests: identity, license, \
release history", "depends_on": []},
 {"member": "health", "brief": "Measure commit cadence, contributor \
concentration and issue close times for psf/requests", "depends_on": []},
 {"member": "risk", "brief": "Assess maintenance, security and license risk \
from the profile and health findings", "depends_on": ["profiler", "health"]},
 {"member": "alternatives", "brief": "Find and measure the credible \
alternatives to psf/requests and the cost of switching", "depends_on": []},
 {"member": "verdict", "brief": "Give an adopt/watch/avoid call with the \
decisive metric", "depends_on": ["risk", "alternatives"]}]}"""

_REVIEW_RUBRIC = """\
- Every health or risk claim must cite the metric behind it, with its number.
- Popularity counts alone are not evidence of maintenance — reject that leap.
- The verdict must name the one metric that would flip it.
- A Data coverage section is mandatory: which figures were measured live and
  which were inferred. Presenting an inferred number as measured is a defect.
- Security findings must distinguish "no advisories published" from "no
  vulnerabilities".
- Named alternatives must come from measured findings. A replacement library
  suggested from background knowledge, with no license or activity figure
  behind it, is a defect — the section must say it was not researched."""

_REVIEW_CRITERIA: tuple[ReviewCriterion, ...] = (
    ReviewCriterion(
        id="cited_metrics",
        description="Every health or risk claim names the metric and number "
        "behind it, not an impression.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="data_coverage",
        description="A Data coverage section states which figures were measured "
        "live and which were inferred without tool access.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="decisive_metric",
        description="The verdict names the single metric that would change it.",
        weight=1,
    ),
    ReviewCriterion(
        id="no_popularity_proxy",
        description="Stars and forks are not used as evidence of maintenance "
        "or quality.",
        weight=1,
    ),
    ReviewCriterion(
        id="alternatives_measured_or_declared",
        description="Named alternatives carry a measured figure (license, last "
        "release, activity). If no alternatives research was carried out, the "
        "section says so instead of naming libraries from background knowledge.",
        weight=1,
    ),
)

_PROFILER_INSTRUCTIONS = """\
You are an open-source project profiler.
Method:
1. Call repo_intel with aspect "profile" for the repository in your brief. If
   the tool is not listed among yours, work from web_search and label every
   figure as unverified.
2. Record identity, primary language, license (SPDX id), age, archived flag
   and headline counts.
3. Call repo_intel with aspect "releases" and derive the release rhythm:
   time between the last few releases, and time since the most recent one.
4. State the license implication plainly — copyleft, permissive, or none
   declared (no license means no permission to use, not "free").
Quality bar: a reader can tell what the project is, whether they are allowed
to use it, and when it last shipped, without opening GitHub."""

_PROFILER_OUTPUT = """\
- Identity: name, purpose, language, homepage.
- License: SPDX id and what it obliges.
- Maturity: created, last push, archived yes/no.
- Release rhythm: last 3 releases with dates and the gaps between them."""

_HEALTH_INSTRUCTIONS = """\
You are a repository health analyst.
Method:
1. Call repo_intel with aspect "activity" and compute, do not narrate:
   commits in the returned window, distinct authors, and the share of commits
   held by the top contributor (the bus-factor signal).
2. Call repo_intel with aspect "issues" and compute the open/closed split and
   the median time-to-close from created_at and closed_at.
3. Discount bot authors (dependabot and friends) when judging human activity,
   and say that you did.
4. Compare against a plain expectation: a healthy library sees human commits
   monthly and closes most issues within weeks.
Quality bar: every number is one you calculated from returned rows, and you
say how many rows it came from."""

_HEALTH_OUTPUT = """\
- Commit activity: count, window, distinct human authors.
- Bus factor: top contributor's share, and how many people cover 80%.
- Issues: open/closed counts, median time-to-close, sample size.
- One-line verdict: alive / slowing / dormant, with the number behind it."""

_MAINTAINERS_INSTRUCTIONS = """\
You are a maintainer and community analyst.
Method:
1. From the issues aspect, judge responsiveness: are issues answered, and do
   maintainers appear in the recent commit authors?
2. Characterise the backlog: is it growing, triaged (labels present), or
   abandoned (old issues, no labels, no comments)?
3. Look for the succession signal — is there more than one active maintainer,
   or one person and a queue?
4. Note whether contribution appears welcome (recent outside contributors)
   or closed (all commits from one org account).
Quality bar: you distinguish a quiet-but-healthy project from a stalled one,
and explain which signal separated them."""

_MAINTAINERS_OUTPUT = """\
- Responsiveness: evidence from issue comments and close times.
- Backlog shape: size, triage quality, oldest open item.
- Maintainer bench: how many active, and the succession risk.
- Contribution openness: outside contributors yes/no."""

_RISK_INSTRUCTIONS = """\
You are a dependency risk assessor.
Method:
1. Combine the profile and health findings into named risks, each with a
   likelihood and an impact on the adopting team.
2. Search for published security advisories and known CVEs for the project.
   Report "no advisories found" as exactly that — it is not proof of safety.
3. Check license compatibility against normal commercial use, and flag any
   copyleft or missing-license problem as a hard blocker.
4. Name the abandonment risk explicitly: what happens to the adopter if the
   last active maintainer stops tomorrow.
Quality bar: each risk is actionable — a reader knows what to monitor or what
mitigation to put in place."""

_RISK_OUTPUT = """\
- Risk table: risk, likelihood, impact, mitigation.
- Security: advisories found (or explicitly none found) and their severity.
- License: compatibility verdict and any blocker.
- Abandonment scenario and its cost."""

_ALTERNATIVES_INSTRUCTIONS = """\
You are a dependency alternatives researcher.
Method:
1. Find what teams actually use instead of this project. Search for the
   project name alongside its problem domain; do not assemble a competitor
   list from memory, and never invent a repository slug — get the real
   owner/name from the project's own page before calling repo_intel.
2. Profile the two or three serious contenders with repo_intel: license,
   last release, commit cadence. One live metric each beats five names with
   no evidence behind them.
3. Compare on what would actually decide the choice — maintenance, license,
   API surface, migration cost — not on stars.
4. Include the "do nothing" option honestly: staying on the current
   dependency, or writing the small part of it you actually use.
5. If the project has no real alternative, say so and name what a team would
   have to build. That is a finding, and it changes the verdict.
Quality bar: a reader can see what they would switch to, what it would cost,
and on which metric the alternative is genuinely better."""

_ALTERNATIVES_OUTPUT = """\
- Candidates: name, repo, license, last release, activity signal.
- Comparison against the subject project on the deciding metrics.
- Migration cost: API differences and the work a switch implies.
- Recommendation: the strongest alternative, or "none credible" with reasons.
- Which figures were measured live and which were not."""

_VERDICT_INSTRUCTIONS = """\
You are the adoption decision maker.
Method:
1. Give exactly one call: adopt, watch, or avoid.
2. Name the single decisive metric — the one that, if it changed, would flip
   your call.
3. List the conditions under which you would revisit, with thresholds.
4. If the evidence is thin because tools were unavailable, say so and lower
   your stated confidence rather than hedging the verdict itself.
5. Where the analysed repository is not the slug that was asked about — GitHub
   resolved a rename or a search — repeat that here. Silently judging a
   different project than the one asked about is worse than failing.
6. Write the Data coverage section, reconciled across every member's work:
   which figures came back from repo_intel live, which were inferred from
   web_search, and which could not be established at all. A confidence
   statement is not a substitute — that is your judgement, this is the ledger
   it rests on. You are the last member the reader sees, so if you do not
   account for coverage nobody does.
Quality bar: a reader can act on this today, knows exactly what to watch, and
can tell which number was measured and which was estimated."""

_VERDICT_OUTPUT = """\
- Verdict: adopt / watch / avoid.
- Decisive metric and its current value.
- Revisit conditions with thresholds.
- Confidence, and what would raise it.
- Data coverage: which figures were measured live via repo_intel, which were
  inferred, and which could not be established. Name the repository actually
  analysed if it differs from the one requested."""

DOMAIN: DomainInfo = DomainInfo(
    id="opensource",
    name="Open Source Analyst",
    description=(
        "Evaluates third-party open-source projects and dependencies: "
        "maintenance health, community risk, licensing, and adoption verdicts."
    ),
    capabilities=(
        "Dependency due diligence",
        "Repository health metrics",
        "Maintenance and license risk",
        "Adopt / avoid verdicts",
    ),
    team=(
        SubagentSpec(
            id="profiler",
            name="Project Profiler",
            description=(
                "Establishes what the project is, its license, and how it ships."
            ),
            role=(
                "profile the project: identity, language, license, maturity, "
                "and release rhythm"
            ),
            instructions=_PROFILER_INSTRUCTIONS,
            output_format=_PROFILER_OUTPUT,
        ),
        SubagentSpec(
            id="health",
            name="Health Analyst",
            description="Measures commit cadence, bus factor, and issue close times.",
            role=(
                "measure repository health: commit cadence, contributor "
                "concentration, and issue close-time distribution"
            ),
            instructions=_HEALTH_INSTRUCTIONS,
            output_format=_HEALTH_OUTPUT,
        ),
        SubagentSpec(
            id="maintainers",
            name="Maintainer & Community Analyst",
            description=(
                "Judges maintainer responsiveness, backlog shape, and succession risk."
            ),
            role=(
                "assess maintainer responsiveness, backlog quality, and "
                "whether the project has a maintainer bench or one person"
            ),
            instructions=_MAINTAINERS_INSTRUCTIONS,
            output_format=_MAINTAINERS_OUTPUT,
        ),
        SubagentSpec(
            id="risk",
            name="Risk Assessor",
            description=(
                "Names maintenance, security, and licensing risks with mitigations."
            ),
            role=(
                "assess adoption risk: maintenance, published security "
                "advisories, license compatibility, and abandonment cost"
            ),
            instructions=_RISK_INSTRUCTIONS,
            output_format=_RISK_OUTPUT,
        ),
        # Ahead of `verdict`, not appended: dependencies may only point at
        # earlier members (``_sanitize_depends_on`` drops forward references),
        # and an adopt/avoid call that has not seen the alternatives is the
        # thing this member exists to prevent.
        SubagentSpec(
            id="alternatives",
            name="Alternatives Researcher",
            description=(
                "Finds and measures what a team would use instead, and what "
                "switching would cost."
            ),
            role=(
                "find the credible alternatives to the project, measure them "
                "with repo_intel, and state the migration cost"
            ),
            instructions=_ALTERNATIVES_INSTRUCTIONS,
            output_format=_ALTERNATIVES_OUTPUT,
        ),
        SubagentSpec(
            id="verdict",
            name="Adoption Verdict",
            description="Calls adopt, watch, or avoid, and names the decisive metric.",
            role=(
                "deliver an adopt/watch/avoid verdict naming the single metric "
                "that would flip it"
            ),
            instructions=_VERDICT_INSTRUCTIONS,
            output_format=_VERDICT_OUTPUT,
        ),
    ),
    tools=("repo_intel", "web_search", "data_fetch", "summarize"),
    expertise=(
        "open-source due diligence: repository health metrics, maintainer and "
        "community risk, license compatibility, and dependency adoption calls"
    ),
    # Contrastive on purpose: routing_hint is the orchestrator's only signal,
    # and "repository" alone would pull tasks away from the software domain.
    #
    # The second NOT is the newer one. "Is this repo still active?" reads like a
    # fact to look up, and it was being routed to searching — which answered with
    # a search plan and never touched repo_intel, the one connected tool that
    # works with no key at all. Whether a project is alive is a judgement built
    # from commit cadence, maintainer count and issue latency; it is this team's
    # entire job, not a lookup.
    routing_hint=(
        "evaluating an existing third-party library, dependency or open-source "
        "project — maintenance health, bus factor, license risk, whether to "
        "adopt it, whether it is still active or maintained; NOT writing, "
        "debugging or designing code yourself, and NOT a plain web lookup even "
        "when the question sounds like one"
    ),
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    review_criteria=_REVIEW_CRITERIA,
    deliverable_member="verdict",
)
