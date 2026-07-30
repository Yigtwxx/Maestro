"""The refresh token's transport: httpOnly cookie in, nothing in the body.

These tests guard CLAUDE.md §9 rule 14. The rotation and reuse-detection
*semantics* are covered by ``test_auth_refresh.py``; what is asserted here is
that the token only ever travels as a cookie, that the cookie carries the
attributes the threat model depends on, and that every failure path expires it.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.cookies import (
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    clearing_cookie_header,
)

_EMAIL = "cookie@example.com"
_PASSWORD = "supersecret"


async def _register_and_login(client, email: str = _EMAIL):  # noqa: ANN001, ANN201
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": _PASSWORD}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp


def _set_cookie_header(response) -> str:  # noqa: ANN001
    """The raw Set-Cookie line for our cookie.

    Read from the headers rather than ``response.cookies``: httpx's jar keeps
    the value and throws the attributes away, and the attributes are the whole
    point of this module.
    """
    headers = [
        h
        for h in response.headers.get_list("set-cookie")
        if h.startswith(f"{REFRESH_COOKIE_NAME}=")
    ]
    assert headers, f"no {REFRESH_COOKIE_NAME} cookie in {response.headers!r}"
    assert len(headers) == 1, f"cookie set more than once: {headers!r}"
    return headers[0]


async def test_login_sets_an_httponly_scoped_cookie(client):
    """The cookie attributes *are* the threat model, including CSRF.

    ``SameSite`` is the only CSRF control on /refresh and /logout: both are
    POST-only, so under either allowed value the browser withholds the cookie
    from a cross-site request and the endpoint sees an unauthenticated call.
    Nothing server-side re-checks this, which is exactly why the attribute is
    asserted here.
    """
    header = _set_cookie_header(await _register_and_login(client)).lower()

    assert "httponly" in header, "JavaScript must not be able to read the session"
    assert f"samesite={settings.refresh_cookie_samesite}" in header
    assert f"path={REFRESH_COOKIE_PATH}".lower() in header, (
        "the cookie must not ride along on every other API call"
    )
    expected_max_age = settings.refresh_token_expire_days * 24 * 60 * 60
    assert f"max-age={expected_max_age}" in header, (
        "the cookie must not outlive (or die before) the token it carries"
    )
    assert ("secure" in header) is settings.refresh_cookie_is_secure


@pytest.mark.parametrize("path", ["/api/v1/auth/login", "/api/v1/auth/refresh"])
async def test_no_endpoint_returns_a_refresh_token_in_its_body(
    client, send_refresh_cookie, path
):
    login = await _register_and_login(client)
    if path == "/api/v1/auth/refresh":
        send_refresh_cookie(login.cookies[REFRESH_COOKIE_NAME])
        resp = await client.post(path)
    else:
        resp = login

    assert resp.status_code == 200, resp.text
    assert "refresh_token" not in resp.json()
    # Also as raw text, so a token nested under some other key still fails.
    assert "refresh_token" not in resp.text


async def test_refresh_works_from_the_cookie_alone(client, send_refresh_cookie):
    login = await _register_and_login(client)
    original = login.cookies[REFRESH_COOKIE_NAME]

    send_refresh_cookie(original)
    resp = await client.post("/api/v1/auth/refresh")  # no body at all

    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    assert resp.cookies[REFRESH_COOKIE_NAME] != original, "rotation must re-cookie"


async def test_a_refresh_token_in_the_body_is_not_accepted(client):
    """The regression guard for "cookie-only, no body fallback".

    A body-accepting path would be exactly the code the cookie exists to
    delete: an endpoint handing out a session to whatever JavaScript can reach
    it.
    """
    login = await _register_and_login(client)
    token = login.cookies[REFRESH_COOKIE_NAME]
    client.cookies.clear()

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})

    assert resp.status_code == 401, resp.text


async def test_refresh_without_a_cookie_is_rejected_and_clears(client):
    client.cookies.clear()
    resp = await client.post("/api/v1/auth/refresh")

    assert resp.status_code == 401
    assert _set_cookie_header(resp)


async def test_a_failed_refresh_expires_the_cookie(client, send_refresh_cookie):
    """A burned family must not leave a dead credential 401-ing for a week."""
    await _register_and_login(client)
    send_refresh_cookie("not-a-jwt")

    resp = await client.post("/api/v1/auth/refresh")

    assert resp.status_code == 401
    assert "max-age=0" in _set_cookie_header(resp).lower()


async def test_logout_clears_the_cookie_and_revokes_the_family(
    client, send_refresh_cookie
):
    login = await _register_and_login(client)
    token = login.cookies[REFRESH_COOKIE_NAME]

    send_refresh_cookie(token)
    out = await client.post("/api/v1/auth/logout")
    assert out.status_code == 204
    assert "max-age=0" in _set_cookie_header(out).lower()

    send_refresh_cookie(token)
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_without_a_cookie_still_clears(client):
    """Answered identically with or without a session, so it is not an oracle."""
    client.cookies.clear()
    out = await client.post("/api/v1/auth/logout")

    assert out.status_code == 204
    assert "max-age=0" in _set_cookie_header(out).lower()


def test_clearing_header_mirrors_the_set_scope():
    """A delete_cookie whose scope differs is silently ignored by the browser."""
    header = clearing_cookie_header()["set-cookie"].lower()

    assert f"path={REFRESH_COOKIE_PATH}".lower() in header
    assert f"samesite={settings.refresh_cookie_samesite}" in header
    assert "httponly" in header
    assert ("secure" in header) is settings.refresh_cookie_is_secure
