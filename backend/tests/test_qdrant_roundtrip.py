"""RAG round-trips against a real Qdrant, not a double.

Every other Qdrant test in this suite patches a hand-written fake, and each fake
defines whatever methods its test needs. That is how ``retrieve_memories`` came
to call a client method that no longer existed: the fakes kept answering, the
``except Exception -> return []`` swallowed the ``AttributeError`` in production,
and RAG returned "no results" for every user while CI stayed green.

These tests use ``AsyncQdrantClient(":memory:")``, which is qdrant-client's own
implementation rather than an imitation of it. Two properties follow, and both
are the point of the file:

* Filters are genuinely evaluated, so per-user isolation (CLAUDE.md rule 4) is
  actually asserted here. Nothing else in the suite inspects ``_user_filter`` --
  a wrong payload key or a missing ``str()`` would leak one user's documents
  into another's context and pass every existing test.
* The API surface is the real one, so a method the client has dropped fails
  loudly instead of degrading to an empty list.

Ranking is deliberately never asserted: the embedder is a stub, so which hit
scores highest is meaningless. Membership is what carries the invariant.
"""

from __future__ import annotations

import uuid

import pytest
from qdrant_client import models

from app.agents.tools import ToolDirective, make_rag_tool_specs
from app.core.constants import (
    DOCUMENT_SEARCH_ACTION,
    MEMORY_RECALL_ACTION,
    QDRANT_CONVERSATION_MEMORIES,
    QDRANT_DOCUMENT_CHUNKS,
    RAG_NO_RESULTS_NOTICE,
)
from app.services import memory_service
from tests.conftest import TEST_EMBEDDING_DIM

ALICE = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOB = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


async def test_retrieve_memories_returns_stored_text(qdrant):
    """The regression guard for client API drift.

    Against a fake this passes no matter what method ``retrieve_memories``
    calls. Against the real client, a removed or renamed method returns [] and
    fails here -- which is exactly what did not happen when ``search`` went away.
    """
    await memory_service.add_memory(ALICE, "the deployment runbook lives in ops/")

    hits = await memory_service.retrieve_memories(ALICE, "runbook")

    assert hits == ["the deployment runbook lives in ops/"], (
        f"Stored text must survive a real round-trip, got {hits}"
    )


async def test_retrieve_memories_other_users_data_is_never_returned(qdrant):
    """Per-user isolation, CLAUDE.md rule 4 -- the load-bearing property.

    Both users store text matching the same query, so only ``_user_filter``
    separates them. Every other test in the suite discards ``query_filter``.
    """
    await memory_service.add_memory(ALICE, "alice quarterly revenue is 12M")
    await memory_service.add_memory(BOB, "bob quarterly revenue is 90M")

    alice_hits = await memory_service.retrieve_memories(ALICE, "quarterly revenue")
    bob_hits = await memory_service.retrieve_memories(BOB, "quarterly revenue")

    assert alice_hits == ["alice quarterly revenue is 12M"], (
        f"Alice must see only her own memory, got {alice_hits}"
    )
    assert bob_hits == ["bob quarterly revenue is 90M"], (
        f"Bob must see only his own memory, got {bob_hits}"
    )


async def test_retrieve_memories_unknown_user_returns_nothing(qdrant):
    """A user with no stored data gets an empty result, not someone else's."""
    await memory_service.add_memory(ALICE, "alice private note")

    hits = await memory_service.retrieve_memories(BOB, "note")

    assert hits == [], f"A user with no data must see nothing, got {hits}"


async def test_ensure_collection_creates_with_configured_dimension(qdrant):
    """The collection is built from ``settings.embedding_dim``, not a constant."""
    await memory_service.ensure_collection(QDRANT_CONVERSATION_MEMORIES)

    info = await qdrant.get_collection(QDRANT_CONVERSATION_MEMORIES)
    params = info.config.params.vectors
    assert params.size == TEST_EMBEDDING_DIM, (
        f"Collection width must follow embedding_dim, got {params.size}"
    )
    assert params.distance == models.Distance.COSINE, params.distance


async def test_add_memory_wrong_embedding_dim_raises(qdrant, monkeypatch):
    """An embedder disagreeing with the collection must fail, not store garbage.

    This is the ``EMBEDDING_ENDPOINT`` pointed at the wrong model case. Callers
    of ``add_memory`` treat a raised error as a real failure, so the mismatch
    has to surface here rather than at retrieval time.
    """
    await memory_service.ensure_collection(QDRANT_CONVERSATION_MEMORIES)

    async def _wrong_width(texts: list[str]) -> list[list[float]]:
        return [[1.0] * (TEST_EMBEDDING_DIM + 1) for _ in texts]

    monkeypatch.setattr(memory_service, "embed_texts", _wrong_width)

    with pytest.raises(Exception) as excinfo:
        await memory_service.add_memory(ALICE, "a note")

    assert excinfo.value is not None, "A dimension mismatch must not be accepted"


