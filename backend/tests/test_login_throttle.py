"""Per-account sign-in throttling: the axis the per-IP limiter cannot cover."""

from __future__ import annotations

import pyotp
import pytest

from app.core.config import settings
from app.core.constants import LOGIN_FAILURE_BUDGET, MFA_FAILURE_BUDGET
from app.utils import login_throttle
from app.utils.rate_limiter import limiter

_PASSWORD = "supersecret"
_EMAIL = "victim@user.com"


async def _register(client, email: str = _EMAIL) -> None:  # noqa: ANN001
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "V"},
    )
    assert resp.status_code == 202, resp.text


async def _login(client, password: str, email: str = _EMAIL, ip: str | None = None):  # noqa: ANN001, ANN201
    headers = {"X-Forwarded-For": ip} if ip else {}
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )


@pytest.fixture
def distributed(rate_limited, monkeypatch):  # noqa: ANN001, ANN201
    """Rate limiting on, with `X-Forwarded-For` believed.

    Lets a test hand every attempt a different source address, which is the
    shape of the attack: the per-IP bucket never fills, so anything that stops
    the run has to be counting the account instead.
    """
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    return rate_limited


async def test_distributed_guessing_against_one_account_is_bounded(client, distributed):  # noqa: ANN001
    """Each guess from a fresh address; the account's own budget still runs out."""
    await _register(client)
    distributed.reset()  # registration must not spend the budget under test

    budget = LOGIN_FAILURE_BUDGET.max_requests
    for attempt in range(budget):
        resp = await _login(client, "wrongpass", ip=f"203.0.113.{attempt}")
        assert resp.status_code == 401, f"attempt {attempt}: {resp.text}"

    blocked = await _login(client, "wrongpass", ip="203.0.113.250")
    assert blocked.status_code == 429, "the account budget must bound the run"
    assert int(blocked.headers["Retry-After"]) > 0


async def test_block_refuses_the_correct_password_too(client, distributed):  # noqa: ANN001
    """The block sits in front of verification -- that is what makes it one."""
    await _register(client)
    distributed.reset()

    for attempt in range(LOGIN_FAILURE_BUDGET.max_requests):
        await _login(client, "wrongpass", ip=f"198.51.100.{attempt}")

    resp = await _login(client, _PASSWORD, ip="198.51.100.250")
    assert resp.status_code == 429


async def test_an_unknown_address_is_throttled_identically(client, distributed):  # noqa: ANN001
    """Throttling only real accounts would make the 429 an existence oracle."""
    distributed.reset()
    unknown = "no-such@user.com"

    for attempt in range(LOGIN_FAILURE_BUDGET.max_requests):
        resp = await _login(client, "wrongpass", email=unknown, ip=f"192.0.2.{attempt}")
        assert resp.status_code == 401

    blocked = await _login(client, "wrongpass", email=unknown, ip="192.0.2.250")
    assert blocked.status_code == 429


async def test_the_budget_is_scoped_to_one_account(client, distributed):  # noqa: ANN001
    """A blocked account must not take every other account down with it."""
    await _register(client)
    await _register(client, "bystander@user.com")
    distributed.reset()

    for attempt in range(LOGIN_FAILURE_BUDGET.max_requests + 1):
        await _login(client, "wrongpass", ip=f"203.0.113.{attempt}")

    resp = await _login(client, _PASSWORD, email="bystander@user.com", ip="203.0.113.9")
    assert resp.status_code == 200, resp.text


async def test_a_success_clears_the_failures(client, distributed):  # noqa: ANN001
    """Someone who mistypes and then gets it right starts over, not one away."""
    await _register(client)
    distributed.reset()

    for attempt in range(LOGIN_FAILURE_BUDGET.max_requests - 1):
        await _login(client, "wrongpass", ip=f"203.0.113.{attempt}")

    ok = await _login(client, _PASSWORD, ip="203.0.113.50")
    assert ok.status_code == 200, ok.text

    # Back at a full budget: one more failure must not reach the ceiling.
    again = await _login(client, "wrongpass", ip="203.0.113.51")
    assert again.status_code == 401, "the counter should have been cleared"


async def test_mfa_codes_have_their_own_account_budget(client, distributed):  # noqa: ANN001
    """Six digits behind a known password need a ceiling of their own."""
    await _register(client, "mfa@user.com")
    first = await _login(client, _PASSWORD, email="mfa@user.com")
    headers = {"Authorization": f"Bearer {first.json()['access_token']}"}

    setup = await client.post("/api/v1/users/me/2fa/setup", headers=headers)
    secret = setup.json()["secret"]
    enable = await client.post(
        "/api/v1/users/me/2fa/enable",
        headers=headers,
        json={"password": _PASSWORD, "code": pyotp.TOTP(secret).now()},
    )
    assert enable.status_code == 200, enable.text

    challenge = await _login(client, _PASSWORD, email="mfa@user.com")
    mfa_token = challenge.json()["mfa_token"]
    distributed.reset()

    for attempt in range(MFA_FAILURE_BUDGET.max_requests):
        resp = await client.post(
            "/api/v1/auth/login/totp",
            json={"mfa_token": mfa_token, "code": "000000"},
            headers={"X-Forwarded-For": f"203.0.113.{attempt}"},
        )
        assert resp.status_code == 400, f"attempt {attempt}: {resp.text}"

    blocked = await client.post(
        "/api/v1/auth/login/totp",
        json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()},
        headers={"X-Forwarded-For": "203.0.113.250"},
    )
    assert blocked.status_code == 429


async def test_a_full_bucket_stops_recording_so_the_block_cannot_be_extended(
    rate_limited,
):  # noqa: ANN001
    """The lockout-DoS bound: hammering past the ceiling adds no time.

    A bucket at its limit refuses further hits, so the newest recorded failure
    stays put and the block still lifts when the oldest one ages out.
    """
    guard = login_throttle.password
    subject = "extend@user.com"
    for _ in range(guard.budget.max_requests):
        await guard.record_failure(subject)

    key = guard._key(subject)
    before = await limiter.count(key, guard.budget)
    for _ in range(20):
        await guard.record_failure(subject)
    after = await limiter.count(key, guard.budget)

    assert after.count == before.count == guard.budget.max_requests
    assert after.retry_after <= before.retry_after


async def test_the_key_does_not_carry_the_address(rate_limited):  # noqa: ANN001
    """Bucket keys travel through monitoring output; an address should not."""
    key = login_throttle.password._key("someone@example.com")
    assert "someone@example.com" not in key
    assert "example.com" not in key
    assert key.startswith("rl:")


async def test_disabled_rate_limiting_disables_the_throttle(client):  # noqa: ANN001
    """The development escape hatch covers this throttle like every other."""
    await _register(client)
    for _ in range(LOGIN_FAILURE_BUDGET.max_requests + 2):
        resp = await _login(client, "wrongpass")
        assert resp.status_code == 401
    ok = await _login(client, _PASSWORD)
    assert ok.status_code == 200, ok.text
