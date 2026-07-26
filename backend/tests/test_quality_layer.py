"""Quality layer (Backend v2 §4.6): deterministic validators, effort scaling,
token budget guard, and step-boundary quota.

No network I/O — fake adapters and an in-memory DB stand in for the LLM and
Postgres.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.agents import main_agent, orchestrator, validators
from app.agents.base import AgentContext, SubagentResult
from app.agents.prompts import (
    GROUNDING_POLICY,
    SUBAGENT_SYSTEM,
    SUBAGENT_TOOLS_RULE,
)
from app.agents.registry import get_domain_info
from app.agents.schemas import RouteDecision
from app.core.constants import (
    TASK_TOKEN_BUDGET_DEFAULT,
    LLMProvider,
    SubagentStatus,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.subscription import Subscription
from app.models.user import User
from app.services import quota_service, usage_service
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse, TokenMeter

SOFTWARE = get_domain_info("software")


class _PlanAdapter(LLMAdapter):
    """Returns a two-member software plan for planning; generic text otherwise.

    Counts calls so a test can prove the reviewer's LLM never ran.
    """

    provider = LLMProvider.OLLAMA

    def __init__(self, per_call_tokens: int = 7) -> None:
        super().__init__()
        self.calls = 0
        self._tokens = per_call_tokens

    async def chat(self, messages, *, temperature=0.2, max_tokens=None, **_):  # noqa: ANN001
        self.calls += 1
        system = messages[0].content
        if "Main Agent, the manager" in system:
            content = json.dumps(
                {
                    "assignments": [
                        {"member": "coder", "brief": "Write function"},
                        {"member": "tester", "brief": "Add tests"},
                    ]
                }
            )
        else:
            content = "Here is the output:\n```python\nx = 1\n```"
        return LLMResponse(content=content, model="fake", tokens_used=self._tokens)


# --- deterministic validators ---------------------------------------------


def test_nonempty_validator_rejects_short_output() -> None:
    hints = validators.validate("general", None, "too short")
    assert hints, "a trivially short output must be rejected"


def test_validators_pass_on_a_real_deliverable() -> None:
    output = "This is a full, complete answer to the subtask at hand."
    assert validators.validate("general", None, output) == []


def test_code_blocks_validator_flags_software_without_code() -> None:
    prose = "A perfectly long explanation with no code block whatsoever here."
    hints = validators.validate("software", None, prose)
    assert any("code block" in h for h in hints), hints


def test_json_validator_flags_data_without_json() -> None:
    prose = "A long data description that contains no JSON object at all here."
    hints = validators.validate("data", None, prose)
    assert any("JSON" in h for h in hints), hints


def test_uncertainty_validator_passes_balanced_markers() -> None:
    output = "The project was archived [? in late 2023 ?] and is unmaintained now."
    assert validators.validate("general", None, output) == []


def test_uncertainty_validator_flags_unclosed_marker() -> None:
    output = "The project was archived [? in late 2023 and is unmaintained now."
    hints = validators.validate("general", None, output)
    assert any("never closed" in h for h in hints), hints


def test_uncertainty_validator_ignores_code_spans() -> None:
    """``[?`` is a regex character class; a software deliverable may contain it."""
    fenced = (
        "Strip the optional marker with this pattern:\n"
        "```python\n"
        'PATTERN = re.compile(r"[?!]+")\n'
        "```\n"
        "It matches a run of `[?]` punctuation."
    )
    assert validators.validate("software", None, fenced) == []


def test_uncertainty_validator_ignores_a_stray_close() -> None:
    """Only open-without-close fires; a lone ``?]`` is harmless punctuation."""
    output = "The maintainer asked what the plan was ?] and never got an answer."
    assert validators.validate("general", None, output) == []


async def test_reviewer_short_circuits_without_llm_on_validator_failure() -> None:
    from app.agents import reviewer

    adapter = _PlanAdapter()
    ctx = AgentContext(adapter=adapter)
    result = SubagentResult(status=SubagentStatus.SUCCESS, data={"output": "nope"})
    verdict = await reviewer.review(ctx, domain="general", subtask="s", result=result)

    assert verdict.approved is False, "a failing validator must reject"
    assert adapter.calls == 0, "the reviewer LLM must not run when a validator fails"


# --- effort scaling --------------------------------------------------------


def test_route_decision_carries_complexity() -> None:
    decision = RouteDecision.model_validate(
        {"domain": "software", "complexity": "complex"}
    )
    assert decision.complexity == "complex"


def test_route_decision_normalizes_unknown_complexity() -> None:
    decision = RouteDecision.model_validate(
        {"domain": "software", "complexity": "gigantic"}
    )
    assert decision.complexity == "standard", "unknown tier -> standard"


async def test_simple_complexity_runs_one_member_and_skips_reviewer() -> None:
    # If the reviewer ran, the adapter's call count would exceed plan+subagent.
    adapter = _PlanAdapter()
    ctx = AgentContext(adapter=adapter)
    result = await main_agent.run(
        ctx,
        domain="software",
        prompt="task",
        reviewer_enabled=True,
        complexity="simple",
    )
    assert result["metadata"]["subtask_count"] == 1, "simple -> exactly one member"
    # plan (1) + single subagent (1) = 2 calls; a reviewer pass would add more.
    assert adapter.calls == 2, (
        f"reviewer must be skipped for simple; got {adapter.calls}"
    )


async def test_route_wrapper_still_returns_domain_string() -> None:
    adapter = _PlanAdapter()
    ctx = AgentContext(adapter=adapter)
    domain = await orchestrator.route(ctx, "do something")
    assert isinstance(domain, str) and domain, domain


# --- token budget guard ----------------------------------------------------


async def test_budget_guard_skips_subagents_when_exhausted() -> None:
    meter = TokenMeter(_PlanAdapter(per_call_tokens=100))
    ctx = AgentContext(adapter=meter, token_budget=1)  # trips right after planning
    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )
    assert result["all_subtasks_failed"] is True, "no subagent should have run"
    errors = [f["error"] for f in result["failed_subtasks"]]
    assert errors and all("budget exhausted" in e for e in errors), errors


async def test_subagent_forces_final_answer_when_budget_exhausted() -> None:
    from app.agents import subagent

    adapter = _PlanAdapter()
    meter = TokenMeter(adapter)
    meter.total_tokens = 100  # the task already burned more than the cap
    ctx = AgentContext(adapter=meter, token_budget=5)
    result = await subagent.run_subtask(
        ctx, domain="software", member=SOFTWARE.team[1], brief="b", index=0
    )
    assert result.status == SubagentStatus.SUCCESS
    assert adapter.calls == 1, (
        "a budget-exhausted subagent makes exactly one final call"
    )


async def test_no_budget_means_unbounded() -> None:
    adapter = _PlanAdapter()
    ctx = AgentContext(adapter=adapter)  # token_budget defaults to None
    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )
    assert result["all_subtasks_failed"] is False
    assert result["metadata"]["subtask_count"] == 2


# --- subagent summaries ----------------------------------------------------


def test_teammate_note_uses_summary_for_large_output() -> None:
    from app.core.constants import UPSTREAM_OUTPUT_MAX_CHARS

    assignment = main_agent.Assignment(member=SOFTWARE.team[0], brief="b")
    big = "x" * (UPSTREAM_OUTPUT_MAX_CHARS + 100)
    result = SubagentResult(
        status=SubagentStatus.SUCCESS,
        data={"output": big, "summary": "concise summary"},
    )
    note = main_agent._teammate_note(assignment, result)
    assert note == "concise summary", "a large deliverable is handed on as its summary"


def test_teammate_note_passes_short_output_through() -> None:
    assignment = main_agent.Assignment(member=SOFTWARE.team[0], brief="b")
    result = SubagentResult(
        status=SubagentStatus.SUCCESS,
        data={"output": "short answer", "summary": "sum"},
    )
    assert main_agent._teammate_note(assignment, result) == "short answer"


# --- structured review criteria --------------------------------------------


def test_weighted_approval_uses_scores_over_boolean() -> None:
    from app.agents.domains.base import ReviewCriterion
    from app.agents.reviewer import _weighted_approved

    criteria = (
        ReviewCriterion(id="a", description="", weight=1),
        ReviewCriterion(id="b", description="", weight=1),
    )
    # Model said "not approved" but every criterion scored full marks.
    assert _weighted_approved(False, {"a": 2, "b": 2}, criteria) is True


def test_hard_fail_criterion_zero_rejects() -> None:
    from app.agents.domains.base import ReviewCriterion
    from app.agents.reviewer import _weighted_approved

    criteria = (
        ReviewCriterion(id="secure", description="", weight=2, hard_fail=True),
        ReviewCriterion(id="typed", description="", weight=1),
    )
    assert _weighted_approved(True, {"secure": 0, "typed": 2}, criteria) is False


def test_no_scores_falls_back_to_boolean() -> None:
    from app.agents.domains.base import ReviewCriterion
    from app.agents.reviewer import _weighted_approved

    criteria = (ReviewCriterion(id="a", description="", weight=1),)
    assert _weighted_approved(True, {}, criteria) is True
    assert _weighted_approved(False, {}, criteria) is False


def test_software_domain_declares_structured_criteria() -> None:
    assert get_domain_info("software").review_criteria, (
        "software should carry structured review criteria"
    )


# --- context compaction ----------------------------------------------------


def test_compact_transcript_collapses_long_middle() -> None:
    from app.agents.subagent import _compact_transcript

    big = "y" * 30_000
    messages = [
        ChatMessage("system", "sys"),
        ChatMessage("user", "brief"),
        ChatMessage("assistant", big),
        ChatMessage("user", big),
        ChatMessage("assistant", "recent tool call"),
        ChatMessage("user", "recent feedback"),
    ]
    out = _compact_transcript(messages)
    assert len(out) < len(messages), "the middle exchanges must be collapsed"
    assert out[0].content == "sys" and out[1].content == "brief", "head preserved"
    assert out[-1].content == "recent feedback", "the latest turn is kept"
    assert "summarized" in out[2].content


def test_compact_transcript_noop_below_threshold() -> None:
    from app.agents.subagent import _compact_transcript

    messages = [ChatMessage("system", "s"), ChatMessage("user", "u")]
    assert _compact_transcript(messages) is messages


# --- step-boundary quota ---------------------------------------------------


async def _make_user(db_session, *, used: int = 0) -> User:  # noqa: ANN001
    now = datetime.now(UTC)
    user = User(email=f"quota-{now.timestamp()}@test.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        Subscription(
            user_id=user.id,
            plan=SubscriptionPlan.STARTER.value,
            status=SubscriptionStatus.ACTIVE.value,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
    )
    await db_session.commit()
    if used:
        await usage_service.record_task_usage(
            user_id=user.id,
            task_id=f"seed-{now.timestamp()}",
            tokens=used,
            provider=LLMProvider.OPENAI.value,
            status="completed",
            billable=True,
        )
    return user


async def test_resolve_budget_caps_at_default_when_quota_is_large(db_session) -> None:
    user = await _make_user(db_session)
    budget = await quota_service.resolve_task_token_budget(user.id)
    assert budget == TASK_TOKEN_BUDGET_DEFAULT, budget


async def test_resolve_budget_is_zero_when_quota_exhausted(db_session) -> None:
    plan_quota = 500_000  # STARTER
    user = await _make_user(db_session, used=plan_quota + 1)
    budget = await quota_service.resolve_task_token_budget(user.id)
    assert budget == 0, "an over-quota user gets a zero budget (subagents skipped)"


def test_tools_rule_requires_retrieval_before_asserting_a_current_fact():
    """Availability is not enough; the model has to be told to reach for a tool.

    The rule used to say only "You can use tools." Across four end-to-end runs
    after the Ollama endpoint switch, subagents issued zero tool calls — the
    finance squad included, in a domain declaring web_search and data_fetch, on a
    prompt that asked for real data. The answer invented Bitcoin prices and then
    attributed them to an API it never called. Adding the obligation below took
    tool use from 0/4 runs to 3/3 with no other change.
    """
    rule = SUBAGENT_TOOLS_RULE.format(tool_lines="- x", max_tool_calls=6)

    assert "Use them before you answer" in rule, rule
    # The specific trigger matters more than the general exhortation: these are
    # the answer elements a local model will otherwise supply from memory.
    for trigger in ("price", "count", "date", "version"):
        assert trigger in rule, f"{trigger} missing from the retrieval rule: {rule}"


def test_grounding_policy_forbids_inventing_a_source_trail():
    """An invented provenance is worse than an openly unsourced answer.

    Observed: a run with no tool calls wrote "retrieved from the CoinGecko API"
    and noted the API had been rate-limited. Both were fiction, and both made the
    figures look checked.
    """
    assert "Never describe work you did not do" in GROUNDING_POLICY
    assert "invents an audit trail" in GROUNDING_POLICY


def test_finance_hard_fails_on_invented_figures_and_sources():
    """Finance is where an invented number costs the most.

    The string rubric already asked for sourcing and did not stop it, because
    without structured criteria the verdict is one boolean a fluent answer earns
    easily.
    """
    criteria = {c.id: c for c in get_domain_info("finance").review_criteria}

    assert "no_invented_provenance" in criteria, criteria
    assert "figures_sourced_or_withheld" in criteria, criteria
    for criterion_id in ("no_invented_provenance", "figures_sourced_or_withheld"):
        assert criteria[criterion_id].hard_fail, (
            f"{criterion_id} must reject on its own, not be outvoted by weight"
        )


def test_subagent_prompt_forbids_deliberating_in_the_answer():
    """With thinking off, a reasoning model deliberates in the deliverable.

    Observed on a live lookup: the answer argued with itself line by line
    ("No, that is incorrect", "Wait, let's re-verify via search results"), and
    closed by announcing a search it never performed. The conclusion may have
    been reachable, but the text was unusable — and a sentence saying it will
    check something is strictly worse than the tool call it replaces.
    """
    system = SUBAGENT_SYSTEM.format(
        name="X",
        domain="general",
        role="r",
        instructions="",
        output_format="",
        objective="",
        upstream="",
        review_hints="",
        memory_context="",
    )
    assert "Your reply is the deliverable, not a workspace" in system, system
    assert "no thinking aloud" in system, system

    rule = SUBAGENT_TOOLS_RULE.format(tool_lines="- x", max_tool_calls=6)
    assert "a sentence announcing a" in rule and "search" in rule, rule
