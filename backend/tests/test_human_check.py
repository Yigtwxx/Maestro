"""Anti-automation layers on the two unauthenticated mail endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.core.constants import SIGNUP_CHALLENGE_TTL_MINUTES
from app.core.security import create_token, decode_token
from app.utils import human_check

_CHALLENGE = "/api/v1/auth/challenge"
_REGISTER = "/api/v1/auth/register"
_LOGIN = "/api/v1/auth/login"
_PASSWORD = "supersecret"

# Captured at import time, which runs before any fixture: this is the real
# function, not conftest's bypass. `monkeypatch.undo()` would be wrong here --
# one monkeypatch instance is shared by every fixture in a test, so undoing
# would revert unrelated patches too.
_REAL_PASSES = human_check.passes


@pytest.fixture(autouse=True)
def _human_check_on(monkeypatch):  # noqa: ANN001, ANN202
    """Restore the real check, which conftest bypasses for the rest of the suite."""
    monkeypatch.setattr(human_check, "passes", _REAL_PASSES)


async def test_challenge_advertises_the_null_provider_by_default(client) -> None:  # noqa: ANN001
    """The frontend learns the provider at runtime, never at build time.

    A site key baked in as a NEXT_PUBLIC_* constant would tie the built image to
    one deployment, which is why SITE_URL is server-only too.
    """
    resp = await client.get(_CHALLENGE)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "none"
    assert body["site_key"] == ""
    assert body["nonce"]


async def test_challenge_advertises_the_configured_site_key(
    client,  # noqa: ANN001
    monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setattr(settings, "captcha_provider", "turnstile")
    monkeypatch.setattr(settings, "captcha_site_key", "0x4AAA")

    body = (await client.get(_CHALLENGE)).json()

    assert body["provider"] == "turnstile"
    assert body["site_key"] == "0x4AAA"


async def test_the_nonce_is_scoped_to_its_own_token_type(client) -> None:  # noqa: ANN001
    """An access or refresh token must not double as a nonce."""
    nonce = (await client.get(_CHALLENGE)).json()["nonce"]

    claims = decode_token(nonce, expected_type="challenge")

    assert claims["type"] == "challenge"
    assert claims["exp"] - claims["iat"] == SIGNUP_CHALLENGE_TTL_MINUTES * 60


async def test_the_nonce_carries_no_account(client) -> None:  # noqa: ANN001
    """It is issued before anyone has identified themselves.

    A real subject here would be a session in disguise -- something an
    unauthenticated caller could present to an endpoint that trusts `sub`.
    """
    nonce = (await client.get(_CHALLENGE)).json()["nonce"]

    claims = decode_token(nonce, expected_type="challenge")

    assert claims["sub"] == "anonymous"


async def _nonce(client) -> str:  # noqa: ANN001
    return (await client.get(_CHALLENGE)).json()["nonce"]


async def _register(client, email: str, **extra: object):  # noqa: ANN001, ANN201
    return await client.post(
        _REGISTER, json={"email": email, "password": _PASSWORD, **extra}
    )


async def _account_exists(client, email: str) -> bool:  # noqa: ANN001
    """A successful login is the only proof the row was written."""
    resp = await client.post(_LOGIN, json={"email": email, "password": _PASSWORD})
    return resp.status_code == 200


async def test_a_filled_honeypot_creates_nothing(client, sent_emails) -> None:  # noqa: ANN001
    """Silently: the body is the one a real registration gets.

    A distinct status or message would tell an automated client exactly which
    layer caught it -- the information needed to tune around it -- and would
    break the byte-identical response /register already guarantees.
    """
    resp = await _register(
        client,
        "bot@user.com",
        challenge=await _nonce(client),
        website_url="http://spam.example",
    )

    assert resp.status_code == 202
    assert resp.json()["detail"] == "Check your email — we've sent you the next step."
    assert sent_emails == []
    assert not await _account_exists(client, "bot@user.com")


async def test_a_forged_nonce_is_rejected(client, sent_emails) -> None:  # noqa: ANN001
    resp = await _register(client, "bot2@user.com", challenge="not.a.jwt")

    assert resp.status_code == 202
    assert sent_emails == []
    assert not await _account_exists(client, "bot2@user.com")


async def test_an_access_token_is_not_a_valid_nonce(client, sent_emails) -> None:  # noqa: ANN001
    """`expected_type` is the control; a bare signature check would pass here.

    Every signed-in caller already holds an access token, so without the type
    check the nonce layer would be satisfied by a credential the attacker can
    mint for themselves in one request.
    """
    # Backdated past SIGNUP_MIN_FORM_SECONDS on purpose. A freshly minted token
    # would be refused by the age floor instead, and the test would pass while
    # asserting nothing about the type -- which is exactly what it did before
    # this line was added.
    issued_at = datetime.now(UTC) - timedelta(minutes=1)
    access = create_token("some-user-id", "access", extra_claims={"iat": issued_at})
    assert decode_token(access, expected_type="access")["type"] == "access"

    resp = await _register(client, "bot3@user.com", challenge=access)

    assert resp.status_code == 202
    assert sent_emails == []
    assert not await _account_exists(client, "bot3@user.com")


async def test_an_instant_submission_is_rejected(
    client,  # noqa: ANN001
    monkeypatch,  # noqa: ANN001
    sent_emails,  # noqa: ANN001
) -> None:
    """Nobody fills three fields in under two seconds.

    The floor is raised rather than the clock slowed: the nonce's `iat` is
    minted by the route under test, so a fixture cannot backdate it.
    """
    monkeypatch.setattr(human_check, "SIGNUP_MIN_FORM_SECONDS", 3600.0)

    resp = await _register(client, "bot4@user.com", challenge=await _nonce(client))

    assert resp.status_code == 202
    assert sent_emails == []
    assert not await _account_exists(client, "bot4@user.com")


async def test_a_missing_nonce_is_rejected(client, sent_emails) -> None:  # noqa: ANN001
    """Absent is not optional.

    The field is optional on the wire so the schema stays backward compatible;
    the *check* decides what a missing value means, and it means no.
    """
    resp = await _register(client, "bot5@user.com")

    assert resp.status_code == 202
    assert sent_emails == []
    assert not await _account_exists(client, "bot5@user.com")


async def test_a_well_formed_submission_still_registers(
    client,  # noqa: ANN001
    monkeypatch,  # noqa: ANN001
    sent_emails,  # noqa: ANN001
) -> None:
    """The layers must not block the case they exist to protect."""
    monkeypatch.setattr(human_check, "SIGNUP_MIN_FORM_SECONDS", 0.0)

    resp = await _register(client, "human@user.com", challenge=await _nonce(client))

    assert resp.status_code == 202
    assert sent_emails != [], "a real signup gets its verification mail"
    assert await _account_exists(client, "human@user.com")


async def test_forgot_password_is_gated_too(
    client,  # noqa: ANN001
    monkeypatch,  # noqa: ANN001
    sent_emails,  # noqa: ANN001
) -> None:
    """Same surface, same body, same protection."""
    monkeypatch.setattr(human_check, "SIGNUP_MIN_FORM_SECONDS", 0.0)
    await _register(client, "owner@user.com", challenge=await _nonce(client))
    sent_emails.clear()

    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "owner@user.com", "website_url": "http://spam.example"},
    )

    assert resp.status_code == 202
    assert (
        resp.json()["detail"]
        == "If an account exists for that address, a reset link is on its way."
    )
    assert sent_emails == [], "no reset link goes out"


async def test_every_rejection_is_counted(client, monkeypatch) -> None:  # noqa: ANN001
    """A silent rejection that is also unmeasured would be unfalsifiable."""
    from app.core.metrics import metrics

    await _register(client, "a@user.com", challenge="x", website_url="spam")
    await _register(client, "b@user.com", challenge="not.a.jwt")
    monkeypatch.setattr(human_check, "SIGNUP_MIN_FORM_SECONDS", 3600.0)
    await _register(client, "c@user.com", challenge=await _nonce(client))

    body = metrics.render()

    assert 'reason="honeypot"} 1' in body
    assert 'reason="challenge"} 2' in body
