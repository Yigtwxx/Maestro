"""Every agent system prompt must carry today's UTC date (grounding)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.agents import main_agent, orchestrator
from app.agents.base import AgentContext
from app.core.constants import LLMProvider
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse


class RecordingAdapter(LLMAdapter):
    """FakeAdapter variant that records every system prompt it receives."""

    provider = LLMProvider.OLLAMA

    def __init__(self) -> None:
        super().__init__()
        self.system_prompts: list[str] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system = messages[0].content
        self.system_prompts.append(system)
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
            content = "Subtask output."
        elif "You are the Reviewer" in system:
            content = '{"approved": true, "issues": [], "retry_hints": []}'
        else:  # synthesis
            content = "Final combined answer."
        return LLMResponse(content=content, model="fake", tokens_used=7)


async def test_all_agent_system_prompts_include_current_date():
    adapter = RecordingAdapter()
    ctx = AgentContext(adapter=adapter)

    domain = await orchestrator.route(ctx, "Build me a Python function")
    await main_agent.run(
        ctx,
        domain=domain,
        prompt="Build me a Python function",
        reviewer_enabled=True,
    )

    today = datetime.now(UTC).date().isoformat()
    # Orchestrator + main plan + 2 subagents + 2 reviews + synthesis = 7 calls.
    assert len(adapter.system_prompts) >= 5, f"Got {len(adapter.system_prompts)}"
    for system in adapter.system_prompts:
        assert f"Current date: {today} (UTC)" in system, (
            f"Missing date line in system prompt: {system[:120]!r}"
        )
