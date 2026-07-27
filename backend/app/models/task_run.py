"""Durable task-execution ORM models (PostgreSQL).

The engine (``services/task_engine``) treats these rows as the authoritative
record of a task's lifecycle: ``task_runs`` carries status, ownership (lease),
and the resume deadline; ``task_checkpoints`` is an append-only, per-step result
log that lets a resumed worker replay completed steps without repeating LLM
spend; ``task_questions`` persists human-in-the-loop prompts so a pending
question survives a restart. MongoDB ``task_sessions`` becomes a projection of
``task_runs.status`` — every status write goes Postgres-first, Mongo-second.

BYOK keys are never written here: a resumed run re-decrypts the key from
``api_keys`` (Backend v2 §4.1).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, Base, TimestampMixin, _uuid_pk

# JSONB on PostgreSQL, portable JSON everywhere else (SQLite in tests). We store
# and load whole payloads without indexing into them, so JSON vs JSONB only
# affects the production storage format, never the query shape.
_JSON = JSON().with_variant(JSONB(), "postgresql")


class TaskRun(Base, TimestampMixin):
    """Run header: ownership, lease, status and resume bookkeeping for one task."""

    __tablename__ = "task_runs"

    # Same id as ``task_sessions.task_id`` (a string UUID).
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32))
    current_step: Mapped[str] = mapped_column(String(16), default="route")
    # Frozen ``TaskCreate`` dump (prompt, domain, flags, limits). Never a key.
    payload: Mapped[dict] = mapped_column(_JSON)
    provider: Mapped[str] = mapped_column(String(32))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    # "host:pid:8hex"; NULL means unowned (reclaimable by the sweep).
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt: Mapped[int] = mapped_column(SmallInteger, default=0)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # Backs the reclaim sweep: scan by status, order/filter by lease expiry.
        Index("ix_task_runs_reclaim", "status", "lease_expires_at"),
        {"comment": "Durable run header: status, lease, resume bookkeeping"},
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<TaskRun task_id={self.task_id!r} status={self.status!r}>"


class TaskCheckpoint(Base):
    """Append-only per-step result. ``(task_id, step_key)`` is unique (idempotent)."""

    __tablename__ = "task_checkpoints"

    # BIGSERIAL on PostgreSQL; SQLite only auto-assigns a rowid for INTEGER
    # PRIMARY KEY, so the test backend needs the plain-Integer variant.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("task_runs.task_id", ondelete="CASCADE"),
        index=True,
    )
    step_key: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(_JSON)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("task_id", "step_key", name="uq_task_checkpoints_step"),
        {"comment": "Append-only per-step results (idempotent replay anchor)"},
    )


class TaskQuestion(Base):
    """A human-in-the-loop question, persisted so it survives a worker restart."""

    __tablename__ = "task_questions"

    question_id: Mapped[uuid.UUID] = _uuid_pk()
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("task_runs.task_id", ondelete="CASCADE"),
        index=True,
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16))  # pending | answered | expired
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = ({"comment": "Persisted human-in-the-loop questions"},)
