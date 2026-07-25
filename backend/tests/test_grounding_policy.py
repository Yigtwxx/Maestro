"""The grounding policy reaches the prompts that write prose — and only those.

A quality review found two recurring failure modes: an identifier reconstructed
by analogy with similar ones, and an unsourced date filled in with a plausible
guess. ``GROUNDING_POLICY`` is the countermeasure, so these tests pin *where* it
is injected. The negative cases matter as much as the positive ones: the
orchestrator and the planner must return strict JSON, and prose rules alongside
a JSON contract cost a small local model its output budget.

No network I/O — a capture adapter stands in for the LLM.
"""

from __future__ import annotations

from app.agents import main_agent, orchestrator, subagent
from app.agents.base import AgentContext
from app.agents.prompts import (
    GROUNDING_POLICY,
    SYNTHESIS_MERGE_RULES,
    SYNTHESIS_SYSTEM,
)
from app.agents.registry import get_domain_info
from app.core.constants import (
    NOT_FOUND_PREFIX,
    UNCERTAINTY_CLOSE,
    UNCERTAINTY_OPEN,
    LLMProvider,
    SubagentStatus,
)
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse

DOMAIN = "searching"
# Long enough to clear nonempty_min_length, so a caller that reviews this output
# reaches the LLM path rather than short-circuiting on a validator.
ANSWER = "A complete and sufficiently long answer to the brief at hand."

# One recognisable phrase from the policy — the clause that names the observed
# failure mode, so it survives rewording of the surrounding block. Matching the
# whole block would make every reflow of the prompt a test failure.
POLICY_MARKER = "by analogy with similar items"


class CaptureAdapter(LLMAdapter):
    """Records the system prompt of every call; always answers ``ANSWER``."""

    provider = LLMProvider.OLLAMA

    def __init__(self) -> None:
        super().__init__()
        self.systems: list[str] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **_: object,
    ) -> LLMResponse:
        self.systems.append(messages[0].content)
        return LLMResponse(content=ANSWER, model="fake", tokens_used=1)


async def test_subagent_system_prompt_carries_the_grounding_policy() -> None:
    adapter = CaptureAdapter()
    ctx = AgentContext(adapter=adapter)
    member = get_domain_info(DOMAIN).team[0]

    result = await subagent.run_subtask(
        ctx, domain=DOMAIN, member=member, brief="Find the release date.", index=0
    )

    assert result.status is SubagentStatus.SUCCESS, result.data
    system = adapter.systems[0]
    assert POLICY_MARKER in system, system
    assert UNCERTAINTY_OPEN in system and UNCERTAINTY_CLOSE in system, system
    assert NOT_FOUND_PREFIX in system, system


async def test_orchestrator_prompt_stays_free_of_the_grounding_policy() -> None:
    adapter = CaptureAdapter()
    ctx = AgentContext(adapter=adapter)

    await orchestrator.route(ctx, "Find the release date of redis-py 5.0.")

    assert adapter.systems, "the orchestrator made no LLM call"
    assert POLICY_MARKER not in adapter.systems[0], adapter.systems[0]


async def test_planner_prompt_stays_free_of_the_grounding_policy() -> None:
    adapter = CaptureAdapter()
    ctx = AgentContext(adapter=adapter)

    # The plan call fails to parse (CaptureAdapter returns prose, not JSON) and
    # main_agent falls back, but the prompt is captured either way — which is all
    # this test inspects.
    await main_agent._plan(ctx, DOMAIN, "Find the release date.", allow_clarify=False)

    assert adapter.systems, "the planner made no LLM call"
    assert POLICY_MARKER not in adapter.systems[0], adapter.systems[0]


def test_synthesis_prompt_carries_the_policy_and_the_merge_rules() -> None:
    system = SYNTHESIS_SYSTEM.format(domain=DOMAIN, output_format="")

    assert GROUNDING_POLICY in system
    assert SYNTHESIS_MERGE_RULES in system
    # The merge is where a marker is most likely to be lost, so the instruction
    # to carry markers through verbatim must survive any reflow of the prompt.
    assert "unchanged" in SYNTHESIS_MERGE_RULES
