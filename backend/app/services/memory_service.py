"""RAG memory service backed by Qdrant.

Every point carries a ``user_id`` payload and all retrieval is filtered by it,
so one user's memory can never leak into another's (CLAUDE.md §15.4).
Embeddings come from the free/local model (see ``llm_service.embed_texts``).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import models

from app.core.config import settings
from app.core.constants import (
    DOCUMENT_CHUNK_OVERLAP,
    DOCUMENT_CHUNK_SIZE,
    QDRANT_CONVERSATION_MEMORIES,
    QDRANT_DOCUMENT_CHUNKS,
    RAG_NO_RESULTS_NOTICE,
    UNTRUSTED_CONTENT_NOTICE,
)
from app.core.database import get_qdrant_client
from app.services.llm_service import embed_texts

logger = logging.getLogger(__name__)

# Collections confirmed to exist this process; skips the exists round-trip.
_known_collections: set[str] = set()

# Cap on points read back per collection when exporting a user's data. Far above
# any realistic per-user count; guards against an unbounded response.
_EXPORT_SCROLL_LIMIT = 10_000


async def ensure_collection(
    name: str = QDRANT_CONVERSATION_MEMORIES,
) -> None:
    """Create the Qdrant collection if it does not already exist."""
    if name in _known_collections:
        return
    client = get_qdrant_client()
    if not await client.collection_exists(name):
        await client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=settings.embedding_dim, distance=models.Distance.COSINE
            ),
        )
    _known_collections.add(name)


def _user_filter(user_id: uuid.UUID) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="user_id", match=models.MatchValue(value=str(user_id))
            )
        ]
    )


async def add_memory(
    user_id: uuid.UUID,
    text: str,
    *,
    metadata: dict[str, Any] | None = None,
    collection: str = QDRANT_CONVERSATION_MEMORIES,
) -> str:
    """Embed and store a memory for a user. Returns the point id."""
    await ensure_collection(collection)
    vectors = await embed_texts([text])
    point_id = str(uuid.uuid4())
    payload = {"user_id": str(user_id), "text": text, **(metadata or {})}
    await get_qdrant_client().upsert(
        collection_name=collection,
        points=[models.PointStruct(id=point_id, vector=vectors[0], payload=payload)],
    )
    return point_id


async def retrieve_memories(
    user_id: uuid.UUID,
    query: str,
    *,
    limit: int = 5,
    collection: str = QDRANT_CONVERSATION_MEMORIES,
    query_vector: list[float] | None = None,
) -> list[str]:
    """Return the most relevant memory texts for a user's query.

    Pass ``query_vector`` to reuse an already-computed embedding of ``query``
    (avoids re-embedding when searching several collections). Returns an empty
    list if the memory backend or embeddings are unavailable — RAG context is
    best-effort and must never block task execution.

    Degradation is silent to the caller but not to the operator: both failure
    modes are logged at WARNING with a traceback, because an empty list is
    otherwise indistinguishable from a genuine no-match and a misconfigured
    ``EMBEDDING_ENDPOINT`` or an unreachable Qdrant would disable RAG with no
    signal anywhere. The embedding and search steps are separated so the log
    says which half broke.
    """
    if query_vector is None:
        try:
            query_vector = (await embed_texts([query]))[0]
        except Exception:  # noqa: BLE001 - best-effort RAG, degrade gracefully
            logger.warning(
                "RAG embedding failed; returning no context",
                exc_info=True,
                extra={"user_id": str(user_id), "collection": collection},
            )
            return []
    try:
        await ensure_collection(collection)
        hits = await get_qdrant_client().search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=_user_filter(user_id),
            limit=limit,
        )
    except Exception:  # noqa: BLE001 - best-effort RAG, degrade gracefully
        logger.warning(
            "RAG search failed; returning no context",
            exc_info=True,
            extra={"user_id": str(user_id), "collection": collection},
        )
        return []
    return [str(hit.payload.get("text", "")) for hit in hits if hit.payload]


def format_rag_block(hits: list[str], *, open_tag: str, close_tag: str) -> str:
    """Render RAG hits as a delimited, untrusted-content prompt block.

    Uploaded documents and past messages are attacker-controllable, so the block
    carries ``UNTRUSTED_CONTENT_NOTICE`` exactly like web-search and fetch
    results. An empty hit list returns a plain note rather than a bare wrapper,
    so the model never reads an empty block as data (RAG is best-effort; a cold
    Qdrant degrades to no results, never an error)."""
    body = "\n\n".join(f"- {hit.strip()}" for hit in hits if hit.strip())
    if not body:
        return RAG_NO_RESULTS_NOTICE
    return f"{open_tag}\n{body}\n{close_tag}\n{UNTRUSTED_CONTENT_NOTICE}"


def chunk_text(
    text: str,
    *,
    size: int = DOCUMENT_CHUNK_SIZE,
    overlap: int = DOCUMENT_CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping character windows for embedding."""
    text = text.strip()
    if not text:
        return []
    step = max(size - overlap, 1)
    chunks = [text[start : start + size] for start in range(0, len(text), step)]
    return [chunk for chunk in chunks if chunk.strip()]


