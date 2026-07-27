"""Phase C: the Main Agent's read-only discovery loop before planning.

Strictly whitelisted to the RAG tools and bounded by ``max_discovery_calls``, so
no external or action tool ever runs at the main tier. Its findings are folded
into the shared memory_context so planning is grounded in the user's own data.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.agents import main_agent
from app.agents import tools as tool_directives
from app.agents.base import AgentContext
from app.core.constants import LLMProvider
from app.services import memory_service
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse

DOMAIN = "general"  # declares document_search + memory_recall
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

DOC_DIRECTIVE = json.dumps({"action": "document_search", "query": "policy"})
WEB_DIRECTIVE = json.dumps({"action": "web_search", "query": "not allowed here"})


class ScriptedAdapter(LLMAdapter):
    provider = LLMProvider.OLLAMA

    def __init__(self, replies: list[str]) -> None:
        super().__init__()
        self.replies = replies
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return LLMResponse(content=reply, model="fake", tokens_used=7)


@pytest.fixture
def retrieve_spy(monkeypatch) -> list[str]:
    """Records each RAG query; returns one hit per lookup."""
    queries: list[str] = []

    async def fake_retrieve(user_id, query, *, limit=5, collection=None, **_):
        queries.append(query)
        return [f"note for: {query}"]

    monkeypatch.setattr(memory_service, "retrieve_memories", fake_retrieve)
    return queries


async def test_discovery_runs_whitelisted_rag_then_stops(retrieve_spy):
    adapter = ScriptedAdapter([DOC_DIRECTIVE, "DONE"])
    ctx = AgentContext(adapter=adapter, user_id=USER_ID, max_discovery_calls=3)

    notes = await main_agent._discover(ctx, DOMAIN, "help with the policy")

    assert retrieve_spy == ["policy"], retrieve_spy
    assert any("note for: policy" in n for n in notes), notes


async def test_discovery_ignores_non_rag_directive(retrieve_spy):
    # web_search is not in the RAG whitelist, so it is never even offered; the
    # directive does not parse against the discovery specs and the loop stops.
    adapter = ScriptedAdapter([WEB_DIRECTIVE, "DONE"])
    ctx = AgentContext(adapter=adapter, user_id=USER_ID, max_discovery_calls=3)

    notes = await main_agent._discover(ctx, DOMAIN, "task")

    assert retrieve_spy == [], "no RAG lookup should have run"
    assert notes == [], notes


async def test_discovery_respects_call_bound(retrieve_spy):
    # The model keeps issuing directives; the loop must stop at the bound.
    adapter = ScriptedAdapter([DOC_DIRECTIVE, DOC_DIRECTIVE, DOC_DIRECTIVE])
    ctx = AgentContext(adapter=adapter, user_id=USER_ID, max_discovery_calls=2)

    notes = await main_agent._discover(ctx, DOMAIN, "task")

    assert len(retrieve_spy) == 2, f"bounded to 2 lookups, got {retrieve_spy}"
    assert len(notes) == 2, notes


async def test_discovery_disabled_switch_is_noop(retrieve_spy, monkeypatch):
    monkeypatch.setattr(main_agent.settings, "main_agent_discovery_enabled", False)
    adapter = ScriptedAdapter([DOC_DIRECTIVE, "DONE"])
    ctx = AgentContext(adapter=adapter, user_id=USER_ID, max_discovery_calls=3)

    notes = await main_agent._discover(ctx, DOMAIN, "task")

    assert notes == [], notes
    assert len(adapter.calls) == 0, "no LLM call when discovery is disabled"


async def test_discovery_noop_without_user_id(retrieve_spy):
    adapter = ScriptedAdapter([DOC_DIRECTIVE, "DONE"])
    ctx = AgentContext(adapter=adapter, user_id=None, max_discovery_calls=3)

    notes = await main_agent._discover(ctx, DOMAIN, "task")

    assert notes == [], "no user id → no discovery"
    assert len(adapter.calls) == 0, adapter.calls


async def test_discovery_whitelist_excludes_web_domain(retrieve_spy):
    """A domain with no RAG tool grants no discovery at all."""
    adapter = ScriptedAdapter([DOC_DIRECTIVE, "DONE"])
    ctx = AgentContext(adapter=adapter, user_id=USER_ID, max_discovery_calls=3)

    # software declares code_execution/file_read but no RAG tool.
    resolved = await tool_directives.resolve_enabled_tools(
        "software", assigned=frozenset({"document_search", "memory_recall"})
    )
    assert resolved == frozenset(), resolved

    notes = await main_agent._discover(ctx, "software", "task")
    assert notes == [], notes
    assert len(adapter.calls) == 0, "no RAG tool in domain → no discovery loop"
