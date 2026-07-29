"""Token lifecycle: issue, consume, expiry, single-use, rotation, safe send."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.constants import EmailTokenPurpose
from app.models import EmailToken, User
from app.services import email_service


async def _user(db_session, email="svc@example.com") -> User:
    user = User(email=email, hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    return user


async def test_issue_token_returns_raw_and_stores_only_hash(db_session) -> None:
    user = await _user(db_session)
    raw, _ = await email_service.issue_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL
    )
    await db_session.commit()

    row = (await db_session.execute(select(EmailToken))).scalar_one()
    assert raw not in (row.token_hash,), "raw token must never be stored"
    assert len(row.token_hash) == 64, "expected a SHA-256 hex digest"


async def test_consume_token_valid_returns_user_and_marks_used(db_session) -> None:
    user = await _user(db_session)
    raw, _ = await email_service.issue_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL
    )
    await db_session.commit()

    consumed = await email_service.consume_token(
        db_session, raw, EmailTokenPurpose.VERIFY_EMAIL
    )
    await db_session.commit()
    assert consumed is not None and consumed.id == user.id

    replay = await email_service.consume_token(
        db_session, raw, EmailTokenPurpose.VERIFY_EMAIL
    )
    assert replay is None, "a token must be single-use"


async def test_consume_token_concurrent_claims_only_one_succeeds(
    db_session, other_db_session
) -> None:
    """Two callers redeeming the same link: exactly one wins.

    The read-then-write version passed both -- the claim only existed as
    pending ORM state until commit, so the second SELECT still saw
    ``used_at IS NULL``. Regression guard for that race.
    """
    user = await _user(db_session)
    raw, _ = await email_service.issue_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL
    )
    await db_session.commit()

    first = await email_service.consume_token(
        db_session, raw, EmailTokenPurpose.VERIFY_EMAIL
    )
    second = await email_service.consume_token(
        other_db_session, raw, EmailTokenPurpose.VERIFY_EMAIL
    )

    winners = [c for c in (first, second) if c is not None]
    assert len(winners) == 1, (
        f"exactly one claim must win, got first={first!r} second={second!r}"
    )


async def test_consume_token_expired_returns_none(db_session) -> None:
    user = await _user(db_session)
    raw, _ = await email_service.issue_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL
    )
    row = (await db_session.execute(select(EmailToken))).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    assert (
        await email_service.consume_token(
            db_session, raw, EmailTokenPurpose.VERIFY_EMAIL
        )
        is None
    )


async def test_consume_token_wrong_purpose_returns_none(db_session) -> None:
    user = await _user(db_session)
    raw, _ = await email_service.issue_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL
    )
    await db_session.commit()
    assert (
        await email_service.consume_token(
            db_session, raw, EmailTokenPurpose.RESET_PASSWORD
        )
        is None
    )


async def test_issue_token_rotation_invalidates_previous_token(db_session) -> None:
    user = await _user(db_session)
    old_raw, _ = await email_service.issue_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL
    )
    await db_session.commit()
    new_raw, _ = await email_service.issue_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL
    )
    await db_session.commit()

    assert (
        await email_service.consume_token(
            db_session, old_raw, EmailTokenPurpose.VERIFY_EMAIL
        )
        is None
    ), "issuing a new token must invalidate the old one"
    assert (
        await email_service.consume_token(
            db_session, new_raw, EmailTokenPurpose.VERIFY_EMAIL
        )
        is not None
    )


async def test_send_verification_provider_failure_does_not_raise(monkeypatch) -> None:
    class ExplodingProvider:
        name = "exploding"

        async def send(self, message) -> None:  # noqa: ANN001
            raise RuntimeError("provider down")

    monkeypatch.setattr(
        email_service, "get_email_provider", lambda: ExplodingProvider()
    )
    await email_service.send_verification("user@example.com", "sometoken")


async def test_send_verification_builds_link_from_site_url(sent_emails) -> None:
    await email_service.send_verification("user@example.com", "RAWTOKEN")
    assert len(sent_emails) == 1
    assert "/verify-email?token=RAWTOKEN" in sent_emails[0].text
