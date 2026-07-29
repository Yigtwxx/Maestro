"""pending address for the email-change flow

Revision ID: 0017_email_token_new_email
Revises: 0016_email_token_codes
Create Date: 2026-07-29

Changing an account's address now goes through ``POST /users/me/email``, which
issues a CHANGE_EMAIL token instead of writing ``users.email`` directly. The
pending address rides on the token row rather than on ``users`` so it expires
and rotates with the token, needs no separate cleanup, and binds a token to the
one address it was issued for -- an older link can never apply a newer address.

``purpose`` is a plain String(20), so the new enum value needs no migration of
its own; only this column does.

The test suite builds its schema with ``Base.metadata.create_all``, so this
migration is never exercised by pytest -- keep it in sync with the ORM by hand.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0017_email_token_new_email"
down_revision = "0016_email_token_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_tokens", sa.Column("new_email", sa.String(length=320), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("email_tokens", "new_email")
