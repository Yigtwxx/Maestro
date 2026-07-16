"""End-to-end agent orchestration test with a fake LLM adapter (no I/O)."""

from __future__ import annotations

import json

import pytest

from app.agents import main_agent, orchestrator
from app.agents.base import AgentContext
from app.agents.registry import (
    DOMAIN_CATALOG,
    DOMAINS,
    get_domain_info,
    normalize_domain,
)
from app.core.constants import MAX_SUBTASKS, TOOL_IDS, LLMProvider, SubagentStatus
from app.services.llm_service import (
    ChatMessage,
    LLMAdapter,
    LLMError,
    LLMResponse,
    TokenMeter,
)

SOFTWARE_TEAM_IDS = [member.id for member in get_domain_info("software").team]


class FakeAdapter(LLMAdapter):
    """Deterministic adapter that answers based on the system prompt."""

    provider = LLMProvider.OLLAMA

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system = messages[0].content
        if "Orchestrator" in system:
            content = '{"domain": "software", "reason": "coding task"}'
        elif "Main Agent, the manager" in system:
            content = json.dumps(
                {
                    "assignments": [
                        {"member": "coder", "brief": "Write function"},
                        {"member": "tester", "brief": "Add tests"},
                    ]
                }
            )
        elif "specialist subagent" in system:
            # A realistic deliverable: long enough and with a fenced code block,
            # so the software domain's deterministic pre-review validators pass.
            content = "Here is the requested output:\n```python\nx = 1\n```"
        elif "You are the Reviewer" in system:
            content = '{"approved": true, "issues": [], "retry_hints": []}'
        else:  # synthesis
            content = "Final combined answer."
        return LLMResponse(content=content, model="fake", tokens_used=7)


class AssignmentAdapter(FakeAdapter):
    """Planner that returns a caller-provided assignments payload."""

    def __init__(self, assignments: list[dict[str, str]]) -> None:
        super().__init__()
        self._assignments = assignments

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if "Main Agent, the manager" in messages[0].content:
            return LLMResponse(
                content=json.dumps({"assignments": self._assignments}),
                model="fake",
                tokens_used=7,
            )
        return await super().chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )


class FailingPlanAdapter(FakeAdapter):
    """Every planner call fails; everything else behaves normally."""

    def __init__(self) -> None:
        super().__init__()
        self.plan_calls = 0

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if "Main Agent, the manager" in messages[0].content:
            self.plan_calls += 1
            raise LLMError("planner down")
        return await super().chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )


class FlakyPlanAdapter(FakeAdapter):
    """First planner call fails; the retry returns a valid plan."""

    def __init__(self) -> None:
        super().__init__()
        self.plan_calls = 0

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if "Main Agent, the manager" in messages[0].content:
            self.plan_calls += 1
            if self.plan_calls == 1:
                raise LLMError("planner hiccup")
            return LLMResponse(
                content=json.dumps(
                    {"assignments": [{"member": "coder", "brief": "Write function"}]}
                ),
                model="fake",
                tokens_used=7,
            )
        return await super().chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )


class FailingSubagentAdapter(FakeAdapter):
    """Every subagent call fails; planner/orchestrator/synthesis are normal.

    Mirrors the hosted failure mode: an Ollama with no chat model pulled makes
    each subtask raise ``ollama chat failed``.
    """

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system = messages[0].content
        # Plan prompts mention "specialist subagents" too — check them first.
        is_subagent = (
            "Main Agent, the manager" not in system and "specialist subagent" in system
        )
        if is_subagent:
            raise LLMError("ollama chat failed")
        return await super().chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )


class OneSubagentFailsAdapter(FakeAdapter):
    """Only the first subagent call fails; the rest succeed (partial failure)."""

    def __init__(self) -> None:
        super().__init__()
        self._failed = False

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system = messages[0].content
        is_subagent = (
            "Main Agent, the manager" not in system and "specialist subagent" in system
        )
        if is_subagent and not self._failed:
            self._failed = True
            raise LLMError("ollama chat failed")
        return await super().chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )


def _members(result: dict) -> list[str]:
    return [subtask["data"]["member"] for subtask in result["subtasks"]]


