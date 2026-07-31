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

The backfill pages its reads and batches its writes. All (id, email) pairs are
collected first (chunking the read to bound memory per round trip), then
`unique_canonicals` is called once over the complete set — a per-chunk call
would miss collisions that straddle chunk boundaries, and the unique index would
then fail to prevent duplicates. The resulting updates are batched with
executemany to reduce round trips.

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
_BACKFILL_CHUNK_SIZE = 1000


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("canonical_email", sa.String(length=320), nullable=True)
    )

    conn = op.get_bind()

    # Collect all (id, email) pairs by chunking the read
    all_pairs = []
    offset = 0
    while True:
        rows = conn.execute(
            sa.text(
                "SELECT id, email FROM users ORDER BY id LIMIT :limit OFFSET :offset"
            ),
            {"limit": _BACKFILL_CHUNK_SIZE, "offset": offset},
        ).all()
        if not rows:
            break
        all_pairs.extend([(row.id, row.email) for row in rows])
        offset += _BACKFILL_CHUNK_SIZE

    # Call unique_canonicals once over the complete set
    # (calling per-chunk would miss collisions that straddle chunk boundaries)
    canonical_map = unique_canonicals(all_pairs)

    # Batch the updates in chunks using executemany
    for i in range(0, len(canonical_map), _BACKFILL_CHUNK_SIZE):
        chunk_ids = list(canonical_map.keys())[i : i + _BACKFILL_CHUNK_SIZE]
        if chunk_ids:
            params = [
                {"canonical": canonical_map[row_id], "id": row_id} for row_id in chunk_ids
            ]
            conn.execute(
                sa.text(
                    "UPDATE users SET canonical_email = :canonical WHERE id = :id"
                ),
                params,
            )

    op.create_index(_INDEX, "users", ["canonical_email"], unique=True)


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="users")
    op.drop_column("users", "canonical_email")
