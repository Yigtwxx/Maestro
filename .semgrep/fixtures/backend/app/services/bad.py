"""Deliberate invariant violations — one group per rule in ../../../../maestro.yml.

Never imported or executed. Undefined names below are intentional: semgrep
matches source structure, not resolved symbols. Every function here MUST be
reported; the workflow asserts the exact per-rule count.
"""

import httpx
from sqlalchemy import text

from app.services import connected_common
from app.services.connected_common import request_api


# maestro-qdrant-query-without-user-scope (expects 2)


async def leak_vectors(collection, query_vector):
    """Cross-tenant read: no query_filter at all."""
    return await get_qdrant_client().query_points(
        collection_name=collection, query=query_vector, limit=10
    )


async def leak_scroll(collection):
    """Cross-tenant enumeration: no scroll_filter."""
    return await get_qdrant_client().scroll(collection_name=collection, limit=10)


# maestro-connected-api-redirect-optin (expects 2)


async def redirect_optin(creds):
    """The repo_intel-only redirect opt-in, adopted by another caller."""
    return await request_api(
        "GET",
        "https://x.test",
        credentials=creds,
        follow_redirect_host="api.x.test",
    )


async def redirect_optin_module(creds):
    """Same violation reached through the module rather than the symbol."""
    return await connected_common.request_api(
        "GET", "https://x.test", follow_redirect_host="api.x.test"
    )


# maestro-http-client-follows-redirects (expects 1)


async def loose_client():
    """A redirect-following client outside the exempt data_fetch tier."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=5) as client:
        return await client.get("https://x.test")


# maestro-secret-in-log (expects 3)


def log_secret(logger, row, settings):
    """A decrypted key, a master key and a password reaching a logger."""
    logger.info("decrypted %s", row.encrypted_key)
    logger.debug("master", extra={"k": settings.master_key})
    logger.warning("pw %s", user_password)


# maestro-raw-sql-outside-alembic (expects 1)


async def raw_sql(conn):
    """A schema/data change that belongs in an Alembic revision."""
    await conn.execute(text("UPDATE users SET role='admin'"))
