"""Document ingestion service for the RAG knowledge base.

Uploaded text is chunked and embedded into the per-user ``document_chunks``
vector collection (CLAUDE.md §10); lightweight metadata is kept in MongoDB
(``documents``). All reads/writes are scoped to the owner (CLAUDE.md §15.4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.constants import MongoCollection
from app.core.database import get_mongo_db
from app.services import memory_service


class DocumentError(ValueError):
    """Raised when a document cannot be ingested."""


@dataclass(slots=True, frozen=True)
class StorageUsage:
    """What a user's knowledge base currently occupies."""

    documents: int
    bytes: int


def _collection():
    return get_mongo_db()[MongoCollection.DOCUMENTS.value]


async def ingest(user_id: uuid.UUID, filename: str, content: bytes) -> dict[str, Any]:
    """Decode, chunk, embed and register an uploaded document."""
    text = content.decode("utf-8", errors="ignore")
    if not text.strip():
        raise DocumentError("Document is empty or not valid UTF-8 text.")

    document_id = str(uuid.uuid4())
    chunk_count = await memory_service.add_document_chunks(
        user_id, document_id=document_id, filename=filename, text=text
    )
    if chunk_count == 0:
        raise DocumentError("Document produced no indexable content.")

    document = {
        "id": document_id,
        "user_id": str(user_id),
        "filename": filename,
        "chunk_count": chunk_count,
        # Raw upload size, which is what the storage quota is denominated in.
        # Recorded here rather than derived from ``chunk_count`` because the
        # chunker overlaps and drops blank runs, so chunks are a lossy proxy.
        "size_bytes": len(content),
        "created_at": datetime.now(UTC),
    }
    await _collection().insert_one(dict(document))
    return document


async def storage_usage(user_id: uuid.UUID) -> StorageUsage:
    """How many documents and bytes this user is holding.

    Summed in Python over a projection rather than through an aggregation
    pipeline: the row count is bounded by ``PLAN_MAX_DOCUMENTS``, so this reads
    a few hundred integers at worst. Rows written before ``size_bytes`` existed
    count as zero — they under-report rather than locking an early account out
    of its own knowledge base, and the count cap still bounds them.
    """
    cursor = _collection().find({"user_id": str(user_id)}, {"_id": 0, "size_bytes": 1})
    documents = 0
    total = 0
    async for doc in cursor:
        documents += 1
        total += int(doc.get("size_bytes") or 0)
    return StorageUsage(documents=documents, bytes=total)


async def list_documents(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """List a user's uploaded documents, newest first."""
    cursor = (
        _collection().find({"user_id": str(user_id)}, {"_id": 0}).sort("created_at", -1)
    )
    return [doc async for doc in cursor]


async def delete_document(user_id: uuid.UUID, document_id: str) -> bool:
    """Delete a document's metadata and its vector chunks. Owner-only."""
    result = await _collection().delete_one(
        {"id": document_id, "user_id": str(user_id)}
    )
    if result.deleted_count == 0:
        return False
    await memory_service.delete_document_chunks(user_id, document_id)
    return True
