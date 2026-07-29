"""Retention sweep over email_tokens: what it removes, and what it must not."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.constants import EMAIL_TOKEN_RETENTION_DAYS, EmailTokenPurpose
from app.models import EmailToken, User
from app.scripts.purge_email_tokens import purge_expired_tokens
from app.services import email_service


async def _user(db_session, email="sweep@example.com") -> User:
    user = User(email=email, hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    return user


async def _row(db_session, user, *, expires_at, used_at=None) -> EmailToken:
    """Insert a token row directly, so its age can be dictated."""
    token = EmailToken(
        user_id=user.id,
        purpose=EmailTokenPurpose.VERIFY_EMAIL.value,
        token_hash=f"h{expires_at.timestamp()}{used_at is not None}",
        expires_at=expires_at,
        used_at=used_at,
    )
    db_session.add(token)
    await db_session.flush()
    return token


async def _count(db_session) -> int:
    return await db_session.scalar(select(func.count()).select_from(EmailToken))


async def test_purge_removes_rows_past_the_retention_window(db_session) -> None:
    now = datetime.now(UTC)
    user = await _user(db_session)
    await _row(
        db_session,
        user,
        expires_at=now - timedelta(days=EMAIL_TOKEN_RETENTION_DAYS + 1),
    )
    await _row(
        db_session,
        user,
        expires_at=now - timedelta(days=EMAIL_TOKEN_RETENTION_DAYS - 1),
    )
    await _row(db_session, user, expires_at=now + timedelta(hours=1))
    await db_session.commit()

    deleted = await purge_expired_tokens(db_session)

    assert deleted == 1, f"only the past-cutoff row should go, deleted {deleted}"
    assert await _count(db_session) == 2, "inside-grace and live rows must survive"


async def test_purge_removes_used_rows_once_expired(db_session) -> None:
    """A redeemed row is still only swept on age -- used_at is not a predicate."""
    now = datetime.now(UTC)
    user = await _user(db_session)
    await _row(
        db_session,
        user,
        expires_at=now - timedelta(days=EMAIL_TOKEN_RETENTION_DAYS + 1),
        used_at=now - timedelta(days=EMAIL_TOKEN_RETENTION_DAYS + 1),
    )
    await db_session.commit()

    deleted = await purge_expired_tokens(db_session)

    assert deleted == 1, f"expected the consumed, aged row to go, deleted {deleted}"
    assert await _count(db_session) == 0, "no rows should remain"


async def test_purge_never_deletes_a_live_token(db_session) -> None:
    """The safety property: a link in flight must survive the sweep."""
    user = await _user(db_session)
    raw = await email_service.issue_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL
    )
    await db_session.commit()

    deleted = await purge_expired_tokens(db_session)
    assert deleted == 0, f"a live token must not be swept, deleted {deleted}"

    consumed = await email_service.consume_token(
        db_session, raw, EmailTokenPurpose.VERIFY_EMAIL
    )
    assert consumed is not None, "the surviving token must still redeem"
    assert consumed.id == user.id


async def test_purge_batches_until_drained(db_session) -> None:
    """More rows than one batch: the loop must keep going, not stop at one."""
    now = datetime.now(UTC)
    user = await _user(db_session)
    batch_size = 5
    total = batch_size + 3
    for i in range(total):
        await _row(
            db_session,
            user,
            expires_at=now - timedelta(days=EMAIL_TOKEN_RETENTION_DAYS + 1, seconds=i),
        )
    await db_session.commit()

    deleted = await purge_expired_tokens(db_session, batch_size=batch_size)

    assert deleted == total, f"expected all {total} rows deleted, got {deleted}"
    assert await _count(db_session) == 0, "no rows should remain"


async def test_purge_dry_run_deletes_nothing(db_session) -> None:
    now = datetime.now(UTC)
    user = await _user(db_session)
    await _row(
        db_session,
        user,
        expires_at=now - timedelta(days=EMAIL_TOKEN_RETENTION_DAYS + 1),
    )
    await db_session.commit()

    deleted = await purge_expired_tokens(db_session, dry_run=True)

    assert deleted == 1, f"dry run should still report the row, got {deleted}"
    assert await _count(db_session) == 1, "dry run must leave the row in place"
