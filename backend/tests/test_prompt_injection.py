"""Domain content (instructions, methodology, output formats) reaches prompts."""

from __future__ import annotations

from app.agents import main_agent
from app.agents.base import AgentContext
from app.agents.registry import DOMAIN_CATALOG, get_domain_info
from app.core.constants import LLMProvider
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse

# FakeAdapter dispatch markers used across the test suite; domain content
# must never contain them or prompt-based dispatch would silently break.
_DISPATCH_MARKERS = (
    "Orchestrator",
    "Main Agent, the manager",
    "specialist subagent",
    "You are the Reviewer",
    "You can use tools",
)


class PromptCaptureAdapter(LLMAdapter):
    """Briefs two members and records every system prompt by pipeline stage."""

    provider = LLMProvider.OLLAMA

    def __init__(self) -> None:
        super().__init__()
        self.plan_system = ""
        self.subagent_systems: list[str] = []
        self.synthesis_system = ""

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system = messages[0].content
        if "Main Agent, the manager" in system:
            self.plan_system = system
            content = (
                '{"assignments": [{"member": "coder", "brief": "b1"},'
                ' {"member": "tester", "brief": "b2"}]}'
            )
        elif "specialist subagent" in system:
            self.subagent_systems.append(system)
            content = "ok"
        else:
            self.synthesis_system = system
            content = "final"
        return LLMResponse(content=content, model="fake", tokens_used=1)


async def test_domain_content_is_injected_into_all_prompt_stages() -> None:
    adapter = PromptCaptureAdapter()
    ctx = AgentContext(adapter=adapter)
    await main_agent.run(ctx, domain="software", prompt="p", reviewer_enabled=False)

    info = get_domain_info("software")
    coder = next(member for member in info.team if member.id == "coder")

    assert info.methodology in adapter.plan_system, "methodology missing from plan"
    assert info.planning_example in adapter.plan_system, (
        "planning example missing from plan"
    )
    assert any(coder.instructions in system for system in adapter.subagent_systems), (
        "member instructions missing from subagent prompt"
    )
    assert any(coder.output_format in system for system in adapter.subagent_systems), (
        "member output format missing from subagent prompt"
    )
    # Two outputs trigger real synthesis; it must carry the domain format.
    assert info.output_format in adapter.synthesis_system, (
        "domain output format missing from synthesis prompt"
    )
    assert '"software"' in adapter.synthesis_system, (
        "domain name missing from synthesis prompt"
    )


def test_domain_content_never_contains_dispatch_markers() -> None:
    for entry in DOMAIN_CATALOG:
        texts = [
            entry.description,
            entry.expertise,
            entry.routing_hint,
            entry.methodology,
            entry.output_format,
            entry.planning_example,
            entry.review_rubric,
        ]
        for member in entry.team:
            texts.extend(
                [
                    member.description,
                    member.role,
                    member.instructions,
                    member.output_format,
                ]
            )
        for text in texts:
            for marker in _DISPATCH_MARKERS:
                assert marker not in text, (
                    f"{entry.id}: content contains dispatch marker {marker!r}"
                )
