"""Wave-based parallel execution of independent subagents (no I/O)."""

from __future__ import annotations

import asyncio
import json

from app.agents import main_agent
from app.agents.base import AgentContext
from app.core.constants import LLMProvider, SubagentStatus
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse


class ConcurrencyTrackingAdapter(LLMAdapter):
    """Plans caller-provided assignments; subagent calls track concurrency.

    Every subagent call waits until either a sibling arrives (overlap proof)
    or a short timeout passes, and records the member order and the peak
    number of in-flight subagent calls.
    """

    provider = LLMProvider.OLLAMA

    def __init__(self, assignments: list[dict]) -> None:
        super().__init__()
        self._assignments = assignments
        self.started: list[str] = []
        self.finished: list[str] = []
        self.in_flight = 0
        self.peak_in_flight = 0
        self._sibling = asyncio.Event()

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system = messages[0].content
        if "Main Agent, the manager" in system:
            return LLMResponse(
                content=json.dumps({"assignments": self._assignments}),
                model="fake",
                tokens_used=1,
            )
        if "specialist subagent" in system:
            member = system.split('"')[1]  # You are "<name>", ...
            self.started.append(member)
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
            if self.in_flight > 1:
                self._sibling.set()
            try:
                await asyncio.wait_for(self._sibling.wait(), timeout=0.2)
            except TimeoutError:
                pass
            self.in_flight -= 1
            self.finished.append(member)
            return LLMResponse(content=f"{member} done", model="fake", tokens_used=1)
        return LLMResponse(content="final", model="fake", tokens_used=1)


async def test_independent_members_run_concurrently():
    adapter = ConcurrencyTrackingAdapter(
        [
            {"member": "market_data", "brief": "b1", "depends_on": []},
            {"member": "news", "brief": "b2", "depends_on": []},
        ]
    )
    ctx = AgentContext(adapter=adapter)
    await main_agent.run(ctx, domain="finance", prompt="task", reviewer_enabled=False)
    assert adapter.peak_in_flight == 2, (
        f"Independent members must overlap, peak={adapter.peak_in_flight}"
    )


async def test_dependent_member_starts_after_dependency_finishes():
    adapter = ConcurrencyTrackingAdapter(
        [
            {"member": "market_data", "brief": "b1", "depends_on": []},
            {"member": "analyst", "brief": "b2", "depends_on": ["market_data"]},
        ]
    )
    ctx = AgentContext(adapter=adapter)
    await main_agent.run(ctx, domain="finance", prompt="task", reviewer_enabled=False)
    assert adapter.finished.index("Market Data Analyst") < adapter.started.index(
        "Financial Analyst & Reporter"
    ), f"Dependent started early: started={adapter.started}"


async def test_parallelism_respects_semaphore_limit():
    adapter = ConcurrencyTrackingAdapter(
        [
            {"member": "market_data", "brief": "b1", "depends_on": []},
            {"member": "news", "brief": "b2", "depends_on": []},
            {"member": "sentiment", "brief": "b3", "depends_on": []},
        ]
    )
    ctx = AgentContext(adapter=adapter, max_parallel_subagents=1)
    await main_agent.run(ctx, domain="finance", prompt="task", reviewer_enabled=False)
    assert adapter.peak_in_flight == 1, (
        f"Semaphore=1 must serialize, peak={adapter.peak_in_flight}"
    )


class OneMemberCrashesAdapter(ConcurrencyTrackingAdapter):
    """First subagent call raises an unexpected (non-LLMError) exception."""

    def __init__(self, assignments: list[dict]) -> None:
        super().__init__(assignments)
        self._crashed = False

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
        if is_subagent and not self._crashed:
            self._crashed = True
            raise RuntimeError("unexpected crash")
        return await super().chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )


async def test_sibling_crash_becomes_error_result_not_task_failure():
    adapter = OneMemberCrashesAdapter(
        [
            {"member": "market_data", "brief": "b1", "depends_on": []},
            {"member": "news", "brief": "b2", "depends_on": []},
        ]
    )
    ctx = AgentContext(adapter=adapter)
    result = await main_agent.run(
        ctx, domain="finance", prompt="task", reviewer_enabled=False
    )
    statuses = sorted(s["status"] for s in result["subtasks"])
    assert statuses == [
        SubagentStatus.ERROR.value,
        SubagentStatus.SUCCESS.value,
    ], f"Expected one error + one success, got {statuses}"


async def test_results_keep_assignment_order_despite_parallelism():
    adapter = ConcurrencyTrackingAdapter(
        [
            {"member": "market_data", "brief": "b1", "depends_on": []},
            {"member": "news", "brief": "b2", "depends_on": []},
        ]
    )
    ctx = AgentContext(adapter=adapter)
    result = await main_agent.run(
        ctx, domain="finance", prompt="task", reviewer_enabled=False
    )
    members = [s["data"]["member"] for s in result["subtasks"]]
    assert members == ["market_data", "news"], f"Order must be deterministic: {members}"
