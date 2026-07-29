"""Email settings defaults and the production RESEND_API_KEY guard."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.constants import (
    EMAIL_PROVIDER_CONSOLE,
    EMAIL_PROVIDER_RESEND,
    EmailTokenPurpose,
)


def test_settings_email_defaults_are_console_and_ungated() -> None:
    # The two defaults are one decision, not two: the console provider writes
    # verification mail to the server log instead of an inbox, so shipping the
    # gate on would 403 task start and API-key create for every account on a
    # fresh install with no way through. Turn the gate on only together with a
    # real sender -- and with EMAIL_VERIFICATION_LIVE on the frontend.
    fresh = Settings(_env_file=None)
    assert fresh.email_provider == EMAIL_PROVIDER_CONSOLE
    assert fresh.email_verification_required is False
    assert fresh.site_url.startswith("http")


def test_email_token_purpose_values_are_stable() -> None:
    # Persisted in the DB `purpose` column: renaming a value orphans rows.
    assert EmailTokenPurpose.VERIFY_EMAIL.value == "verify_email"
    assert EmailTokenPurpose.RESET_PASSWORD.value == "reset_password"


def test_production_resend_without_api_key_refuses_to_boot() -> None:
    with pytest.raises(ValidationError, match="RESEND_API_KEY"):
        Settings(
            environment="production",
            jwt_secret="x" * 40,
            api_key_master_key="a" * 64,  # 64-char hex = 32 bytes
            email_provider=EMAIL_PROVIDER_RESEND,
            resend_api_key="",
            _env_file=None,
        )
