"""durable task execution engine

Revision ID: 0010_task_runs
Revises: 0009_remove_trial_and_discount
Create Date: 2026-07-12

Backend v2 Tur 8 — durable execution engine foundation.

Adds:
* task_runs         — authoritative run header (status, lease/ownership, deadline)
* task_checkpoints  — append-only per-step results; (task_id, step_key) unique
* task_questions    — persisted human-in-the-loop prompts (survive a restart)
* usage_records.billable — free-tier (Ollama) tokens recorded but not billed
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op
from app.models.base import GUID

revision = "0010_task_runs"
down_revision = "0009_remove_trial_and_discount"
branch_labels = None
depends_on = None

# JSONB on PostgreSQL, portable JSON elsewhere (mirrors models.task_run._JSON).
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "task_runs",
        sa.Column("task_id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "current_step",
            sa.String(length=16),
            nullable=False,
            server_default="route",
        ),
        sa.Column("payload", _JSON, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        comment="Durable run header: status, lease, resume bookkeeping",
    )
    op.create_index("ix_task_runs_user_id", "task_runs", ["user_id"])
    op.create_index(
        "ix_task_runs_reclaim", "task_runs", ["status", "lease_expires_at"]
    )

    op.create_table(
        "task_checkpoints",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("step_key", sa.String(length=80), nullable=False),
        sa.Column("payload", _JSON, nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["task_runs.task_id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("task_id", "step_key", name="uq_task_checkpoints_step"),
        comment="Append-only per-step results (idempotent replay anchor)",
    )
    op.create_index("ix_task_checkpoints_task_id", "task_checkpoints", ["task_id"])

    op.create_table(
        "task_questions",
        sa.Column("question_id", GUID(), primary_key=True),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["task_runs.task_id"], ondelete="CASCADE"
        ),
        comment="Persisted human-in-the-loop questions",
    )
    op.create_index("ix_task_questions_task_id", "task_questions", ["task_id"])

    op.add_column(
        "usage_records",
        sa.Column(
            "billable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("usage_records", "billable")
    op.drop_index("ix_task_questions_task_id", table_name="task_questions")
    op.drop_table("task_questions")
    op.drop_index("ix_task_checkpoints_task_id", table_name="task_checkpoints")
    op.drop_table("task_checkpoints")
    op.drop_index("ix_task_runs_reclaim", table_name="task_runs")
    op.drop_index("ix_task_runs_user_id", table_name="task_runs")
    op.drop_table("task_runs")