async def test_all_subtasks_failing_flags_result_and_skips_synthesis():
    ctx = AgentContext(adapter=FailingSubagentAdapter())
    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )
    statuses = {subtask["status"] for subtask in result["subtasks"]}
    assert statuses == {SubagentStatus.ERROR.value}, f"Expected all error: {statuses}"
    assert result["all_subtasks_failed"] is True, "All-error task must be flagged"
    assert result["answer"] == "No successful subtask output.", (
        f"Expected sentinel answer, got {result['answer']!r}"
    )


async def test_partial_subtask_failure_is_not_flagged_all_failed():
    ctx = AgentContext(adapter=OneSubagentFailsAdapter())
    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )
    statuses = sorted(subtask["status"] for subtask in result["subtasks"])
    assert statuses == [
        SubagentStatus.ERROR.value,
        SubagentStatus.SUCCESS.value,
    ], f"Expected one error + one success, got {statuses}"
    assert result["all_subtasks_failed"] is False, (
        "A task with at least one successful subtask must not be flagged failed"
    )


async def test_full_pipeline_without_reviewer():
    meter = TokenMeter(FakeAdapter())
    ctx = AgentContext(adapter=meter)
    domain = await orchestrator.route(ctx, "Build me a Python function")
    assert domain == "software"

    result = await main_agent.run(
        ctx,
        domain=domain,
        prompt="Build me a Python function",
        reviewer_enabled=False,
    )
    assert result["domain"] == "software"
    assert result["answer"] == "Final combined answer."
    assert result["metadata"]["subtask_count"] == 2
    assert _members(result) == ["coder", "tester"]

    # Billing counts every call -- route, plan, both subagents, synthesis --
    # at 7 tokens each. Summing only the subagents would report 14 and let the
    # other three calls run free.
    assert meter.total_tokens == 35, f"Expected 35 tokens, got {meter.total_tokens}"


async def test_pipeline_with_reviewer_approves():
    ctx = AgentContext(adapter=FakeAdapter(), max_review_iterations=3)
    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=True
    )
    for subtask in result["subtasks"]:
        assert subtask["metadata"].get("review_iterations") == 0


async def test_max_iterations_caps_assignments():
    ctx = AgentContext(adapter=FakeAdapter(), max_iterations=1)
    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )
    assert result["metadata"]["subtask_count"] == 1


async def test_assign_unknown_member_ids_are_dropped():
    adapter = AssignmentAdapter(
        [
            {"member": "coder", "brief": "Write function"},
            {"member": "bogus_member", "brief": "Do something"},
            {"member": "tester", "brief": "Add tests"},
        ]
    )
    ctx = AgentContext(adapter=adapter)
    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )
    members = _members(result)
    assert members == ["coder", "tester"], f"Expected only team members: {members}"


async def test_assign_duplicate_member_keeps_first_brief():
    adapter = AssignmentAdapter(
        [
            {"member": "coder", "brief": "First brief"},
            {"member": "coder", "brief": "Second brief"},
        ]
    )
    ctx = AgentContext(adapter=adapter)
    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )
    assert _members(result) == ["coder"], f"Expected dedupe: {_members(result)}"
    brief = result["subtasks"][0]["data"]["subtask"]
    assert brief == "First brief", f"Expected first brief kept, got {brief}"


async def test_assign_results_follow_team_order():
    # LLM answers out of order; execution must follow the fixed team order.
    adapter = AssignmentAdapter(
        [
            {"member": "tester", "brief": "Add tests"},
            {"member": "coder", "brief": "Write function"},
        ]
    )
    ctx = AgentContext(adapter=adapter)
    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )
    members = _members(result)
    assert members == ["coder", "tester"], f"Expected team order, got {members}"


async def test_assign_empty_assignments_falls_back_to_full_team():
    ctx = AgentContext(adapter=AssignmentAdapter([]))
    result = await main_agent.run(
        ctx, domain="software", prompt="task", reviewer_enabled=False
    )
    assert _members(result) == SOFTWARE_TEAM_IDS, f"Got {_members(result)}"


