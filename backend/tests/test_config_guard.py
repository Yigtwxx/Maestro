"""Production config guard (config.py:_guard_production_secrets).

The guard blocks startup when ENVIRONMENT=production and the JWT/AES secrets are
still placeholders or too weak, a datastore URL still carries an example or
default password, rate limiting is switched off, or the proxy-header decision was
never made. Settings is instantiated directly with explicit kwargs: init args
outrank environment variables in pydantic-settings, so conftest's ``JWT_SECRET``
env value never leaks into these cases. ``_env_file`` is disabled so a local
``.env`` cannot influence the result either.
"""

from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from app.core.config import Settings

# A 32-byte AES master key, base64-encoded — the valid production shape.
_VALID_MASTER_KEY = base64.b64encode(b"0" * 32).decode("ascii")
_STRONG_JWT_SECRET = "s" * 40

# What a real production deployment sets. Each case below overrides one key, so a
# failure names exactly the variable the test is about — otherwise every
# `pytest.raises` here would keep passing even if the rule it targets were
# deleted, because the config would be invalid for unrelated reasons.
_PROD_POSTGRES_URL = "postgresql+asyncpg://maestro:Hk2p9WqLb4Tz@postgres:5432/maestro"
_PROD_MONGODB_URL = "mongodb://maestro:Hk2p9WqLb4Tz@mongo:27017/?authSource=admin"
_PROD_OK: dict[str, object] = {
    "environment": "production",
    "jwt_secret": _STRONG_JWT_SECRET,
    "api_key_master_key": _VALID_MASTER_KEY,
    "postgres_url": _PROD_POSTGRES_URL,
    "mongodb_url": _PROD_MONGODB_URL,
    "trust_proxy_headers": True,
}