async def add_document_chunks(
    user_id: uuid.UUID,
    *,
    document_id: str,
    filename: str,
    text: str,
) -> int:
    """Chunk, embed and store a document's text. Returns the chunk count."""
    chunks = chunk_text(text)
    if not chunks:
        return 0
    await ensure_collection(QDRANT_DOCUMENT_CHUNKS)
    vectors = await embed_texts(chunks)
    points = [
        models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "user_id": str(user_id),
                "document_id": document_id,
                "filename": filename,
                "text": chunk,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    await get_qdrant_client().upsert(
        collection_name=QDRANT_DOCUMENT_CHUNKS, points=points
    )
    return len(points)


async def export_user_texts(user_id: uuid.UUID, collection: str) -> list[str]:
    """Read back a user's stored texts from one collection (GDPR Art.20).

    Best-effort: a cold or unreachable Qdrant yields an empty list rather than
    failing the whole export.
    """
    try:
        points, _ = await get_qdrant_client().scroll(
            collection_name=collection,
            scroll_filter=_user_filter(user_id),
            limit=_EXPORT_SCROLL_LIMIT,
            with_payload=True,
            with_vectors=False,
        )
    except Exception:  # noqa: BLE001 - best-effort export, degrade gracefully
        logger.warning(
            "Vector export failed; user data export is incomplete",
            exc_info=True,
            extra={"user_id": str(user_id), "collection": collection},
        )
        return []
    return [str(point.payload.get("text", "")) for point in points if point.payload]


async def purge_user_vectors(user_id: uuid.UUID) -> None:
    """Delete every vector point belonging to a user, in every collection.

    Called from the account purge. Unlike ``delete_document_chunks`` this does
    NOT swallow errors: an unreachable Qdrant must abort the purge so the sweep
    retries, rather than silently leaving the user's memories behind.
    """
    for collection in (QDRANT_CONVERSATION_MEMORIES, QDRANT_DOCUMENT_CHUNKS):
        await get_qdrant_client().delete(
            collection_name=collection,
            points_selector=models.FilterSelector(filter=_user_filter(user_id)),
        )


async def delete_document_chunks(user_id: uuid.UUID, document_id: str) -> None:
    """Remove all vector points belonging to one of a user's documents.

    Best-effort, unlike ``purge_user_vectors``: the caller has already deleted
    the Mongo metadata and there is nothing to retry from. A failure therefore
    orphans the chunks, which is exactly why it is logged rather than passed
    over — the account purge is the backstop that eventually removes them.
    """
    try:
        await get_qdrant_client().delete(
            collection_name=QDRANT_DOCUMENT_CHUNKS,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=str(user_id)),
                        ),
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        ),
                    ]
                )
            ),
        )
    except Exception:  # noqa: BLE001 - deletion is best-effort
        logger.warning(
            "Document chunk deletion failed; vectors are orphaned",
            exc_info=True,
            extra={"user_id": str(user_id), "document_id": document_id},
        )
