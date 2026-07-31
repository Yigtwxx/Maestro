"""Durable run-header persistence for the task engine.

``task_runs`` is the authoritative record of a task's status and ownership. A
worker owns a run via a heartbeat-renewed lease; when the lease expires (the
worker crashed) the reconciliation sweep atomically re-claims the row. The claim
is a single conditional UPDATE guarded on the lease, so ``uvicorn --workers N``
is safe: exactly one worker wins each orphan.

Runs outside any request scope, so ``SessionLocal`` is a module attribute the
tests can repoint at their in-memory database (mirrors ``usage_service``).
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update

from app.core.constants import RESUMABLE_TASK_STATUSES, TaskStatus
from app.core.database import SessionLocal
from app.models.task_run import TaskRun
from app.models.user import User

# Identifies this process as a run owner: "host:pid:8hex". The random suffix
# distinguishes two workers that share a host+pid across a fast restart.
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

_RESUMABLE_VALUES = tuple(s.value for s in RESUMABLE_TASK_STATUSES)


class ConcurrencyLimitReached(Exception):
    """The user already holds as many in-flight runs as their plan allows."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"concurrent task limit of {limit} reached")
        self.limit = limit


@dataclass(slots=True)
class RunRow:
    """Detached snapshot of a ``task_runs`` row (safe to use after the session)."""

    task_id: str
    user_id: uuid.UUID
    status: str
    current_step: str
    payload: dict
    provider: str
    cancel_requested: bool
    attempt: int
    deadline_at: datetime


def _to_row(run: TaskRun) -> RunRow:
    return RunRow(
        task_id=run.task_id,
        user_id=run.user_id,
        status=run.status,
        current_step=run.current_step,
        payload=dict(run.payload or {}),
        provider=run.provider,
        cancel_requested=run.cancel_requested,
        attempt=run.attempt,
        deadline_at=run.deadline_at,
    )


async def create_run(
    *,
    task_id: str,
    user_id: uuid.UUID,
    payload: dict,
    provider: str,
    deadline_at: datetime,
    max_active: int | None = None,
) -> None:
    """Insert the run header for a freshly started task (owned by this worker).

    ``max_active`` caps how many non-terminal runs the user may hold at once
    (``None`` = no cap; see ``PLAN_MAX_CONCURRENT_TASKS``). It is enforced here
    rather than in the route because this is the *only* insert point for a run
    header: a count in the handler would leave a TOCTOU window several awaits
    wide, and a burst of simultaneous starts would each observe the pre-insert
    count and all pass -- which is exactly the case the cap exists to stop.
    The count and the insert therefore share one transaction, serialized per
    user by a row lock on ``users``. Locking the ``task_runs`` rows instead
    would not work: there is nothing to lock when the count is zero, and no gap
    lock stops a concurrent INSERT.

    Raises ``ConcurrencyLimitReached`` (nothing is written) when the cap is hit.
    """
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        if max_active is not None:
            # SQLite (tests) has no row locks and renders no FOR UPDATE, which
            # is harmless there: it serializes writers process-wide anyway.
            await db.execute(
                select(User.id).where(User.id == user_id).with_for_update()
            )
            active = await db.scalar(
                select(func.count())
                .select_from(TaskRun)
                .where(
                    TaskRun.user_id == user_id,
                    TaskRun.status.in_(_RESUMABLE_VALUES),
                )
            )
            if (active or 0) >= max_active:
                await db.rollback()
                raise ConcurrencyLimitReached(max_active)
        db.add(
            TaskRun(
                task_id=task_id,
                user_id=user_id,
                status=TaskStatus.PENDING.value,
                current_step="route",
                payload=payload,
                provider=provider,
                worker_id=WORKER_ID,
                lease_expires_at=now,  # claimed immediately by the launching worker
                attempt=0,
                deadline_at=deadline_at,
            )
        )
        await db.commit()


async def get_run(task_id: str) -> RunRow | None:
    """Return a detached snapshot of a run header, or None."""
    async with SessionLocal() as db:
        run = await db.get(TaskRun, task_id)
        return _to_row(run) if run is not None else None


