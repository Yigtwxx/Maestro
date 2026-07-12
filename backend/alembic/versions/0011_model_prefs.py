"""per-role model preferences

Revision ID: 0011_model_prefs
Revises: 0010_task_runs
Create Date: 2026-07-12

Backend v2 Tur 10 — model routing.

Adds ``users.model_preferences`` (JSONB): a per-role map of model names applied
when a task does not pin a model, e.g. {"main": "claude-opus-4-8"}.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0011_model_prefs"
down_revision = "0010_task_runs"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("users", sa.Column("model_preferences", _JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "model_preferences")