async def test_purge_user_vectors_leaves_other_users_intact(qdrant):
    """Rule 10's purge must be scoped -- deleting everyone's data is worse."""
    await memory_service.add_memory(ALICE, "alice memory")
    await memory_service.add_memory(BOB, "bob memory")
    await memory_service.add_document_chunks(
        ALICE, document_id="d1", filename="a.txt", text="alice document body"
    )

    await memory_service.purge_user_vectors(ALICE)

    assert await memory_service.retrieve_memories(ALICE, "memory") == [], (
        "Alice's memories must be gone"
    )
    assert (
        await memory_service.retrieve_memories(
            ALICE, "document", collection=QDRANT_DOCUMENT_CHUNKS
        )
        == []
    ), "Alice's document chunks must be gone"
    assert await memory_service.retrieve_memories(BOB, "memory") == ["bob memory"], (
        "Bob's memories must survive a purge of Alice"
    )


async def test_export_user_texts_returns_only_owner_rows(qdrant):
    """The GDPR export is another place a bad filter leaks across accounts."""
    await memory_service.add_memory(ALICE, "alice exported note")
    await memory_service.add_memory(BOB, "bob private note")

    texts = await memory_service.export_user_texts(ALICE, QDRANT_CONVERSATION_MEMORIES)

    assert texts == ["alice exported note"], (
        f"Export must contain only the owner's rows, got {texts}"
    )


async def test_delete_document_chunks_removes_only_that_document(qdrant):
    """The two-condition filter (user_id AND document_id) is real here."""
    await memory_service.add_document_chunks(
        ALICE, document_id="keep", filename="keep.txt", text="keep this content"
    )
    await memory_service.add_document_chunks(
        ALICE, document_id="drop", filename="drop.txt", text="drop this content"
    )

    await memory_service.delete_document_chunks(ALICE, "drop")

    remaining = await memory_service.retrieve_memories(
        ALICE, "content", collection=QDRANT_DOCUMENT_CHUNKS, limit=10
    )
    assert remaining == ["keep this content"], (
        f"Only the named document's chunks may be deleted, got {remaining}"
    )


async def test_add_document_chunks_splits_long_text_into_several_points(qdrant):
    """Chunking must actually produce multiple retrievable points."""
    text = "sentence about orbital mechanics. " * 200

    count = await memory_service.add_document_chunks(
        ALICE, document_id="d1", filename="long.txt", text=text
    )

    assert count > 1, f"A long document must chunk into several points, got {count}"
    hits = await memory_service.retrieve_memories(
        ALICE, "orbital", collection=QDRANT_DOCUMENT_CHUNKS, limit=count
    )
    assert len(hits) == count, f"Every chunk must be retrievable, got {len(hits)}"


@pytest.mark.parametrize(
    ("action", "collection", "stored"),
    [
        (DOCUMENT_SEARCH_ACTION, QDRANT_DOCUMENT_CHUNKS, "the uploaded handbook text"),
        (MEMORY_RECALL_ACTION, QDRANT_CONVERSATION_MEMORIES, "an earlier conversation"),
    ],
)
async def test_rag_tool_returns_the_users_own_data(qdrant, action, collection, stored):
    """End-to-end through the agent tool, which is where the outage was visible.

    Both tools formatted ``RAG_NO_RESULTS_NOTICE`` for every query while the
    client method was missing, so the agent layer is the right altitude for a
    guard: it proves the executor reaches storage, not just that it runs.
    """
    if collection == QDRANT_DOCUMENT_CHUNKS:
        await memory_service.add_document_chunks(
            ALICE, document_id="d1", filename="h.txt", text=stored
        )
    else:
        await memory_service.add_memory(ALICE, stored)

    spec = make_rag_tool_specs(ALICE)[action]
    output = await spec.executor(ToolDirective(action=action, args={"query": "text"}))

    assert stored in output, f"The tool must surface the user's own data, got {output}"
    assert RAG_NO_RESULTS_NOTICE not in output, (
        f"Stored data must not report as 'no results', got {output}"
    )


async def test_rag_tool_does_not_surface_another_users_data(qdrant):
    """The tool executor closes over one user id; storage must honour it."""
    await memory_service.add_document_chunks(
        BOB, document_id="d1", filename="b.txt", text="bob confidential filing"
    )

    spec = make_rag_tool_specs(ALICE)[DOCUMENT_SEARCH_ACTION]
    output = await spec.executor(
        ToolDirective(action=DOCUMENT_SEARCH_ACTION, args={"query": "filing"})
    )

    assert "bob confidential filing" not in output, (
        f"One user's documents must never reach another's context, got {output}"
    )
    assert RAG_NO_RESULTS_NOTICE in output, output