async def set_status(
    task_id: str, status: str, *, current_step: str | None = None
) -> None:
    """Advance a run's status (Postgres-first; Mongo is the projection)."""
    values: dict = {"status": status, "updated_at": datetime.now(UTC)}
    if current_step is not None:
        values["current_step"] = current_step
    async with SessionLocal() as db:
        await db.execute(
            update(TaskRun).where(TaskRun.task_id == task_id).values(values)
        )
        await db.commit()


async def request_cancel(task_id: str) -> bool:
    """Mark a run for cancellation. Returns True if a run row existed.

    Persistent so a resumed task honours the cancel even if the request landed
    on a different worker (the ctrl-channel delivery is added in Tur 9).
    """
    async with SessionLocal() as db:
        result = await db.execute(
            update(TaskRun)
            .where(TaskRun.task_id == task_id)
            .values(cancel_requested=True, updated_at=datetime.now(UTC))
        )
        await db.commit()
        return result.rowcount > 0


async def is_cancel_requested(task_id: str) -> bool:
    """Whether cancellation was requested for this run."""
    async with SessionLocal() as db:
        return bool(
            await db.scalar(
                select(TaskRun.cancel_requested).where(TaskRun.task_id == task_id)
            )
        )


async def renew_lease(task_id: str, ttl_seconds: int) -> None:
    """Extend this worker's ownership lease (called by the heartbeat)."""
    expires = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    async with SessionLocal() as db:
        await db.execute(
            update(TaskRun)
            .where(TaskRun.task_id == task_id)
            .values(worker_id=WORKER_ID, lease_expires_at=expires)
        )
        await db.commit()


async def claim_orphans(
    *, ttl_seconds: int, max_attempts: int, limit: int = 20
) -> list[RunRow]:
    """Atomically claim runs whose lease expired (the owning worker crashed).

    Each claim is a single conditional UPDATE guarded on the lease, so two
    workers sweeping at once never both win the same row. Returns the rows this
    worker won, with ``attempt`` already incremented.
    """
    now = datetime.now(UTC)
    new_expiry = now + timedelta(seconds=ttl_seconds)
    claimed: list[RunRow] = []
    async with SessionLocal() as db:
        candidates = (
            await db.scalars(
                select(TaskRun.task_id)
                .where(
                    TaskRun.status.in_(_RESUMABLE_VALUES),
                    (TaskRun.lease_expires_at.is_(None))
                    | (TaskRun.lease_expires_at < now),
                    TaskRun.attempt < max_attempts,
                )
                .limit(limit)
            )
        ).all()
        for task_id in candidates:
            result = await db.execute(
                update(TaskRun)
                .where(
                    TaskRun.task_id == task_id,
                    TaskRun.status.in_(_RESUMABLE_VALUES),
                    (TaskRun.lease_expires_at.is_(None))
                    | (TaskRun.lease_expires_at < now),
                    TaskRun.attempt < max_attempts,
                )
                .values(
                    worker_id=WORKER_ID,
                    lease_expires_at=new_expiry,
                    attempt=TaskRun.attempt + 1,
                    updated_at=now,
                )
            )
            if result.rowcount == 1:
                run = await db.get(TaskRun, task_id)
                if run is not None:
                    claimed.append(_to_row(run))
        await db.commit()
    return claimed


async def list_dead_over_cap(*, max_attempts: int, limit: int = 50) -> list[RunRow]:
    """Orphaned runs that have exhausted their resume attempts.

    These can no longer be reclaimed by ``claim_orphans`` (it filters
    ``attempt < max_attempts``), so without this they would hang at ``running``
    forever. The sweep finalizes each as failed. Finalization is idempotent, so
    no atomic claim is needed here.
    """
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        runs = (
            await db.scalars(
                select(TaskRun)
                .where(
                    TaskRun.status.in_(_RESUMABLE_VALUES),
                    (TaskRun.lease_expires_at.is_(None))
                    | (TaskRun.lease_expires_at < now),
                    TaskRun.attempt >= max_attempts,
                )
                .limit(limit)
            )
        ).all()
        return [_to_row(run) for run in runs]


async def delete_run(task_id: str, user_id: uuid.UUID) -> None:
    """Remove a run header (and, by cascade, its checkpoints/questions)."""
    async with SessionLocal() as db:
        await db.execute(
            delete(TaskRun).where(
                TaskRun.task_id == task_id, TaskRun.user_id == user_id
            )
        )
        await db.commit()