async def test_assign_plan_llm_error_retries_once_then_uses_role_briefs():
    adapter = FailingPlanAdapter()
    ctx = AgentContext(adapter=adapter)
    result = await main_agent.run(
        ctx, domain="software", prompt="raw task", reviewer_enabled=False
    )
    assert adapter.plan_calls == 2, f"Expected one retry, got {adapter.plan_calls}"
    assert _members(result) == SOFTWARE_TEAM_IDS, f"Got {_members(result)}"
    briefs = [subtask["data"]["subtask"] for subtask in result["subtasks"]]
    for member, brief in zip(get_domain_info("software").team, briefs, strict=True):
        assert "raw task" not in brief, f"Raw prompt leaked into brief: {brief}"
        assert "view_original_request" in brief, f"No tool pointer in brief: {brief}"
        assert member.role in brief, f"Role missing from brief: {brief}"


async def test_assign_plan_retry_succeeds_on_second_attempt():
    adapter = FlakyPlanAdapter()
    ctx = AgentContext(adapter=adapter)
    result = await main_agent.run(
        ctx, domain="software", prompt="raw task", reviewer_enabled=False
    )
    assert adapter.plan_calls == 2, f"Expected a retry, got {adapter.plan_calls}"
    assert _members(result) == ["coder"], f"Got {_members(result)}"
    brief = result["subtasks"][0]["data"]["subtask"]
    assert brief == "Write function", f"Expected planned brief, got {brief}"


def test_fallback_assignments_use_role_template_and_chained_deps():
    team = get_domain_info("software").team
    assignments = main_agent._fallback_assignments(team)
    for index, (member, assignment) in enumerate(zip(team, assignments, strict=True)):
        assert member.role in assignment.brief, assignment.brief
        assert "view_original_request" in assignment.brief, assignment.brief
        expected_deps = tuple(m.id for m in team[:index])
        assert assignment.depends_on == expected_deps, (
            f"Expected {expected_deps}, got {assignment.depends_on}"
        )


async def test_assign_depends_on_unknown_self_and_forward_refs_dropped():
    adapter = AssignmentAdapter(
        [
            # coder depends on itself, an unknown id, and tester (forward ref
            # in final team order) — all must be dropped.
            {
                "member": "coder",
                "brief": "Write function",
                "depends_on": ["coder", "bogus", "tester"],
            },
            {"member": "tester", "brief": "Add tests", "depends_on": ["coder"]},
        ]
    )
    ctx = AgentContext(adapter=adapter)
    events: list[dict] = []

    async def emit(event_type, payload):  # noqa: ANN001 - EmitFn shape
        events.append(payload)

    ctx.emit = emit
    await main_agent.run(ctx, domain="software", prompt="task", reviewer_enabled=False)
    briefs = next(p["assignments"] for p in events if "assignments" in p)
    by_member = {b["member_id"]: b["depends_on"] for b in briefs}
    assert by_member["coder"] == [], f"Expected empty deps, got {by_member['coder']}"
    assert by_member["tester"] == ["coder"], f"Got {by_member['tester']}"


async def test_assign_fallback_chains_team_in_order():
    ctx = AgentContext(adapter=FailingPlanAdapter())
    events: list[dict] = []

    async def emit(event_type, payload):  # noqa: ANN001 - EmitFn shape
        events.append(payload)

    ctx.emit = emit
    await main_agent.run(ctx, domain="software", prompt="task", reviewer_enabled=False)
    briefs = next(p["assignments"] for p in events if "assignments" in p)
    deps = [b["depends_on"] for b in briefs]
    expected = [SOFTWARE_TEAM_IDS[:i] for i in range(len(SOFTWARE_TEAM_IDS))]
    assert deps == expected, f"Expected chained deps {expected}, got {deps}"


class UpstreamCaptureAdapter(AssignmentAdapter):
    """Records subagent system prompts and gives each member a unique output."""

    def __init__(self, assignments: list[dict]) -> None:
        super().__init__(assignments)
        self.subagent_systems: list[str] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system = messages[0].content
        # Plan prompts mention "specialist subagents" too — check them first.
        is_subagent = (
            "Main Agent, the manager" not in system and "specialist subagent" in system
        )
        if is_subagent:
            self.subagent_systems.append(system)
            return LLMResponse(
                content=f"output #{len(self.subagent_systems)}",
                model="fake",
                tokens_used=7,
            )
        return await super().chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )


