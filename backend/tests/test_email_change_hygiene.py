"""Email identity hygiene on POST /users/me/email and its confirmation."""

from __future__ import annotations

import re

from sqlalchemy import select

from app.core.constants import UserRole
from app.models.user import User

_REGISTER = "/api/v1/auth/register"
_LOGIN = "/api/v1/auth/login"
_CHANGE = "/api/v1/users/me/email"
_CONFIRM = "/api/v1/auth/change-email"
_PASSWORD = "password123"


def _token(message) -> str:  # noqa: ANN001
    """Same helper as ``tests/test_email_change.py``; the link format is shared."""
    match = re.search(r"token=([A-Za-z0-9_\-]+)", message.text)
    assert match is not None, f"expected an action link, got: {message.text}"
    return match.group(1)


async def _signed_in(client, email: str) -> dict[str, str]:  # noqa: ANN001
    await client.post(_REGISTER, json={"email": email, "password": _PASSWORD})
    resp = await client.post(_LOGIN, json={"email": email, "password": _PASSWORD})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_a_disposable_target_is_refused(client) -> None:  # noqa: ANN001
    headers = await _signed_in(client, "owner@example.com")

    resp = await client.post(
        _CHANGE,
        json={"new_email": "throwaway@mailinator.com", "current_password": _PASSWORD},
        headers=headers,
    )

    assert resp.status_code == 400, resp.text


async def test_an_ordinary_target_is_accepted(client, sent_emails) -> None:  # noqa: ANN001
    headers = await _signed_in(client, "owner@example.com")
    sent_emails.clear()

    resp = await client.post(
        _CHANGE,
        json={"new_email": "owner@gmail.com", "current_password": _PASSWORD},
        headers=headers,
    )

    assert resp.status_code == 202, resp.text
    assert sent_emails


async def test_confirming_a_change_stores_the_new_canonical(  # noqa: ANN001
    client, db_session, sent_emails
) -> None:
    headers = await _signed_in(client, "owner@example.com")
    sent_emails.clear()
    await client.post(
        _CHANGE,
        json={"new_email": "You+tag@Gmail.com", "current_password": _PASSWORD},
        headers=headers,
    )
    token = _token(next(m for m in sent_emails if m.to == "you+tag@gmail.com"))

    resp = await client.post(_CONFIRM, json={"token": token})

    assert resp.status_code == 200, resp.text
    stored = await db_session.scalar(
        select(User.canonical_email).where(User.email == "you+tag@gmail.com")
    )
    assert stored == "you@gmail.com"


async def test_an_admin_role_bypasses_hygiene_even_off_the_grant_list(  # noqa: ANN001
    client, db_session, sent_emails
) -> None:
    """The role-based exemption (Fix 3) is the authenticated counterpart to
    `GRANT_ADMIN_EMAILS`: it fires on `user.role`, not on the caller's address
    matching a configured string, so an admin whose own address was never
    listed still moves to a disposable domain."""
    headers = await _signed_in(client, "owner@example.com")
    user = await db_session.scalar(
        select(User).where(User.email == "owner@example.com")
    )
    user.role = UserRole.ADMIN.value
    await db_session.commit()

    resp = await client.post(
        _CHANGE,
        json={"new_email": "throwaway@mailinator.com", "current_password": _PASSWORD},
        headers=headers,
    )

    assert resp.status_code == 202, resp.text


async def test_confirming_onto_another_accounts_mailbox_conflicts(  # noqa: ANN001
    client, sent_emails
) -> None:
    """The collision surfaces at confirm time, by which point the caller has
    proven they can read that inbox -- so a 409 leaks nothing new."""
    await client.post(
        _REGISTER, json={"email": "taken@gmail.com", "password": _PASSWORD}
    )
    headers = await _signed_in(client, "owner@example.com")
    sent_emails.clear()
    await client.post(
        _CHANGE,
        json={"new_email": "t.a.k.e.n+x@gmail.com", "current_password": _PASSWORD},
        headers=headers,
    )
    token = _token(next(m for m in sent_emails if m.to == "t.a.k.e.n+x@gmail.com"))

    resp = await client.post(_CONFIRM, json={"token": token})

    assert resp.status_code == 409, resp.text
