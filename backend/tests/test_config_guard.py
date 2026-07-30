"""Production secret guard (config.py:_guard_production_secrets).

The guard blocks startup when ENVIRONMENT=production and the JWT/AES secrets are
still placeholders or too weak. Settings is instantiated directly with explicit
kwargs: init args outrank environment variables in pydantic-settings, so
conftest's ``JWT_SECRET`` env value never leaks into these cases. ``_env_file``
is disabled so a local ``.env`` cannot influence the result either.
"""

from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from app.core.config import Settings

# A 32-byte AES master key, base64-encoded — the valid production shape.
_VALID_MASTER_KEY = base64.b64encode(b"0" * 32).decode("ascii")
_STRONG_JWT_SECRET = "s" * 40


def _make(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        _make(
            environment="production",
            jwt_secret="change-me",
            api_key_master_key=_VALID_MASTER_KEY,
        )


def test_production_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        _make(
            environment="production",
            jwt_secret="tooshort",
            api_key_master_key=_VALID_MASTER_KEY,
        )


def test_production_rejects_default_master_key() -> None:
    with pytest.raises(ValidationError):
        _make(
            environment="production",
            jwt_secret=_STRONG_JWT_SECRET,
            api_key_master_key="change-me-32-byte-base64-master-key",
        )


def test_production_rejects_bad_master_key() -> None:
    with pytest.raises(ValidationError):
        _make(
            environment="production",
            jwt_secret=_STRONG_JWT_SECRET,
            api_key_master_key="not-thirty-two-bytes",
        )


def test_production_accepts_strong_secrets() -> None:
    settings = _make(
        environment="production",
        jwt_secret=_STRONG_JWT_SECRET,
        api_key_master_key=_VALID_MASTER_KEY,
    )
    assert settings.environment == "production"


def test_production_rejects_an_insecure_refresh_cookie() -> None:
    # The cookie *is* the session; over plain HTTP it is readable in transit.
    with pytest.raises(ValidationError):
        _make(
            environment="production",
            jwt_secret=_STRONG_JWT_SECRET,
            api_key_master_key=_VALID_MASTER_KEY,
            refresh_cookie_secure=False,
        )


def test_refresh_cookie_is_secure_by_default_outside_development() -> None:
    """Unset means "on unless this is a dev box", so nobody has to remember it."""
    assert (
        _make(
            environment="production",
            jwt_secret=_STRONG_JWT_SECRET,
            api_key_master_key=_VALID_MASTER_KEY,
        ).refresh_cookie_is_secure
        is True
    )
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
