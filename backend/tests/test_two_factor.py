"""Integration tests for TOTP two-factor auth (SQLite-backed)."""

from __future__ import annotations

import pyotp

_PASSWORD = "supersecret"


async def _register_and_login(client, email: str) -> tuple[dict[str, str], str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "T"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, token


async def _enroll(client, headers) -> tuple[str, list[str]]:  # noqa: ANN001
    """Setup + enable 2FA; return (secret, recovery_codes)."""
    setup = await client.post("/api/v1/users/me/2fa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    body = setup.json()
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert body["qr_svg"].lstrip().startswith("<?xml")
    secret = body["secret"]

    code = pyotp.TOTP(secret).now()
    enable = await client.post(
        "/api/v1/users/me/2fa/enable",
        headers=headers,
        json={"password": _PASSWORD, "code": code},
    )
    assert enable.status_code == 200, enable.text
    codes = enable.json()["recovery_codes"]
    assert len(codes) == 10, f"expected 10 recovery codes, got {len(codes)}"
    return secret, codes


async def test_enable_flags_two_factor_on_profile(client):
    headers, _ = await _register_and_login(client, "2fa1@user.com")
    await _enroll(client, headers)
    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.json()["two_factor_enabled"] is True


async def test_enable_requires_correct_code(client):
    headers, _ = await _register_and_login(client, "2fa2@user.com")
    await client.post("/api/v1/users/me/2fa/setup", headers=headers)
    resp = await client.post(
        "/api/v1/users/me/2fa/enable",
        headers=headers,
        json={"password": _PASSWORD, "code": "000000"},
    )
    assert resp.status_code == 400, "a wrong TOTP code must not enable 2FA"


async def test_login_requires_second_factor_when_enabled(client):
    headers, _ = await _register_and_login(client, "2fa3@user.com")
    secret, _ = await _enroll(client, headers)

    # Password alone now returns an MFA challenge, not tokens.
    login = await client.post(
        "/api/v1/auth/login", json={"email": "2fa3@user.com", "password": _PASSWORD}
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body.get("mfa_required") is True
    assert "access_token" not in body
    mfa_token = body["mfa_token"]

    # The interim token cannot be used as an access token.
    denied = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {mfa_token}"}
    )
    assert denied.status_code == 401, "the interim MFA token must not access the API"

    # Completing with a valid TOTP issues real tokens.
    verify = await client.post(
        "/api/v1/auth/login/totp",
        json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()},
    )
    assert verify.status_code == 200, verify.text
    assert "access_token" in verify.json()


async def test_login_totp_rejects_wrong_code(client):
    headers, _ = await _register_and_login(client, "2fa4@user.com")
    await _enroll(client, headers)
    login = await client.post(
        "/api/v1/auth/login", json={"email": "2fa4@user.com", "password": _PASSWORD}
    )
    mfa_token = login.json()["mfa_token"]
    resp = await client.post(
        "/api/v1/auth/login/totp",
        json={"mfa_token": mfa_token, "code": "000000"},
    )
    assert resp.status_code == 400


async def test_recovery_code_logs_in_once(client):
    headers, _ = await _register_and_login(client, "2fa5@user.com")
    _, codes = await _enroll(client, headers)
    recovery = codes[0]

    login = await client.post(
        "/api/v1/auth/login", json={"email": "2fa5@user.com", "password": _PASSWORD}
    )
    mfa_token = login.json()["mfa_token"]
    first = await client.post(
        "/api/v1/auth/login/totp", json={"mfa_token": mfa_token, "code": recovery}
    )
    assert first.status_code == 200, "a recovery code should complete login"

    # The same code cannot be reused.
    login2 = await client.post(
        "/api/v1/auth/login", json={"email": "2fa5@user.com", "password": _PASSWORD}
    )
    mfa_token2 = login2.json()["mfa_token"]
    second = await client.post(
        "/api/v1/auth/login/totp",
        json={"mfa_token": mfa_token2, "code": recovery},
    )
    assert second.status_code == 400, "recovery codes are single-use"


async def test_disable_turns_two_factor_off(client):
    headers, _ = await _register_and_login(client, "2fa6@user.com")
    await _enroll(client, headers)

    resp = await client.post(
        "/api/v1/users/me/2fa/disable",
        headers=headers,
        json={"password": _PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["two_factor_enabled"] is False

    # Login no longer requires a second factor.
    login = await client.post(
        "/api/v1/auth/login", json={"email": "2fa6@user.com", "password": _PASSWORD}
    )
    assert "access_token" in login.json()


async def test_disable_requires_password(client):
    headers, _ = await _register_and_login(client, "2fa7@user.com")
    await _enroll(client, headers)
    resp = await client.post(
        "/api/v1/users/me/2fa/disable",
        headers=headers,
        json={"password": "wrongpass"},
    )
    assert resp.status_code == 400


async def test_setup_blocked_while_already_enabled(client):
    headers, _ = await _register_and_login(client, "2fa8@user.com")
    await _enroll(client, headers)
    resp = await client.post("/api/v1/users/me/2fa/setup", headers=headers)
    assert resp.status_code == 400, "re-keying requires disabling first"
