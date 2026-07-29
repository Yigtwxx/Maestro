"""The typeable code that ships beside the verification link.

Six digits is a small keyspace, so the properties that keep it safe -- the
attempt cap, the short expiry, and the per-user scope -- are what these tests
are really about.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.constants import EMAIL_CODE_MAX_ATTEMPTS
from app.models import EmailToken

_CODE = "/api/v1/auth/verify-email/code"


def _extract_code(message) -> str:
    match = re.search(r"Or enter this code: (\d{6})", message.text)
    assert match is not None, f"email should carry a 6-digit code, got: {message.text}"
    return match.group(1)


def _extract_token(message) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", message.text)
    assert match is not None, "email should contain an action link"
    return match.group(1)


async def _register_and_login(client, email="code@example.com", password="password123"):
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _verified(client, headers) -> bool:
    me = await client.get("/api/v1/users/me", headers=headers)
    return me.json()["email_verified"]


async def test_register_email_carries_both_a_link_and_a_code(
    client, sent_emails
) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "both@example.com", "password": "password123"},
    )
    body = sent_emails[0].text
    assert "/verify-email?token=" in body, "the one-click link must survive"
    assert re.search(r"Or enter this code: \d{6}", body), "and a code must be added"


async def test_verify_email_correct_code_marks_user_verified(
    client, sent_emails
) -> None:
    headers = await _register_and_login(client)
    code = _extract_code(sent_emails[0])

    resp = await client.post(_CODE, headers=headers, json={"code": code})

    assert resp.status_code == 200, resp.text
    assert await _verified(client, headers) is True


async def test_verify_email_wrong_code_returns_400(client, sent_emails) -> None:
    headers = await _register_and_login(client)
    real = _extract_code(sent_emails[0])
    wrong = f"{(int(real) + 1) % 10**6:06d}"

    resp = await client.post(_CODE, headers=headers, json={"code": wrong})

    assert resp.status_code == 400, resp.text
    assert await _verified(client, headers) is False


async def test_verify_email_code_is_single_use(client, sent_emails) -> None:
    headers = await _register_and_login(client)
    code = _extract_code(sent_emails[0])
    assert (
        await client.post(_CODE, headers=headers, json={"code": code})
    ).status_code == 200
    # A second redemption is a no-op rather than an error: the account is
    # already verified, and saying otherwise would be a confusing lie.
    assert (
        await client.post(_CODE, headers=headers, json={"code": code})
    ).status_code == 200


async def test_verify_email_code_burns_after_max_attempts(
    client, sent_emails, db_session
) -> None:
    """The load-bearing control: guessing must run out, not run forever."""
    headers = await _register_and_login(client)
    real = _extract_code(sent_emails[0])
    wrong = f"{(int(real) + 1) % 10**6:06d}"

    for i in range(EMAIL_CODE_MAX_ATTEMPTS):
        resp = await client.post(_CODE, headers=headers, json={"code": wrong})
        assert resp.status_code == 400, f"attempt {i + 1} should fail: {resp.text}"

    resp = await client.post(_CODE, headers=headers, json={"code": real})
    assert resp.status_code == 400, "the correct code must die with the attempt budget"
    assert await _verified(client, headers) is False


async def test_verify_email_expired_code_fails_but_link_still_works(
    client, sent_emails, db_session
) -> None:
    """The code and the link expire on independent clocks."""
    headers = await _register_and_login(client)
    code = _extract_code(sent_emails[0])
    token = _extract_token(sent_emails[0])

    row = (await db_session.execute(select(EmailToken))).scalar_one()
    row.code_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    resp = await client.post(_CODE, headers=headers, json={"code": code})
    assert resp.status_code == 400, "an expired code must be refused"

    resp = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp.status_code == 200, "the 24h link must outlive the 15m code"


async def test_verify_email_code_cannot_verify_another_account(
    client, sent_emails
) -> None:
    """The per-user scope: six digits are not unique, so scope is the guard."""
    victim_headers = await _register_and_login(client, email="victim@example.com")
    victim_code = _extract_code(sent_emails[0])

    attacker_headers = await _register_and_login(client, email="attacker@example.com")

    resp = await client.post(
        _CODE, headers=attacker_headers, json={"code": victim_code}
    )

    assert resp.status_code == 400, "a code must not cross accounts"
    assert await _verified(client, victim_headers) is False
    assert await _verified(client, attacker_headers) is False


async def test_resend_verification_rotates_the_code(client, sent_emails) -> None:
    headers = await _register_and_login(client)
    old_code = _extract_code(sent_emails[0])

    await client.post("/api/v1/auth/resend-verification", headers=headers)
    new_code = _extract_code(sent_emails[1])

    assert (
        await client.post(_CODE, headers=headers, json={"code": old_code})
    ).status_code == 400, "the old code must die on resend"
    assert (
        await client.post(_CODE, headers=headers, json={"code": new_code})
    ).status_code == 200


async def test_verify_email_code_requires_auth(client) -> None:
    resp = await client.post(_CODE, json={"code": "123456"})
    assert resp.status_code in (401, 403)


async def test_verify_email_code_rejects_non_numeric_shapes(
    client, sent_emails
) -> None:
    headers = await _register_and_login(client)
    for bad in ("12345", "1234567", "abcdef", ""):
        resp = await client.post(_CODE, headers=headers, json={"code": bad})
        assert resp.status_code == 422, f"{bad!r} should not reach the service"


async def test_password_reset_email_carries_no_code(client, sent_emails) -> None:
    """Reset grants takeover, so it deliberately stays link-only."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "reset@example.com", "password": "password123"},
    )
    sent_emails.clear()
    await client.post(
        "/api/v1/auth/forgot-password", json={"email": "reset@example.com"}
    )

    assert len(sent_emails) == 1
    assert "enter this code" not in sent_emails[0].text.lower()


async def test_stored_row_never_holds_the_plaintext_code(
    client, sent_emails, db_session
) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "hash@example.com", "password": "password123"},
    )
    code = _extract_code(sent_emails[0])

    row = (await db_session.execute(select(EmailToken))).scalar_one()
    assert row.code_hash != code, "the raw code must never be stored"
    assert len(row.code_hash) == 64, "expected a SHA-256 hex digest"