def _make(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def _prod(**overrides: object) -> Settings:
    """A production config that boots, with ``overrides`` applied."""
    return _make(**{**_PROD_OK, **overrides})


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        _prod(jwt_secret="change-me")


def test_production_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        _prod(jwt_secret="tooshort")


def test_production_rejects_default_master_key() -> None:
    with pytest.raises(ValidationError, match="API_KEY_MASTER_KEY"):
        _prod(api_key_master_key="change-me-32-byte-base64-master-key")


def test_production_rejects_bad_master_key() -> None:
    with pytest.raises(ValidationError, match="API_KEY_MASTER_KEY"):
        _prod(api_key_master_key="not-thirty-two-bytes")


def test_production_accepts_strong_secrets() -> None:
    settings = _prod()
    assert settings.environment == "production"


def test_production_rejects_an_insecure_refresh_cookie() -> None:
    # The cookie *is* the session; over plain HTTP it is readable in transit.
    with pytest.raises(ValidationError, match="REFRESH_COOKIE_SECURE"):
        _prod(refresh_cookie_secure=False)


def test_refresh_cookie_is_secure_by_default_outside_development() -> None:
    """Unset means "on unless this is a dev box", so nobody has to remember it."""
    assert _prod().refresh_cookie_is_secure is True
    # Development opts out on its own: Safari refuses a Secure cookie over
    # http://localhost, which would break `npm run dev` in one major browser.
    assert _make(environment="development").refresh_cookie_is_secure is False


def test_refresh_cookie_samesite_rejects_none() -> None:
    """SameSite=none would delete the only CSRF control on /refresh + /logout."""
    with pytest.raises(ValidationError):
        _make(refresh_cookie_samesite="none")


def test_development_allows_defaults() -> None:
    settings = _make(
        environment="development",
        jwt_secret="change-me",
        api_key_master_key="change-me-32-byte-base64-master-key",
    )
    assert settings.jwt_secret == "change-me"


@pytest.mark.parametrize(
    ("field", "value", "expected_variable"),
    [
        # Still the development default: a local datastore whose password is
        # published in this repository.
        (
            "postgres_url",
            "postgresql+asyncpg://maestro:maestro@localhost:5433/maestro",
            "POSTGRES_URL",
        ),
        ("mongodb_url", "mongodb://localhost:27018", "MONGODB_URL"),
        # A verbatim copy of .env.prod.example, where CHANGE_ME was never
        # substituted. The Redis case is the sneaky one: it boots today and
        # silently degrades to per-process buckets, weakening every throttle.
        (
            "postgres_url",
            "postgresql+asyncpg://maestro:CHANGE_ME@postgres:5432/maestro",
            "POSTGRES_URL",
        ),
        (
            "mongodb_url",
            "mongodb://maestro:CHANGE_ME@mongo:27017/?authSource=admin",
            "MONGODB_URL",
        ),
        ("redis_url", "redis://:CHANGE_ME@redis:6379/0", "REDIS_URL"),
        # Guessable: the password equals the username, or is a compose default.
        (
            "postgres_url",
            "postgresql+asyncpg://postgres:postgres@db:5432/maestro",
            "POSTGRES_URL",
        ),
        (
            "mongodb_url",
            "mongodb://maestro:password@mongo:27017/?authSource=admin",
            "MONGODB_URL",
        ),
    ],
)
def test_production_datastore_placeholder_or_default_rejected(
    field: str, value: str, expected_variable: str
) -> None:
    with pytest.raises(ValidationError, match=expected_variable):
        _prod(**{field: value})


def test_production_qdrant_api_key_placeholder_rejected() -> None:
    with pytest.raises(ValidationError, match="QDRANT_API_KEY"):
        _prod(qdrant_api_key="CHANGE_ME")


def test_production_datastore_without_credentials_accepted() -> None:
    """The guard rejects placeholders and defaults, not the absence of auth.

    A MongoDB or Redis reachable only on the compose network legitimately runs
    without a password; refusing that would break a working deployment.
    """
    settings = _prod(
        mongodb_url="mongodb://mongo:27017/?directConnection=true",
        redis_url="redis://redis:6379/0",
    )
    assert settings.environment == "production"


def test_production_unparseable_datastore_url_accepted() -> None:
    """A malformed URL must not become a bogus credential complaint.

    urlsplit raises on a broken IPv6 literal; the driver's own connection error
    is the useful message, so credential inspection stays silent here.
    """
    settings = _prod(redis_url="redis://[::1:6379/0")
    assert settings.environment == "production"


def test_production_rate_limiting_disabled_rejected() -> None:
    # Documented as forbidden since day one, now enforced: with no limiter,
    # credential stuffing against /auth/login costs an attacker nothing.
    with pytest.raises(ValidationError, match="RATE_LIMIT_ENABLED"):
        _prod(rate_limit_enabled=False)


def test_production_unset_proxy_headers_rejected() -> None:
    """Neither value is safe in every topology, so unset must not be guessed.

    `true` with the backend exposed lets a client forge X-Forwarded-For and mint
    a bucket per request; `false` behind Caddy buckets everyone under the proxy's
    single container IP, so one client tripping the login limit locks out the
    rest.
    """
    with pytest.raises(ValidationError, match="TRUST_PROXY_HEADERS"):
        _prod(trust_proxy_headers=None)


def test_proxy_headers_are_trusted_resolves_unset_to_false() -> None:
    # Preserves the pre-tri-state default exactly: development and the test
    # suite read the peer address and never believe the header.
    assert _make(environment="development").proxy_headers_are_trusted is False
    assert _prod(trust_proxy_headers=False).proxy_headers_are_trusted is False
    assert _prod(trust_proxy_headers=True).proxy_headers_are_trusted is True


def test_production_guard_reports_every_problem_at_once() -> None:
    """One boot attempt, one complete list.

    An operator who copied .env.prod.example must not have to restart four times
    to discover four mistakes — which is also why every production check lives in
    one validator: pydantic stops at the first `mode="after"` validator that
    raises, so a second one's findings would never be seen.
    """
    with pytest.raises(ValidationError) as excinfo:
        _prod(
            jwt_secret="change-me",
            postgres_url="postgresql+asyncpg://maestro:CHANGE_ME@postgres:5432/maestro",
            rate_limit_enabled=False,
            trust_proxy_headers=None,
        )
    message = excinfo.value.errors()[0]["msg"]
    assert "Insecure production configuration: " in message, message
    for variable in (
        "JWT_SECRET",
        "POSTGRES_URL",
        "RATE_LIMIT_ENABLED",
        "TRUST_PROXY_HEADERS",
    ):
        assert variable in message, f"{variable} missing from: {message}"


def test_production_guard_never_echoes_a_credential() -> None:
    """A datastore URL *is* a password, and boot failures land in logs.

    Asserted on the validator's own message rather than on
    `str(ValidationError)`: pydantic appends a truncated repr of the whole input
    dict to the latter, which is a separate, pre-existing concern (it already
    applies to JWT_SECRET) and not what this guard controls.
    """
    password = "Zt7QpX2mVr8LdN4s"
    with pytest.raises(ValidationError) as excinfo:
        _prod(
            postgres_url=f"postgresql+asyncpg://maestro:{password}@postgres:5432/x",
            rate_limit_enabled=False,
        )
    message = excinfo.value.errors()[0]["msg"]
    assert password not in message, message


def test_multi_worker_without_redis_rejected_in_any_environment() -> None:
    # Not gated on ENVIRONMENT=production: multi-worker without Redis is
    # broken everywhere (event bus / HITL / cancel go process-local).
    with pytest.raises(ValidationError):
        _make(environment="development", web_concurrency=4, redis_url="")


def test_multi_worker_with_redis_accepted() -> None:
    settings = _make(web_concurrency=4, redis_url="redis://localhost:6379/0")
    assert settings.web_concurrency == 4


def test_single_worker_without_redis_accepted() -> None:
    settings = _make(web_concurrency=1, redis_url="")
    assert settings.web_concurrency == 1


def test_code_execution_defaults_off() -> None:
    # Fail-closed: enabling this tool means the backend can reach a Docker
    # daemon, so a deployment that never sets the variable must not get it.
    settings = _make()
    assert settings.code_execution_enabled is False, (
        "CODE_EXECUTION_ENABLED must default to false — see config.py"
    )


def test_turnstile_without_keys_is_refused() -> None:
    """A provider that cannot verify is worse than no provider at all.

    `none` degrades honestly to the honeypot and nonce layers. `turnstile` with
    no secret fails closed on every call, so registration silently stops
    working -- refuse the boot instead of discovering it from support tickets.
    """
    with pytest.raises(ValidationError, match="CAPTCHA_SECRET_KEY"):
        _prod(captcha_provider="turnstile", captcha_site_key="0x4AAA")


def test_turnstile_with_both_keys_boots() -> None:
    _prod(
        captcha_provider="turnstile",
        captcha_site_key="0x4AAA",
        captcha_secret_key="0x4BBB",
    )


def test_unknown_captcha_provider_is_refused() -> None:
    with pytest.raises(ValidationError, match="CAPTCHA_PROVIDER"):
        _make(captcha_provider="recaptcha")
