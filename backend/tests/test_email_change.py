"""Changing an account's address, which must re-prove inbox ownership.

The bug this flow replaces: PATCH /users/me rewrote ``email`` and left
``email_verified`` true, so a verified account could be repointed at an
address nobody had proven they owned -- and password-reset mail followed it.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from app.core.cookies import REFRESH_COOKIE_NAME
from app.models import User

_REQUEST = "/api/v1/users/me/email"
_CONFIRM = "/api/v1/auth/change-email"
_CONFIRM_CODE = "/api/v1/auth/change-email/code"
_OLD = "owner@example.com"
_NEW = "moved@example.com"
_PASSWORD = "password123"


def _token(message) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", message.text)
    assert match is not None, f"expected an action link, got: {message.text}"
    return match.group(1)


def _code(message) -> str:
    match = re.search(r"Or enter this code: (\d{6})", message.text)
    assert match is not None, f"expected a 6-digit code, got: {message.text}"
    return match.group(1)


async def _register_and_login(client, email=_OLD, password=_PASSWORD):
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _current_email(client, headers) -> str:
    return (await client.get("/api/v1/users/me", headers=headers)).json()["email"]


async def test_request_requires_the_current_password(client, sent_emails) -> None:
    """A stolen access token alone must not redirect account recovery."""
    headers = await _register_and_login(client)
    sent_emails.clear()

    resp = await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": _NEW, "current_password": "wrong-password"},
    )

    assert resp.status_code == 400, resp.text
    assert sent_emails == [], "a failed attempt must not email anyone"
    assert await _current_email(client, headers) == _OLD


async def test_request_emails_the_new_address_and_warns_the_old_one(
    client, sent_emails
) -> None:
    headers = await _register_and_login(client)
    sent_emails.clear()

    resp = await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": _NEW, "current_password": _PASSWORD},
    )

    assert resp.status_code == 202, resp.text
    assert len(sent_emails) == 2, "the new address and the old one both hear about it"
    to_new = next(m for m in sent_emails if m.to == _NEW)
    to_old = next(m for m in sent_emails if m.to == _OLD)
    assert "token=" in to_new.text, "the new address gets the actionable link"
    assert "token=" not in to_old.text, "the old address must not be actionable"
    assert not re.search(r"\b\d{6}\b", to_old.text), "nor carry a code"
    assert _NEW in to_old.text, "but must name the address being moved to"


async def test_address_does_not_move_until_confirmed(client, sent_emails) -> None:
    """The property the old code broke."""
    headers = await _register_and_login(client)
    sent_emails.clear()
    await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": _NEW, "current_password": _PASSWORD},
    )

    assert await _current_email(client, headers) == _OLD


async def test_confirming_the_link_moves_the_address(client, sent_emails) -> None:
    headers = await _register_and_login(client)
    sent_emails.clear()
    await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": _NEW, "current_password": _PASSWORD},
    )
    token = _token(next(m for m in sent_emails if m.to == _NEW))

    resp = await client.post(_CONFIRM, json={"token": token})
    assert resp.status_code == 200, resp.text

    fresh = await client.post(
        "/api/v1/auth/login", json={"email": _NEW, "password": _PASSWORD}
    )
    assert fresh.status_code == 200, "the new address must be the sign-in address"
    new_headers = {"Authorization": f"Bearer {fresh.json()['access_token']}"}
    body = (await client.get("/api/v1/users/me", headers=new_headers)).json()
    assert body["email"] == _NEW
    assert body["email_verified"] is True, "clicking the link is the proof"


async def test_confirming_the_code_moves_the_address(client, sent_emails) -> None:
    headers = await _register_and_login(client)
    sent_emails.clear()
    await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": _NEW, "current_password": _PASSWORD},
    )
    code = _code(next(m for m in sent_emails if m.to == _NEW))

    resp = await client.post(_CONFIRM_CODE, headers=headers, json={"code": code})

    assert resp.status_code == 200, resp.text
    fresh = await client.post(
        "/api/v1/auth/login", json={"email": _NEW, "password": _PASSWORD}
    )
    assert fresh.status_code == 200


async def test_confirmation_is_single_use(client, sent_emails) -> None:
    headers = await _register_and_login(client)
    sent_emails.clear()
    await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": _NEW, "current_password": _PASSWORD},
    )
    token = _token(next(m for m in sent_emails if m.to == _NEW))

    assert (await client.post(_CONFIRM, json={"token": token})).status_code == 200
    assert (await client.post(_CONFIRM, json={"token": token})).status_code == 400


async def test_a_stale_token_cannot_apply_the_older_address(
    client, sent_emails
) -> None:
    """A token is bound to the address it was issued for, and rotates."""
    headers = await _register_and_login(client)
    sent_emails.clear()
    await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": "first@example.com", "current_password": _PASSWORD},
    )
    stale = _token(next(m for m in sent_emails if m.to == "first@example.com"))

    sent_emails.clear()
    await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": "second@example.com", "current_password": _PASSWORD},
    )

    assert (await client.post(_CONFIRM, json={"token": stale})).status_code == 400
    assert await _current_email(client, headers) == _OLD


async def test_confirming_into_a_taken_address_conflicts(client, sent_emails) -> None:
    """The one place a collision surfaces -- after inbox ownership is proven."""
    await _register_and_login(client, email="squatter@example.com")
    headers = await _register_and_login(client)
    sent_emails.clear()
    await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": "squatter@example.com", "current_password": _PASSWORD},
    )
    token = _token(next(m for m in sent_emails if m.to == "squatter@example.com"))

    resp = await client.post(_CONFIRM, json={"token": token})

    assert resp.status_code == 409, resp.text
    assert await _current_email(client, headers) == _OLD


async def test_request_to_the_same_address_is_a_quiet_no_op(
    client, sent_emails
) -> None:
    headers = await _register_and_login(client)
    sent_emails.clear()

    resp = await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": _OLD.upper(), "current_password": _PASSWORD},
    )

    assert resp.status_code == 202, "answered identically, so it reveals nothing"
    assert sent_emails == [], "but nothing is actually sent"


async def test_request_does_not_reveal_whether_the_target_exists(
    client, sent_emails
) -> None:
    """Otherwise this endpoint becomes an account-existence oracle."""
    await _register_and_login(client, email="taken@example.com")
    headers = await _register_and_login(client)

    taken = await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": "taken@example.com", "current_password": _PASSWORD},
    )
    free = await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": "free@example.com", "current_password": _PASSWORD},
    )

    assert taken.status_code == free.status_code
    assert taken.json() == free.json(), "responses must be indistinguishable"


async def test_confirming_revokes_other_sessions(
    client, sent_emails, send_refresh_cookie
) -> None:
    """A changed sign-in address should not leave stale refresh tokens alive."""
    await _register_and_login(client)
    stale = await client.post(
        "/api/v1/auth/login", json={"email": _OLD, "password": _PASSWORD}
    )
    stale_refresh = stale.cookies[REFRESH_COOKIE_NAME]

    headers = await _register_and_login(client)
    sent_emails.clear()
    await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": _NEW, "current_password": _PASSWORD},
    )
    token = _token(next(m for m in sent_emails if m.to == _NEW))
    await client.post(_CONFIRM, json={"token": token})

    send_refresh_cookie(stale_refresh)
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401, "old sessions must not survive the change"


async def test_no_second_account_is_created(client, sent_emails, db_session) -> None:
    headers = await _register_and_login(client)
    sent_emails.clear()
    await client.post(
        _REQUEST,
        headers=headers,
        json={"new_email": _NEW, "current_password": _PASSWORD},
    )
    token = _token(next(m for m in sent_emails if m.to == _NEW))
    await client.post(_CONFIRM, json={"token": token})

    users = (await db_session.execute(select(User))).scalars().all()
    assert len(users) == 1, "a change moves the account, it does not clone it"


async def test_request_requires_auth(client) -> None:
    resp = await client.post(
        _REQUEST, json={"new_email": _NEW, "current_password": _PASSWORD}
    )
    assert resp.status_code in (401, 403)
