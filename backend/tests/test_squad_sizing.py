"""Squad sizing: the effort caps, the fallback ranking, and the synthesis cap.

These three move together. Raising the caps only helps if the tiers are
reachable and if a bigger team cannot overflow the synthesis prompt, so each
guard here protects one leg of that.

No network I/O — fake adapters stand in for the LLM.
"""

from __future__ import annotations

import json

from app.agents import main_agent
from app.agents.base import AgentContext
from app.agents.prompts import ORCHESTRATOR_SYSTEM
from app.agents.registry import DOMAIN_CATALOG, get_domain_info
from app.core.config import settings
from app.core.constants import (
    MAX_SUBTASKS,
    MAX_SUBTASKS_BY_COMPLEXITY,
    SUBAGENT_MAX_TOKENS,
    SYNTHESIS_MEMBER_OUTPUT_MAX_CHARS,
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
    LLMProvider,
)
from app.services.llm_service import LLMAdapter, LLMResponse

# --- effort caps -----------------------------------------------------------


def test_every_tier_is_reachable_within_the_hard_cap() -> None:
    """A tier above ``MAX_SUBTASKS`` is a number that can never take effect.

    ``_assign`` takes ``min(max_iterations, tier, MAX_SUBTASKS)``, so raising a
    tier without raising the hard cap changes nothing at all.
    """
    for tier, cap in MAX_SUBTASKS_BY_COMPLEXITY.items():
        assert 1 <= cap <= MAX_SUBTASKS, f"{tier} cap {cap} exceeds {MAX_SUBTASKS}"


def test_the_largest_team_can_run_in_full() -> None:
    """The point of the hard cap is to bound a run, not to silence a member.

    A domain whose team is larger than ``MAX_SUBTASKS`` has members that are
    dropped on every single run, in every tier — dead prompt text that still
    ships in the planning roster.
    """
    largest = max(DOMAIN_CATALOG, key=lambda entry: len(entry.team))
    assert len(largest.team) <= MAX_SUBTASKS_BY_COMPLEXITY["complex"], (
        f"{largest.id} has {len(largest.team)} members but the complex tier "
        f"caps at {MAX_SUBTASKS_BY_COMPLEXITY['complex']}"
    )


