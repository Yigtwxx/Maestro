"""Per-step checkpoint persistence for the durable task engine.

An append-only ``task_checkpoints`` row records the result of a completed engine
step. On resume, a step whose checkpoint exists is *replayed* (its payload is
loaded, zero LLM calls); only the interrupted step re-runs. ``(task_id,
step_key)`` is unique, so writing a checkpoint twice is a no-op — LLM calls are
not idempotent, but exactly-once replay of their *results* is (Backend v2 §4.1).

Like ``usage_service``, these helpers run outside any request scope and open
their own session; ``SessionLocal`` is a module attribute so tests can point it
at their in-memory database.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.task_run import TaskCheckpoint


async def is_complete(task_id: str, step_key: str) -> bool:
    """Whether a checkpoint already exists for this step."""
    async with SessionLocal() as db:
        row = await db.scalar(
            select(TaskCheckpoint.id).where(
                TaskCheckpoint.task_id == task_id,
                TaskCheckpoint.step_key == step_key,
            )
        )
        return row is not None


async def load(task_id: str, step_key: str) -> dict | None:
    """Return a completed step's payload, or None if it has not run."""
    async with SessionLocal() as db:
        return await db.scalar(
            select(TaskCheckpoint.payload).where(
                TaskCheckpoint.task_id == task_id,
                TaskCheckpoint.step_key == step_key,
            )
        )


async def write(task_id: str, step_key: str, payload: dict, tokens_used: int) -> None:
    """Persist a step result. Idempotent: a second write for the same key is a
    no-op (the unique constraint is the backstop; the engine owns the run alone,
    so this is about crash-replay, not concurrency)."""
    async with SessionLocal() as db:
        exists = await db.scalar(
            select(TaskCheckpoint.id).where(
                TaskCheckpoint.task_id == task_id,
                TaskCheckpoint.step_key == step_key,
            )
        )
        if exists is not None:
            return
        db.add(
            TaskCheckpoint(
                task_id=task_id,
                step_key=step_key,
                payload=payload,
                tokens_used=tokens_used,
                created_at=datetime.now(UTC),
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()


async def token_sum(task_id: str) -> int:
    """Total tokens recorded across a run's checkpoints (seeds the meter on
    resume so billing includes pre-crash spend)."""
    async with SessionLocal() as db:
        total = await db.scalar(
            select(func.coalesce(func.sum(TaskCheckpoint.tokens_used), 0)).where(
                TaskCheckpoint.task_id == task_id
            )
        )
        return int(total or 0)
