"""api keys: custom OpenAI-compatible endpoint columns

Adds ``api_keys.base_url`` and ``api_keys.model``. Both are NULL for every
named provider; they are only populated for the ``custom`` provider, where the
user connects an arbitrary OpenAI-compatible endpoint (self-hosted, OpenRouter,
LM Studio, vLLM, ...) by supplying a base URL and a model name.

Storing these as real columns (rather than encoding them into ``label``) keeps
them validatable, queryable, and separate from the user-facing label.

Revision ID: 0005_api_key_endpoint
Revises: 0004_account_deletion
Create Date: 2026-07-11

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_api_key_endpoint"
down_revision = "0004_account_deletion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("base_url", sa.String(512), nullable=True))
    op.add_column("api_keys", sa.Column("model", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "model")
    op.drop_column("api_keys", "base_url")