def test_standard_tier_runs_more_than_half_of_a_typical_team() -> None:
    """``standard`` is the tier nearly every routed prompt lands on.

    It is also the default when the classifier is unsure, so a low value here
    silently halves most squads. Pinned against the median team rather than a
    literal, so the guard follows the catalog if teams grow again.
    """
    sizes = sorted(len(entry.team) for entry in DOMAIN_CATALOG)
    median = sizes[len(sizes) // 2]
    assert MAX_SUBTASKS_BY_COMPLEXITY["standard"] >= median / 2, (
        f"standard tier {MAX_SUBTASKS_BY_COMPLEXITY['standard']} runs less than "
        f"half of a median {median}-member team"
    )


def test_orchestrator_prompt_demonstrates_every_complexity_tier() -> None:
    """A tier with no worked example is one the classifier will not emit.

    The prompt listed all three tiers in its contract but showed only two in
    its examples, and the unshown one was ``complex`` — so the full-team tier
    was unreachable from routing however large the teams grew.
    """
    for tier in MAX_SUBTASKS_BY_COMPLEXITY:
        marker = f'"complexity": "{tier}"'
        assert marker in ORCHESTRATOR_SYSTEM, f"no worked example emits {tier}"


# --- fallback ranking ------------------------------------------------------


def test_fallback_ranks_the_deliverable_member_first() -> None:
    """Planning failed, so nothing else orders this list.

    Every fallback assignment used to share ``rank = 0``; the effort cap's
    stable sort then degraded to team-order slicing, which keeps the
    preparatory member that leads almost every roster.
    """
    info = get_domain_info("seo")
    assignments = main_agent._fallback_assignments(
        info.team, "prompt", info.deliverable_member
    )
    first = min(assignments, key=lambda a: a.rank)
    assert first.member.id == info.deliverable_member, (
        f"expected {info.deliverable_member} ranked first, got {first.member.id}"
    )
    ranks = sorted(a.rank for a in assignments)
    assert ranks == list(range(len(assignments))), f"ranks must be dense: {ranks}"


def test_fallback_without_a_deliverable_keeps_team_order() -> None:
    """Domains that leave ``deliverable_member`` empty keep the old behaviour."""
    info = get_domain_info("software")
    assert not info.deliverable_member, "software is the no-deliverable case"
    assignments = main_agent._fallback_assignments(info.team, "prompt", "")
    by_rank = [a.member.id for a in sorted(assignments, key=lambda a: a.rank)]
    assert by_rank == [member.id for member in info.team], by_rank


def test_truncated_fallback_keeps_the_deliverable_member() -> None:
    """The behaviour the rank exists for, measured at the cap rather than in it."""
    info = get_domain_info("seo")
    assignments = main_agent._fallback_assignments(
        info.team, "prompt", info.deliverable_member
    )
    limit = 2
    keep = {a.member.id for a in sorted(assignments, key=lambda a: a.rank)[:limit]}
    assert info.deliverable_member in keep, (
        f"the cap dropped the member whose output is the answer: {keep}"
    )


# --- the cap must never drop the answer ------------------------------------


class _RosterPlanAdapter(LLMAdapter):
    """Briefs the whole team in team order — what small models actually do.

    The planning prompt asks for members "in order of importance", but a model
    that simply enumerates its roster produces team order, which puts the
    deliverable member last because that is where a domain declares it.
    """

    provider = LLMProvider.OLLAMA

    def __init__(self, domain: str) -> None:
        super().__init__()
        self._info = get_domain_info(domain)

    async def chat(self, messages, *, temperature=0.2, max_tokens=None, **_):  # noqa: ANN001
        if "Main Agent, the manager" in messages[0].content:
            plan = {
                "assignments": [
                    {"member": member.id, "brief": f"do {member.id}", "depends_on": []}
                    for member in self._info.team
                ]
            }
            return LLMResponse(content=json.dumps(plan), tokens_used=1, model="fake")
        return LLMResponse(content="answer", tokens_used=1, model="fake")


async def test_every_tier_keeps_the_deliverable_member() -> None:
    """Every input to the answer and no answer is the worst plan of all.

    Observed on seo at the ``standard`` tier: four specialists survived the cap
    and the strategist that merges them did not, so the run produced four
    partial reports and nothing a reader could act on.
    """
    for entry in DOMAIN_CATALOG:
        if not entry.deliverable_member:
            continue  # software/marketing leave the choice to the planner
        for tier in MAX_SUBTASKS_BY_COMPLEXITY:
            ctx = AgentContext(adapter=_RosterPlanAdapter(entry.id))
            result = await main_agent.run(
                ctx,
                domain=entry.id,
                prompt="task",
                reviewer_enabled=False,
                complexity=tier,
            )
            ran = [(sub.get("data") or {}).get("member") for sub in result["subtasks"]]
            assert entry.deliverable_member in ran, (
                f"{entry.id}/{tier}: the cap dropped {entry.deliverable_member}, "
                f"leaving {ran}"
            )


class _PartialPlanAdapter(LLMAdapter):
    """Briefs a prefix of the team and never names the deliverable member.

    The observed shape: an `opensource` plan of profiler + health + risk with
    no `verdict`. Nothing exceeded the cap, so truncation never ran.
    """

    provider = LLMProvider.OLLAMA

    def __init__(self, domain: str, size: int) -> None:
        super().__init__()
        self._info = get_domain_info(domain)
        self._size = size

    async def chat(self, messages, *, temperature=0.2, max_tokens=None, **_):  # noqa: ANN001
        if "Main Agent, the manager" in messages[0].content:
            picked = [
                member
                for member in self._info.team
                if member.id != self._info.deliverable_member
            ][: self._size]
            plan = {
                "assignments": [
                    {"member": member.id, "brief": f"do {member.id}", "depends_on": []}
                    for member in picked
                ]
            }
            return LLMResponse(content=json.dumps(plan), tokens_used=1, model="fake")
        return LLMResponse(content="answer", tokens_used=1, model="fake")


async def test_a_plan_that_omits_the_deliverable_still_gets_one() -> None:
    """Truncation is not the only way to lose the answer.

    A live `opensource` run planned three members and named no `verdict`, so
    the report carried risks but no adopt/avoid call and no data-coverage
    ledger — sections 5 and 6 of the domain's own output format, both absent.
    Checked at every plan size, because the fix must hold whether there is room
    to append or a member has to be dropped to make room.
    """
    for entry in DOMAIN_CATALOG:
        if not entry.deliverable_member:
            continue
        for tier, cap in MAX_SUBTASKS_BY_COMPLEXITY.items():
            for size in range(1, len(entry.team) + 1):
                ctx = AgentContext(adapter=_PartialPlanAdapter(entry.id, size))
                result = await main_agent.run(
                    ctx,
                    domain=entry.id,
                    prompt="task",
                    reviewer_enabled=False,
                    complexity=tier,
                )
                ran = [
                    (sub.get("data") or {}).get("member") for sub in result["subtasks"]
                ]
                assert entry.deliverable_member in ran, (
                    f"{entry.id}/{tier}/size={size}: no answer-producing member "
                    f"in {ran}"
                )
                assert len(ran) <= min(cap, len(entry.team)), (
                    f"{entry.id}/{tier}/size={size}: {len(ran)} members exceeds "
                    f"the cap {cap}"
                )


async def test_promotion_does_not_exceed_the_cap() -> None:
    """Buying the deliverable a slot must cost one, not add one."""
    entry = get_domain_info("seo")
    ctx = AgentContext(adapter=_RosterPlanAdapter("seo"))
    result = await main_agent.run(
        ctx, domain="seo", prompt="task", reviewer_enabled=False, complexity="standard"
    )
    cap = MAX_SUBTASKS_BY_COMPLEXITY["standard"]
    assert result["metadata"]["subtask_count"] == min(cap, len(entry.team)), result[
        "metadata"
    ]


# --- synthesis input cap ---------------------------------------------------


class _EchoAdapter(LLMAdapter):
    """Records the last user message so a test can measure what was sent.

    ``_synthesize`` streams, and the base ``chat_stream`` degrades a
    non-streaming adapter to a single delta over ``chat`` — so overriding
    ``chat`` alone captures the synthesis prompt.
    """

    provider = LLMProvider.OLLAMA

    def __init__(self) -> None:
        super().__init__()
        self.synthesis_prompt = ""

    async def chat(self, messages, *, temperature=0.2, max_tokens=None, **_):  # noqa: ANN001
        self.synthesis_prompt = messages[-1].content
        return LLMResponse(content="final answer", tokens_used=1, model="fake")


async def test_synthesis_truncates_each_member_output() -> None:
    """A long member deliverable must not push the system prompt out of context.

    Ollama drops the *front* of an over-length prompt, which is where the
    system prompt is — so an uncapped join does not merely cost tokens, it
    removes the instructions synthesis runs on.
    """
    adapter = _EchoAdapter()
    ctx = AgentContext(adapter=adapter)
    long_output = "x" * (SYNTHESIS_MEMBER_OUTPUT_MAX_CHARS * 3)
    answer = await main_agent._synthesize(
        ctx,
        domain="general",
        prompt="task",
        outputs=[("Writer", long_output), ("Checker", long_output)],
        known_gaps=[],
    )

    assert answer == "final answer", answer
    assert adapter.synthesis_prompt, "synthesis prompt was never captured"
    assert len(adapter.synthesis_prompt) < len(long_output) * 2, (
        "member outputs reached synthesis untruncated"
    )
    assert "[truncated]" in adapter.synthesis_prompt, adapter.synthesis_prompt[-200:]


def test_full_team_synthesis_fits_the_local_context_window() -> None:
    """The cap is only correct if MAX_SUBTASKS members still fit.

    Estimated in characters against the configured Ollama context, leaving room
    for the system prompt, the original task and the streamed answer.
    """
    member_chars = MAX_SUBTASKS * SYNTHESIS_MEMBER_OUTPUT_MAX_CHARS
    context_chars = settings.ollama_num_ctx * TOKEN_ESTIMATE_CHARS_PER_TOKEN
    assert member_chars < context_chars / 2, (
        f"{MAX_SUBTASKS} members at {SYNTHESIS_MEMBER_OUTPUT_MAX_CHARS} chars "
        f"({member_chars}) leaves too little of {context_chars} for the prompt"
    )


def test_the_cap_is_below_an_uncapped_member_deliverable() -> None:
    """A cap above what a member can emit is not a cap."""
    uncapped = SUBAGENT_MAX_TOKENS * TOKEN_ESTIMATE_CHARS_PER_TOKEN
    assert SYNTHESIS_MEMBER_OUTPUT_MAX_CHARS < uncapped, "the synthesis cap never binds"


# --- dependency direction --------------------------------------------------


def test_planning_examples_only_depend_on_earlier_members() -> None:
    """``_sanitize_depends_on`` drops forward references silently.

    A planning example that teaches a backwards dependency teaches the model a
    link the pipeline will then discard — the member runs, just without the
    upstream context the example implied it needs. This bit when new members
    were first appended to the end of their team tuples.
    """
    for entry in DOMAIN_CATALOG:
        example = entry.planning_example
        if not example:
            continue
        payload = example[example.index("{", example.index("\n")) :]
        assignments = json.loads(payload)["assignments"]
        position = {member.id: index for index, member in enumerate(entry.team)}
        for item in assignments:
            member_id = item["member"]
            assert member_id in position, f"{entry.id}: unknown member {member_id}"
            for dep in item.get("depends_on", []):
                assert dep in position, f"{entry.id}: unknown dependency {dep}"
                assert position[dep] < position[member_id], (
                    f"{entry.id}: {member_id} depends on {dep}, which runs later "
                    "in team order — the dependency would be dropped"
                )


def test_every_member_is_reachable_from_its_planning_example() -> None:
    """Sanity guard on the roster the example teaches, not on its size."""
    for entry in DOMAIN_CATALOG:
        assert entry.planning_example, f"{entry.id}: no planning example"
        ids = {member.id for member in entry.team}
        cited = set()
        payload = entry.planning_example[
            entry.planning_example.index("{", entry.planning_example.index("\n")) :
        ]
        for item in json.loads(payload)["assignments"]:
            cited.add(item["member"])
        assert cited <= ids, f"{entry.id}: example cites unknown members {cited - ids}"
