"""Database connections: PostgreSQL (async SQLAlchemy), MongoDB (Motor),
Qdrant (vector DB).

Connections are created lazily and shared process-wide. FastAPI lifespan
(`app.main`) is responsible for closing them on shutdown.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

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
        _mongo_client = AsyncIOMotorClient(settings.mongodb_url)
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


async def close_connections() -> None:
    """Close all shared connections (called on app shutdown)."""
    global _mongo_client, _qdrant_client
    await engine.dispose()
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None
