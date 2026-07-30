"""The upload path, end to end, against a real vector store.

``document_service`` had no test at all: the one route reference in the suite
asserts a 403 for a locked account and never reaches the service. That left the
whole ingest chain -- decode, chunk, embed, upsert, register metadata --
covered only by the fact that nothing imported it.

Qdrant is real here (see ``conftest.qdrant``); Mongo is the in-memory
``FakeMongoCollection``, because what these tests are about is whether the
chunks become retrievable, and the metadata row is a flat insert either way.
Real-Mongo coverage lives in test_integration_mongo.py.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.constants import QDRANT_DOCUMENT_CHUNKS
from app.services import document_service, memory_service
from tests.conftest import FakeMongoCollection

ALICE = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOB = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

HANDBOOK = b"The travel policy allows economy fares booked fourteen days ahead."


@pytest.fixture
def documents_db(monkeypatch) -> FakeMongoCollection:
    """Point ``document_service`` at an in-memory metadata collection."""
    collection = FakeMongoCollection()
    monkeypatch.setattr(document_service, "_collection", lambda: collection)
    return collection


async def _search(user_id: uuid.UUID, query: str, limit: int = 10) -> list[str]:
    return await memory_service.retrieve_memories(
        user_id, query, collection=QDRANT_DOCUMENT_CHUNKS, limit=limit
    )


async def test_ingest_then_search_returns_the_chunk(qdrant, documents_db):
    """The whole chain has to land: an ingested document must be findable."""
    document = await document_service.ingest(ALICE, "handbook.txt", HANDBOOK)

    assert document["chunk_count"] >= 1, document
    hits = await _search(ALICE, "travel policy")
    assert HANDBOOK.decode() in hits, f"Ingested text must be retrievable, got {hits}"


async def test_ingest_registers_metadata_for_the_owner(qdrant, documents_db):
    await document_service.ingest(ALICE, "handbook.txt", HANDBOOK)

    listed = await document_service.list_documents(ALICE)
    assert len(listed) == 1, listed
    assert listed[0]["filename"] == "handbook.txt", listed[0]
    assert listed[0]["user_id"] == str(ALICE), listed[0]


async def test_ingest_indexes_chunks_under_the_owner_only(qdrant, documents_db):
    """A second account must not reach the uploader's document (rule 4)."""
    await document_service.ingest(ALICE, "handbook.txt", HANDBOOK)

    assert await _search(BOB, "travel policy") == [], (
        "Another user's upload must never be retrievable"
    )
    assert await document_service.list_documents(BOB) == [], (
        "Another user's metadata must not be listed"
    )


async def test_ingest_empty_document_raises_document_error(qdrant, documents_db):
    with pytest.raises(document_service.DocumentError):
        await document_service.ingest(ALICE, "empty.txt", b"   \n\t  ")

    assert await document_service.list_documents(ALICE) == [], (
        "A rejected upload must leave no metadata behind"
    )


async def test_ingest_undecodable_bytes_are_ignored_not_fatal(qdrant, documents_db):
    """``errors="ignore"`` is deliberate; the readable remainder still indexes."""
    document = await document_service.ingest(
        ALICE, "mixed.bin", b"\xff\xfe readable tail content"
    )

    assert document["chunk_count"] >= 1, document
    hits = await _search(ALICE, "readable tail")
    assert any("readable tail content" in hit for hit in hits), hits


async def test_delete_document_removes_chunks_from_qdrant(qdrant, documents_db):
    """Metadata and vectors must go together, or the vectors are unaddressable."""
    document = await document_service.ingest(ALICE, "handbook.txt", HANDBOOK)

    deleted = await document_service.delete_document(ALICE, document["id"])

    assert deleted is True, "Deleting an owned document must report success"
    assert await _search(ALICE, "travel policy") == [], (
        "Chunks must not outlive their metadata row"
    )
    assert await document_service.list_documents(ALICE) == [], "Metadata must be gone"


async def test_delete_document_by_non_owner_leaves_chunks_intact(qdrant, documents_db):
    """A non-owner's delete must be a no-op on both stores, not a partial one."""
    document = await document_service.ingest(ALICE, "handbook.txt", HANDBOOK)

    deleted = await document_service.delete_document(BOB, document["id"])

    assert deleted is False, "A non-owner must not delete another user's document"
    assert await _search(ALICE, "travel policy") != [], (
        "The owner's chunks must survive a foreign delete attempt"
    )