async def test_run_dependent_member_sees_upstream_output():
    adapter = UpstreamCaptureAdapter(
        [
            {"member": "architect", "brief": "Design it", "depends_on": []},
            {"member": "coder", "brief": "Build it", "depends_on": ["architect"]},
        ]
    )
    ctx = AgentContext(adapter=adapter)
    await main_agent.run(ctx, domain="software", prompt="task", reviewer_enabled=False)

    architect_prompt, coder_prompt = adapter.subagent_systems
    assert "Work from your teammates" not in architect_prompt, (
        "Independent member must not get an upstream block"
    )
    assert "--- Architect ---" in coder_prompt, coder_prompt
    assert "output #1" in coder_prompt, "Architect's output missing from coder prompt"


async def test_run_subagent_prompt_omits_raw_user_request():
    adapter = UpstreamCaptureAdapter(
        [{"member": "coder", "brief": "Build it", "depends_on": []}]
    )
    ctx = AgentContext(adapter=adapter)
    await main_agent.run(
        ctx, domain="software", prompt="the big goal", reviewer_enabled=False
    )
    assert "the big goal" not in adapter.subagent_systems[0], (
        "Raw user request must not be injected into the subagent prompt"
    )


async def test_run_subagent_prompt_offers_view_original_request_rule():
    adapter = UpstreamCaptureAdapter(
        [{"member": "coder", "brief": "Build it", "depends_on": []}]
    )
    ctx = AgentContext(adapter=adapter)
    await main_agent.run(
        ctx, domain="software", prompt="the big goal", reviewer_enabled=False
    )
    assert '"action": "view_original_request"' in adapter.subagent_systems[0], (
        "Subagent must be offered the view_original_request directive"
    )


def test_domain_catalog_contains_all_expected_domains():
    expected = {
        "software",
        "finance",
        "marketing",
        "seo",
        "searching",
        "research",
        "data",
        "content",
        "legal",
        "education",
        "general",
    }
    assert set(DOMAINS) == expected, f"Catalog domains mismatch: {set(DOMAINS)}"


def test_legal_domain_carries_not_legal_advice_disclaimer():
    info = get_domain_info("legal")
    assert "not legal advice" in info.output_format, (
        "legal output_format must carry the not-legal-advice disclaimer"
    )
    assert "disclaimer" in info.review_rubric.lower(), (
        "legal review_rubric must enforce the disclaimer"
    )


def test_domain_catalog_entries_are_complete():
    for entry in DOMAIN_CATALOG:
        assert entry.name, f"{entry.id}: empty name"
        assert entry.description, f"{entry.id}: empty description"
        assert entry.expertise, f"{entry.id}: empty expertise"
        assert entry.routing_hint, f"{entry.id}: empty routing_hint"
        assert entry.capabilities, f"{entry.id}: no capabilities"
        assert entry.methodology, f"{entry.id}: empty methodology"
        assert entry.output_format, f"{entry.id}: empty output_format"
        assert entry.planning_example, f"{entry.id}: empty planning_example"
        assert entry.review_rubric, f"{entry.id}: empty review_rubric"
        assert '"depends_on"' in entry.planning_example, (
            f"{entry.id}: planning_example does not teach depends_on"
        )
        unknown = set(entry.tools) - TOOL_IDS
        assert not unknown, f"{entry.id}: unknown tools {unknown}"


def test_domain_catalog_teams_are_valid():
    for entry in DOMAIN_CATALOG:
        size = len(entry.team)
        assert 1 <= size <= MAX_SUBTASKS, f"{entry.id}: team size {size}"
        ids = [member.id for member in entry.team]
        assert len(ids) == len(set(ids)), f"{entry.id}: duplicate member ids {ids}"
        for member in entry.team:
            assert member.name, f"{entry.id}/{member.id}: empty name"
            assert member.description, f"{entry.id}/{member.id}: empty description"
            assert member.role, f"{entry.id}/{member.id}: empty role"
            assert member.instructions, f"{entry.id}/{member.id}: empty instructions"
            assert member.output_format, f"{entry.id}/{member.id}: empty output_format"


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("seo", "seo"),
        ("searching", "searching"),
        (" SEO ", "seo"),
        ("bogus", "general"),
        ("", "general"),
    ],
)
def test_normalize_domain_maps_candidates_to_known_domains(candidate, expected):
    result = normalize_domain(candidate)
    assert result == expected, f"Expected {expected}, got {result}"
