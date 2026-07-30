"""RAG round-trips against a real Qdrant server, over HTTP.

test_qdrant_roundtrip.py covers the same behaviour in local mode, which is the
same library but a different execution path: no HTTP, no server-side filter
engine, no wire serialisation of the payload and filter models. This file is
what proves the two agree, so the cheap tier stays a valid proxy for production.

Deselected by default (see the ``integration`` marker in pyproject.toml); run
with ``docker compose up -d --wait qdrant`` and ``pytest -m integration``.

Writes land in per-test scratch collections — see the ``qdrant_server`` fixture
for why ``collection=`` is passed explicitly here but not in the local tier.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import memory_service
from tests.conftest import TEST_EMBEDDING_DIM

pytestmark = pytest.mark.integration

ALICE = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOB = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


async def test_retrieve_memories_returns_stored_text(qdrant_server):
    """The API-drift guard, against the transport production actually uses."""
    await memory_service.add_memory(
        ALICE, "the runbook lives in ops/", collection=qdrant_server.memories
    )

    hits = await memory_service.retrieve_memories(
        ALICE, "runbook", collection=qdrant_server.memories
    )

    assert hits == ["the runbook lives in ops/"], (
        f"Stored text must survive a real server round-trip, got {hits}"
    )


async def test_retrieve_memories_other_users_data_is_never_returned(qdrant_server):
    """Per-user isolation evaluated by the server's own filter engine (rule 4)."""
    await memory_service.add_memory(
        ALICE, "alice revenue is 12M", collection=qdrant_server.memories
    )
    await memory_service.add_memory(
        BOB, "bob revenue is 90M", collection=qdrant_server.memories
    )

    alice_hits = await memory_service.retrieve_memories(
        ALICE, "revenue", collection=qdrant_server.memories
    )

    assert alice_hits == ["alice revenue is 12M"], (
        f"The server must not return another user's points, got {alice_hits}"
    )


async def test_ensure_collection_creates_with_configured_dimension(qdrant_server):
    """``VectorParams`` must survive serialisation to the server unchanged."""
    await memory_service.ensure_collection(qdrant_server.memories)

    info = await qdrant_server.client.get_collection(qdrant_server.memories)
    assert info.config.params.vectors.size == TEST_EMBEDDING_DIM, info.config.params


async def test_add_memory_wrong_embedding_dim_is_rejected(qdrant_server, monkeypatch):
    """A real server rejects a mismatched vector; the error must not be swallowed."""
    await memory_service.ensure_collection(qdrant_server.memories)

    async def _wrong_width(texts: list[str]) -> list[list[float]]:
        return [[1.0] * (TEST_EMBEDDING_DIM + 1) for _ in texts]

    monkeypatch.setattr(memory_service, "embed_texts", _wrong_width)

    with pytest.raises(Exception) as excinfo:
        await memory_service.add_memory(
            ALICE, "a note", collection=qdrant_server.memories
        )

    assert excinfo.value is not None, "The server must reject a dimension mismatch"


async def test_export_user_texts_returns_only_owner_rows(qdrant_server):
    """``scroll``'s filter is a different server code path from search's."""
    await memory_service.add_memory(
        ALICE, "alice exported note", collection=qdrant_server.memories
    )
    await memory_service.add_memory(
        BOB, "bob private note", collection=qdrant_server.memories
    )

    texts = await memory_service.export_user_texts(ALICE, qdrant_server.memories)

    assert texts == ["alice exported note"], (
        f"Export must contain only the owner's rows, got {texts}"
    )


async def test_document_chunks_round_trip_and_delete(qdrant_server):
    """The document path reaches its collection through the patched constant."""
    count = await memory_service.add_document_chunks(
        ALICE, document_id="d1", filename="h.txt", text="the travel policy body"
    )
    assert count >= 1, count

    hits = await memory_service.retrieve_memories(
        ALICE, "travel policy", collection=qdrant_server.documents
    )
    assert hits == ["the travel policy body"], hits

    await memory_service.delete_document_chunks(ALICE, "d1")

    remaining = await memory_service.retrieve_memories(
        ALICE, "travel policy", collection=qdrant_server.documents
    )
    assert remaining == [], (
        f"Deleted chunks must be gone from the server, got {remaining}"
    )


async def test_purge_user_vectors_leaves_other_users_intact(qdrant_server):
    """Rule 10's purge, against the server, scoped to one account."""
    await memory_service.add_memory(
        ALICE, "alice memory", collection=qdrant_server.memories
    )
    await memory_service.add_memory(
        BOB, "bob memory", collection=qdrant_server.memories
    )
    await memory_service.add_document_chunks(
        ALICE, document_id="d1", filename="a.txt", text="alice document body"
    )

    await memory_service.purge_user_vectors(ALICE)

    assert (
        await memory_service.retrieve_memories(
            ALICE, "memory", collection=qdrant_server.memories
        )
        == []
    ), "Alice's memories must be gone"
    assert await memory_service.retrieve_memories(
        BOB, "memory", collection=qdrant_server.memories
    ) == ["bob memory"], "Bob's memories must survive a purge of Alice"
