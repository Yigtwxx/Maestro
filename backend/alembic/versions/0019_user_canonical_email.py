"""add users.canonical_email with a unique index

Revision ID: 0019_user_canonical_email
Revises: 0018_free_plan
Create Date: 2026-07-31

One mailbox may now hold one account: `you+1@gmail.com` and `y.o.u@gmail.com`
reduce to the same canonical address, and the unique index added here is what
enforces it -- rather than a SELECT before the INSERT, which would be a TOCTOU
window and a timing oracle in front of the registration endpoint.

Existing rows may already collide under that rule, in which case creating the
index would fail. `unique_canonicals` drops every member of a colliding group,
leaving those rows NULL: Postgres unique indexes do not conflict on NULL, so
those accounts are grandfathered and keep working, while every registration
after this migration writes a value.

Unlike 0012 and 0018, this migration **imports application code**
(`utils.email_identity`) instead of pinning its literals locally. The
convention exists so a later enum change cannot rewrite history; here the
opposite is required. The backfilled values have to agree with whatever rule the
running application enforces at the moment of upgrade -- if they diverged, the
column would be populated under one rule and enforced under another, and the
index would reject addresses the app considers distinct. The rule also cannot be
expressed in SQL, so this is a Python data migration by necessity.

The test suite builds its schema with `Base.metadata.create_all` and never runs
this file; only the CI smoke job does. Review it as SQL.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.utils.email_identity import unique_canonicals

revision = "0019_user_canonical_email"
down_revision = "0018_free_plan"
branch_labels = None
depends_on = None

_INDEX = "ix_users_canonical_email"


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("canonical_email", sa.String(length=320), nullable=True)
    )

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, email FROM users")).all()
    for row_id, canonical in unique_canonicals(
        [(row.id, row.email) for row in rows]
    ).items():
        conn.execute(
            sa.text("UPDATE users SET canonical_email = :canonical WHERE id = :id"),
            {"canonical": canonical, "id": row_id},
        )

    op.create_index(_INDEX, "users", ["canonical_email"], unique=True)


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="users")
    op.drop_column("users", "canonical_email")
