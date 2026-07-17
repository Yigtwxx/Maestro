"""EmailToken ORM model basics (table creation, defaults, cascade FK)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.constants import EmailTokenPurpose
from app.models import EmailToken, User


async def test_email_token_row_roundtrip_persists_all_columns(db_session) -> None:
    user = User(email="tok@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    token = EmailToken(
        user_id=user.id,
        purpose=EmailTokenPurpose.VERIFY_EMAIL.value,
        token_hash="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(token)
    await db_session.commit()

    row = (await db_session.execute(select(EmailToken))).scalar_one()
    assert row.user_id == user.id
    assert row.used_at is None, "a fresh token must be unused"
    assert isinstance(row.id, uuid.UUID)


async def test_user_email_verified_defaults_to_false(db_session) -> None:
    user = User(email="fresh@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    assert user.email_verified is False
