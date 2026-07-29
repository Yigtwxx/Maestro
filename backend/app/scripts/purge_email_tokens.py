"""Delete email_tokens rows whose links died long ago.

Run with ``python -m app.scripts.purge_email_tokens`` from ``backend/``, once a
day, from cron or a container scheduler.

Why a script and not an in-process task: the same reasoning as
``purge_deleted_accounts`` -- a task in the FastAPI lifespan would run once per
API instance (racing itself) and tie the sweep to API uptime, while a lazy
per-request sweep would never fire for the dormant rows that are exactly the
problem.

Retention is a single predicate, ``expires_at < cutoff``. ``expires_at`` is set
unconditionally at issue, so every dead row -- redeemed, superseded by a newer
token, or never clicked -- ages past it. Adding ``used_at IS NOT NULL`` would
match nothing extra and would cost the index scan.

Deleting redeemed rows does not weaken replay protection: a replayed token
whose row is gone matches zero rows and is rejected exactly as one still
marked used.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EMAIL_TOKEN_PURGE_BATCH, EMAIL_TOKEN_RETENTION_DAYS
from app.core.database import SessionLocal, close_connections
from app.models.email_token import EmailToken

logger = logging.getLogger(__name__)

# Arbitrary but stable key identifying this job to `pg_try_advisory_lock`.
# Distinct from purge_deleted_accounts' 0x4D414550 so the two never block
# each other.
_ADVISORY_LOCK_KEY = 0x4D414554  # "MAET"

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


async def purge_expired_tokens(
    db: AsyncSession,
    *,
    retention_days: int = EMAIL_TOKEN_RETENTION_DAYS,
    batch_size: int = EMAIL_TOKEN_PURGE_BATCH,
    dry_run: bool = False,
) -> int:
    """Delete every token row past the retention window. Returns the count.

    Deletes in batches, committing each one, so a first run over a large
    backlog never holds a single long-lived lock.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    deleted = 0
    while True:
        ids = (
            await db.scalars(
                sa.select(EmailToken.id)
                .where(EmailToken.expires_at < cutoff)
                .limit(batch_size)
            )
        ).all()
        if not ids:
            break
        if dry_run:
            # Report what the first batch would remove without touching it.
            deleted += len(ids)
            break
        await db.execute(
            sa.delete(EmailToken)
            .where(EmailToken.id.in_(ids))
            # Bulk DML: skip the ORM evaluate pass (naive-vs-aware compare on
            # SQLite), same as email_service.issue_token.
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        deleted += len(ids)
    return deleted


async def _main(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        async with SessionLocal() as db:
            if not await _acquire_lock(db):
                logger.info("Another token sweep holds the lock; exiting.")
                return
            try:
                deleted = await purge_expired_tokens(
                    db, retention_days=args.retention_days, dry_run=args.dry_run
                )
            finally:
                await _release_lock(db)
        verb = "Would delete" if args.dry_run else "Deleted"
        logger.info("%s %d expired email token(s).", verb, deleted)
    finally:
        await close_connections()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete email_tokens rows past the retention window."
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=EMAIL_TOKEN_RETENTION_DAYS,
        help="How long a dead row is kept (default: %(default)s).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what the first batch would remove, then stop.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(_main(_parse_args()))
