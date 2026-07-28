"""Compliant shapes that must produce zero findings.

These mirror real call sites in `backend/app/`. A false positive here is as much
a bug as a missed detection: a rule that fires on correct code gets muted, and a
muted rule protects nothing.
"""

import httpx
from sqlalchemy import text


async def scoped_search(collection, query_vector, user_id):
    """The `_user_filter` helper — how memory_service scopes its RAG search."""
    return await get_qdrant_client().search(
        collection_name=collection,
        query_vector=query_vector,
        query_filter=_user_filter(user_id),
        limit=10,
    )


async def scoped_delete_inline(user_id, document_id):
    """An inline Filter — how the document purge path scopes its delete.

    Equally valid, and the reason the rule accepts a nested `user_id` condition
    rather than only the helper's name.
    """
    return await get_qdrant_client().delete(
        collection_name="document_chunks",
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id", match=models.MatchValue(value=str(user_id))
                    ),
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=str(document_id)),
                    ),
                ]
            )
        ),
    )


async def safe_client():
    """The shared outbound client: redirects disabled."""
    async with httpx.AsyncClient(follow_redirects=False) as client:
        return await client.get("https://x.test")


def log_identifiers(logger, user_id, tokens_used):
    """Identifiers and counters are fine.

    `tokens_used` is why the secret pattern deliberately omits a bare `token`
    match — token accounting is logged all over the task engine.
    """
    logger.info("task done", extra={"user_id": str(user_id), "tokens_used": tokens_used})


def mention_a_secret_in_prose(logger):
    """A message that merely names a credential is not a leak."""
    logger.warning("api_key missing for provider")


async def sanctioned_probe(conn):
    """The one permitted raw statement: the connection health probe."""
    await conn.execute(text("SELECT 1"))
