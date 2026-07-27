"""Phase D: RAG tools (document_search, memory_recall) over the user's own data.

Keyless and per-user scoped. The load-bearing property is isolation: the
executor must pass the run's ``user_id`` to ``memory_service`` and never a
global default (CLAUDE.md §6). Results are wrapped as untrusted content; a cold
Qdrant degrades to a plain note, never an error.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.agents import subagent
from app.agents import tools as tool_directives
from app.agents.base import AgentContext
from app.agents.registry import get_domain_info
from app.core.constants import (
    DOCUMENT_SEARCH_ACTION,
    MEMORY_RECALL_ACTION,
    QDRANT_CONVERSATION_MEMORIES,
    QDRANT_DOCUMENT_CHUNKS,
    RAG_NO_RESULTS_NOTICE,
    UNTRUSTED_CONTENT_NOTICE,
    LLMProvider,
)
from app.services import memory_service
from app.services.llm_service import ChatMessage, LLMAdapter, LLMResponse

DOMAIN = "general"  # declares document_search + memory_recall
USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

DOC_DIRECTIVE = json.dumps({"action": "document_search", "query": "vacation policy"})
RECALL_DIRECTIVE = json.dumps({"action": "memory_recall", "query": "my timezone"})
FINAL = "Final answer."


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
def retrieve_calls(monkeypatch) -> list[tuple[uuid.UUID, str, str]]:
    """Records (user_id, query, collection) per retrieval; returns one hit."""
    calls: list[tuple[uuid.UUID, str, str]] = []

    async def fake_retrieve(
        user_id, query, *, limit=5, collection=QDRANT_CONVERSATION_MEMORIES, **_
    ):
        calls.append((user_id, query, collection))
        return ["A relevant snippet from the user's own data."]

    monkeypatch.setattr(memory_service, "retrieve_memories", fake_retrieve)
    return calls


async def _run(adapter: LLMAdapter, *, user_id=USER_ID, **ctx_kwargs):
    ctx = AgentContext(adapter=adapter, user_id=user_id, **ctx_kwargs)
    member = get_domain_info(DOMAIN).team[0]
    return await subagent.run_subtask(
        ctx, domain=DOMAIN, member=member, brief="Do the thing", index=0
    )


async def test_document_search_passes_run_user_id(retrieve_calls):
    adapter = ScriptedAdapter([DOC_DIRECTIVE, FINAL])
    result = await _run(adapter)

    assert len(retrieve_calls) == 1, retrieve_calls
    user_id, query, collection = retrieve_calls[0]
    assert user_id == USER_ID, f"executor must scope to the run's user, got {user_id}"
    assert collection == QDRANT_DOCUMENT_CHUNKS, collection
    assert query == "vacation policy", query
    assert result.metadata["document_searches_used"] == 1, result.metadata


async def test_memory_recall_reads_conversation_collection(retrieve_calls):
    adapter = ScriptedAdapter([RECALL_DIRECTIVE, FINAL])
    result = await _run(adapter)

    _, _, collection = retrieve_calls[0]
    assert collection == QDRANT_CONVERSATION_MEMORIES, collection
    assert result.metadata["memory_recalls_used"] == 1, result.metadata


async def test_rag_result_is_wrapped_as_untrusted(retrieve_calls):
    adapter = ScriptedAdapter([DOC_DIRECTIVE, FINAL])
    await _run(adapter)

    # The second LLM call carries the retrieval feedback with the untrusted notice.
    fed_back = "\n".join(m.content for m in adapter.calls[1])
    assert UNTRUSTED_CONTENT_NOTICE in fed_back, fed_back
    assert "A relevant snippet" in fed_back, fed_back


async def test_cold_backend_degrades_to_note(monkeypatch):
    async def empty_retrieve(user_id, query, *, limit=5, collection=None, **_):
        return []  # cold Qdrant / no match

    monkeypatch.setattr(memory_service, "retrieve_memories", empty_retrieve)
    adapter = ScriptedAdapter([DOC_DIRECTIVE, FINAL])
    result = await _run(adapter)

    fed_back = "\n".join(m.content for m in adapter.calls[1])
    assert RAG_NO_RESULTS_NOTICE in fed_back, fed_back
    assert result.data["output"] == FINAL, result.data


def test_specs_for_omits_rag_without_user_id() -> None:
    """No user id → no RAG specs, so those actions silently drop."""
    from app.services.service_key_service import ServiceCredentials

    enabled = frozenset({DOCUMENT_SEARCH_ACTION, MEMORY_RECALL_ACTION})
    specs = tool_directives.specs_for(enabled, ServiceCredentials(), user_id=None)
    assert specs == {}, "RAG specs must not be built without a user id"


def test_specs_for_builds_rag_with_user_id() -> None:
    from app.services.service_key_service import ServiceCredentials

    enabled = frozenset({DOCUMENT_SEARCH_ACTION, MEMORY_RECALL_ACTION})
    specs = tool_directives.specs_for(enabled, ServiceCredentials(), user_id=USER_ID)
    assert set(specs) == {DOCUMENT_SEARCH_ACTION, MEMORY_RECALL_ACTION}, specs
    assert specs[DOCUMENT_SEARCH_ACTION].metadata_key == "document_searches_used"
