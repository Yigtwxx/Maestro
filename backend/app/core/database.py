"""Database connections: PostgreSQL (async SQLAlchemy), MongoDB (Motor),
Qdrant (vector DB), Redis (rate-limit buckets).

Connections are created lazily and shared process-wide. FastAPI lifespan
(`app.main`) is responsible for closing them on shutdown.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.constants import MongoCollection

logger = logging.getLogger(__name__)

# --- PostgreSQL (SQLAlchemy async) ----------------------------------------

engine: AsyncEngine = create_async_engine(
    settings.postgres_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a scoped async DB session."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# --- MongoDB (Motor) ------------------------------------------------------

_mongo_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    """Return the shared Motor client (created on first use)."""
    global _mongo_client
    if _mongo_client is None:
        # `tz_aware` marks the dates Mongo returns as UTC. Without it they come
        # back naive, serialize without an offset, and clients read them as
        # local time — shifting every task timestamp by the UTC offset.
        _mongo_client = AsyncIOMotorClient(settings.mongodb_url, tz_aware=True)
    return _mongo_client


def get_mongo_db() -> AsyncIOMotorDatabase:
    """Return the application's MongoDB database."""
    return get_mongo_client()[settings.mongodb_db_name]


# --- Qdrant (vector DB) ---------------------------------------------------

_qdrant_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    """Return the shared async Qdrant client (created on first use)."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
    return _qdrant_client


# --- Redis (rate limiting) ------------------------------------------------

# The limiter runs on every request, so a slow Redis must not become slow
# requests: treat anything past this budget as an outage and fall back.
_REDIS_TIMEOUT_SECONDS = 0.25

_redis_client: Redis | None = None


def get_redis_client() -> Redis | None:
    """Return the shared Redis client, or None when no `REDIS_URL` is set.

    A None return is the supported single-instance configuration, not an error:
    `app.utils.rate_limiter` then keeps its buckets in process memory.
    """
    global _redis_client
    if not settings.redis_url:
        return None
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=_REDIS_TIMEOUT_SECONDS,
            socket_timeout=_REDIS_TIMEOUT_SECONDS,
            decode_responses=True,
        )
    return _redis_client


# --- MongoDB index management ---------------------------------------------

_TTL_INDEX_NAME = "ttl_created_at"
_SECONDS_PER_DAY = 86_400
# Raised when an index of the same name already exists with different options
# — for a TTL index that means the retention window changed.
_INDEX_OPTIONS_CONFLICT = 85


async def _ensure_ttl_index(
    db: AsyncIOMotorDatabase, collection: str, ttl_seconds: int
) -> None:
    """Create the `created_at` TTL index, retuning it if the window changed."""
    try:
        await db[collection].create_index(
            "created_at", expireAfterSeconds=ttl_seconds, name=_TTL_INDEX_NAME
        )
        return
    except OperationFailure as exc:
        if exc.code != _INDEX_OPTIONS_CONFLICT:
            raise

    # `collMod` retunes the index in place; drop-and-recreate would leave
    # documents unexpired in the gap.
    try:
        await db.command(
            {
                "collMod": collection,
                "index": {
                    "name": _TTL_INDEX_NAME,
                    "expireAfterSeconds": ttl_seconds,
                },
            }
        )
    except OperationFailure:
        logger.warning(
            "collMod failed on %s; recreating the TTL index", collection, exc_info=True
        )
        await db[collection].drop_index(_TTL_INDEX_NAME)
        await db[collection].create_index(
            "created_at", expireAfterSeconds=ttl_seconds, name=_TTL_INDEX_NAME
        )


async def ensure_indexes() -> None:
    """Create MongoDB indexes on startup. Idempotent and best-effort.

    Covers the hot query paths (`task_id` lookups, owner + recency for the task
    history list) and the retention TTL. Failures are logged, never raised:
    Mongo may still be starting and the API must come up regardless.
    """
    ttl_seconds = settings.task_retention_days * _SECONDS_PER_DAY
    sessions = MongoCollection.TASK_SESSIONS.value
    logs = MongoCollection.AGENT_LOGS.value
    try:
        db = get_mongo_db()
    except Exception:  # noqa: BLE001 - a bad Mongo URL must not block startup
        logger.warning("Cannot reach MongoDB to ensure indexes", exc_info=True)
        return

    for collection, keys in (
        (sessions, [("task_id", ASCENDING)]),
        # Backs the task history list: filter by owner, newest first.
        (sessions, [("user_id", ASCENDING), ("created_at", DESCENDING)]),
        (logs, [("task_id", ASCENDING)]),
    ):
        try:
            await db[collection].create_index(keys)
        except Exception:  # noqa: BLE001 - a missing index only costs speed
            logger.warning(
                "Failed to create index %s on %s", keys, collection, exc_info=True
            )

    # Kept separate: retention must still be attempted if an index above failed.
    for collection in (sessions, logs):
        try:
            await _ensure_ttl_index(db, collection, ttl_seconds)
        except Exception:  # noqa: BLE001 - startup must not depend on Mongo
            logger.warning(
                "Failed to ensure the TTL index on %s", collection, exc_info=True
            )


async def close_connections() -> None:
    """Close all shared connections (called on app shutdown)."""
    global _mongo_client, _qdrant_client, _redis_client
    await engine.dispose()
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
