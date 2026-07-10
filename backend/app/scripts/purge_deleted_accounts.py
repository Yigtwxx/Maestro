"""Purge accounts whose deletion grace period has lapsed.

Run with ``python -m app.scripts.purge_deleted_accounts`` from ``backend/``,
once a day, from cron or a container scheduler.

Why a script and not an in-process task: a background task in the FastAPI
lifespan would run once per API instance (racing itself), die silently if its
loop raised, and tie the 30-day promise to API uptime. Computing the purge
lazily on request is worse still -- a user who never signs in again would never
be purged.

Failure semantics: each account is purged in its own transaction, with the
PostgreSQL row deleted LAST. If Mongo or Qdrant is unreachable the transaction
rolls back, ``deletion_requested_at`` stays set, and the next run retries. Every
purge operation is idempotent, so at-least-once execution is safe.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ACCOUNT_DELETION_GRACE_DAYS
from app.core.database import SessionLocal, close_connections
from app.models.user import User
from app.services import user_service

logger = logging.getLogger(__name__)

# Arbitrary but stable key identifying this job to `pg_try_advisory_lock`.
_ADVISORY_LOCK_KEY = 0x4D414550  # "MAEP"

_POSTGRES = "postgresql"


async def _acquire_lock(db: AsyncSession) -> bool:
    """Take a cross-instance lock, if the backend supports one.

    SQLite (the test suite) has no advisory locks, and no concurrency to guard
    against either, so the sweep simply proceeds there.
    """
    if db.bind.dialect.name != _POSTGRES:
        return True
    locked = await db.scalar(
        sa.select(sa.func.pg_try_advisory_lock(_ADVISORY_LOCK_KEY))
    )
    return bool(locked)


async def _release_lock(db: AsyncSession) -> None:
    """Release the advisory lock taken by ``_acquire_lock``."""
    if db.bind.dialect.name == _POSTGRES:
        await db.scalar(sa.select(sa.func.pg_advisory_unlock(_ADVISORY_LOCK_KEY)))


async def purge_due_accounts(db: AsyncSession) -> int:
    """Purge every account past its grace period. Returns how many were purged.

    A failure on one account is logged and skipped; its flag stays set so the
    next run retries it.
    """
    cutoff = datetime.now(UTC) - timedelta(days=ACCOUNT_DELETION_GRACE_DAYS)
    due = (
        await db.scalars(
            sa.select(User).where(
                User.deletion_requested_at.is_not(None),
                User.deletion_requested_at < cutoff,
            )
        )
    ).all()

    purged = 0
    for user in due:
        user_id = user.id
        try:
            # Mongo + Qdrant first: the PostgreSQL row carries the flag that
            # lets us find this account again if anything below fails.
            await user_service.purge_user_data(user_id)
            await db.delete(user)
            await db.commit()
        except Exception:  # noqa: BLE001 - one bad account must not stop the sweep
            await db.rollback()
            logger.exception("Failed to purge account %s; will retry next run", user_id)
            continue
        purged += 1
        logger.info("Purged account %s", user_id)
    return purged


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        async with SessionLocal() as db:
            if not await _acquire_lock(db):
                logger.info("Another purge sweep holds the lock; exiting.")
                return
            try:
                purged = await purge_due_accounts(db)
            finally:
                await _release_lock(db)
        logger.info("Purged %d account(s).", purged)
    finally:
        await close_connections()


if __name__ == "__main__":
    asyncio.run(_main())
