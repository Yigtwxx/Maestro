"""Tur 10 remainder: ToolProvider seam, native tool loop, AGENT_DELTA
streaming, and the per-role AdapterPool.

All exercised with fakes — no network I/O.
"""

from __future__ import annotations

from app.agents import main_agent, subagent
from app.agents.base import AgentContext
from app.agents.registry import get_domain_info
from app.agents.tools import (
    TOOL_SPECS,
    ToolDirective,
    ToolSpec,
    builtin_tool_provider,
    tool_defs_for,
)
from app.core.constants import PROVIDER_TIER_MODELS, EventType, LLMProvider
from app.services.llm_service import (
    AdapterCapabilities,
    AdapterPool,
    ChatMessage,
    LLMAdapter,
    LLMResponse,
    ToolCall,
    _parse_openai_tool_calls,
)

SOFTWARE = get_domain_info("software")


# --- ToolProvider seam -----------------------------------------------------


def test_builtin_tool_provider_exposes_the_registry() -> None:
    assert builtin_tool_provider.specs() is TOOL_SPECS


def test_tool_defs_for_builds_native_schemas() -> None:
    defs = tool_defs_for({"web_search": TOOL_SPECS["web_search"]})
    assert len(defs) == 1
    assert defs[0].name == "web_search"
    assert "query" in defs[0].parameters["properties"]


# --- native tool-call parsing ----------------------------------------------


def test_parse_openai_tool_calls_reads_arguments() -> None:
    calls = _parse_openai_tool_calls(
        [{"id": "1", "function": {"name": "web_search", "arguments": '{"query": "x"}'}}]
    )
    assert calls[0].name == "web_search"
    assert calls[0].arguments == {"query": "x"}


def test_parse_openai_tool_calls_tolerates_bad_json() -> None:
    calls = _parse_openai_tool_calls(
        [{"id": "2", "function": {"name": "f", "arguments": "not json"}}]
    )
    assert calls[0].arguments == {}


# --- native tool loop ------------------------------------------------------


class _NativeAdapter(LLMAdapter):
    """Requests one tool call, then answers. Advertises native tools."""

    provider = LLMProvider.OPENAI
    capabilities = AdapterCapabilities(native_tools=True)

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def chat(
        self, messages, *, temperature=0.2, max_tokens=None, tools=None, **_
    ):  # noqa: ANN001
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                model="m",
                tokens_used=1,
                tool_calls=[
                    ToolCall(id="1", name="web_search", arguments={"query": "x"})
                ],
            )
        return LLMResponse(content="final answer", model="m", tokens_used=1)


async def test_native_tool_loop_executes_then_answers() -> None:
    executed: list[ToolDirective] = []

    async def _run(directive: ToolDirective) -> str:
        executed.append(directive)
        return "tool result"

    spec = ToolSpec(
        action="web_search",
        budget_attr="max_web_searches",
        metadata_key="searches_used",
        event_arg="query",
        executor=_run,
        describe=lambda d, done: "web search",
    )
    ctx = AgentContext(adapter=_NativeAdapter())
    response, tokens, usage = await subagent._native_tool_loop(
        ctx,
        [ChatMessage("system", "s"), ChatMessage("user", "b")],
        member=SOFTWARE.team[0],
        index=0,
        specs={"web_search": spec},
    )
    assert response.content == "final answer"
    assert len(executed) == 1, "the requested tool must run exactly once"
    assert usage["web_search"] == 1


# --- AGENT_DELTA streaming -------------------------------------------------


class _SynthAdapter(LLMAdapter):
    provider = LLMProvider.OLLAMA

    async def chat(self, messages, *, temperature=0.2, max_tokens=None, **_):  # noqa: ANN001
        return LLMResponse(content="Final combined answer.", model="m", tokens_used=1)


async def test_synthesis_streams_agent_delta_events() -> None:
    events: list[tuple[EventType, dict]] = []

    async def emit(event_type, payload):  # noqa: ANN001
        events.append((event_type, payload))

    ctx = AgentContext(adapter=_SynthAdapter(), emit=emit)
    answer = await main_agent._synthesize(
        ctx, "software", "task", [("A", "one"), ("B", "two")]
    )
    assert answer == "Final combined answer."
    deltas = [p for t, p in events if t is EventType.AGENT_DELTA]
    assert deltas, "synthesis must stream at least one AGENT_DELTA"
    assert "".join(p["text"] for p in deltas) == "Final combined answer."


# --- AdapterPool -----------------------------------------------------------


def test_pool_resolves_a_model_per_role() -> None:
    pool = AdapterPool(provider=LLMProvider.ANTHROPIC)
    assert pool.for_role("main").model == PROVIDER_TIER_MODELS["anthropic"]["strong"]
    assert pool.for_role("subagent").model == PROVIDER_TIER_MODELS["anthropic"]["cheap"]


def test_pool_roles_share_one_token_counter() -> None:
    pool = AdapterPool(provider=LLMProvider.ANTHROPIC)
    main = pool.for_role("main")
    sub = pool.for_role("subagent")
    pool.total_tokens = 42
    assert main.total_tokens == 42 and sub.total_tokens == 42, "one shared counter"


def test_pool_model_override_wins_for_every_role() -> None:
    pool = AdapterPool(provider=LLMProvider.CUSTOM, model="fixed-model")
    assert pool.for_role("subagent").model == "fixed-model"
    assert pool.for_role("synthesis").model == "fixed-model"
