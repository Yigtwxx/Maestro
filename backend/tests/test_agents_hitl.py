"""Tests for RAG context injection and human-in-the-loop clarification."""

from __future__ import annotations

from app.agents import main_agent
from app.agents.base import AgentContext
from app.agents.registry import get_domain_info
from app.core.constants import LLMProvider
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse


class ClarifyAdapter(LLMAdapter):
    """Main Agent asks a question on its first plan, then briefs one member."""

    provider = LLMProvider.OLLAMA

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
        system = messages[0].content
        if "Main Agent, the manager" in system:
            self.plan_calls += 1
            if self.plan_calls == 1:
                content = '{"question": "Which language?"}'
            else:
                content = '{"assignments": [{"member": "coder", "brief": "do it"}]}'
        elif "specialist subagent" in system:
            content = "done"
        else:
            content = "final"
        return LLMResponse(content=content, model="fake", tokens_used=1)


async def test_hitl_clarification_asks_then_replans():
    asked: list[str] = []

    async def ask(question: str) -> str:
        asked.append(question)
        return "Python"

    ctx = AgentContext(adapter=ClarifyAdapter(), ask_user=ask, allow_questions=True)
    result = await main_agent.run(
        ctx, domain="software", prompt="build", reviewer_enabled=False
    )
    assert asked == ["Which language?"], asked
    assert result["metadata"]["subtask_count"] == 1, result


async def test_questions_disabled_ignores_clarification():
    ctx = AgentContext(adapter=ClarifyAdapter(), allow_questions=False)
    result = await main_agent.run(
        ctx, domain="software", prompt="build", reviewer_enabled=False
    )
    # No clarification path: the question JSON has no assignments, so the
    # whole fixed team runs with the raw prompt.
    team_size = len(get_domain_info("software").team)
    assert result["metadata"]["subtask_count"] == team_size, result


class CaptureAdapter(LLMAdapter):
    """Records the subagent system prompt so we can assert on injected memory."""

    provider = LLMProvider.OLLAMA

    def __init__(self) -> None:
        super().__init__()
        self.subagent_system = ""

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system = messages[0].content
        if "Main Agent, the manager" in system:
            content = '{"assignments": [{"member": "coder", "brief": "s1"}]}'
        elif "specialist subagent" in system:
            self.subagent_system = system
            content = "ok"
        else:
            content = "final"
        return LLMResponse(content=content, model="fake", tokens_used=1)


async def test_memory_context_injected_into_subagent_prompt():
    adapter = CaptureAdapter()
    ctx = AgentContext(adapter=adapter, memory_context=["prior fact X"])
    await main_agent.run(ctx, domain="software", prompt="p", reviewer_enabled=False)
    assert "prior fact X" in adapter.subagent_system, adapter.subagent_system
