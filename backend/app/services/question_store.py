"""Persisted human-in-the-loop questions.

A ``task_questions`` row records a clarifying question the Main Agent asked, so a
pending question is visible in durable state (and, from Tur 9, answerable from
any worker). Cross-worker answer *delivery* still rides the in-process future in
Tur 8; this store gives the question a durable status (pending -> answered |
expired) and backs the ``awaiting_answer`` task status.

Opens its own session (runs outside a request); ``SessionLocal`` is a module
attribute the tests repoint at their in-memory database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models.task_run import TaskQuestion


async def create_question(
    *, task_id: str, question: str, expires_at: datetime
) -> uuid.UUID:
    """Record a pending question and return its id."""
    question_id = uuid.uuid4()
    async with SessionLocal() as db:
        db.add(
            TaskQuestion(
                question_id=question_id,
                task_id=task_id,
                question=question,
                status="pending",
                asked_at=datetime.now(UTC),
                expires_at=expires_at,
            )
        )
        await db.commit()
    return question_id


async def answer_question(question_id: uuid.UUID, answer: str) -> None:
    """Mark a question answered (idempotent; only affects a pending row)."""
    async with SessionLocal() as db:
        await db.execute(
            update(TaskQuestion)
            .where(
                TaskQuestion.question_id == question_id,
                TaskQuestion.status == "pending",
            )
            .values(answer=answer, status="answered", answered_at=datetime.now(UTC))
        )
        await db.commit()


async def expire_question(question_id: uuid.UUID) -> None:
    """Mark a question expired (the agent proceeded best-effort)."""
    async with SessionLocal() as db:
        await db.execute(
            update(TaskQuestion)
            .where(
                TaskQuestion.question_id == question_id,
                TaskQuestion.status == "pending",
            )
            .values(status="expired")
        )
        await db.commit()


async def latest_pending(task_id: str) -> TaskQuestion | None:
    """Most recent still-pending question for a task, or None."""
    async with SessionLocal() as db:
        return await db.scalar(
            select(TaskQuestion)
            .where(TaskQuestion.task_id == task_id, TaskQuestion.status == "pending")
            .order_by(TaskQuestion.asked_at.desc())
        )
