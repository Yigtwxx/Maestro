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


def test_development_allows_defaults() -> None:
    settings = _make(
        environment="development",
        jwt_secret="change-me",
        api_key_master_key="change-me-32-byte-base64-master-key",
    )
    assert settings.jwt_secret == "change-me"
