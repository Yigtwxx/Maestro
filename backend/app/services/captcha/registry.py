"""CAPTCHA provider lookup.

Adding a provider is a two-line change here plus one adapter module; nothing
that calls ``get_captcha_provider`` needs to know.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.constants import CAPTCHA_PROVIDER_NONE, CAPTCHA_PROVIDER_TURNSTILE
from app.services.captcha.base import CaptchaError, CaptchaProvider
from app.services.captcha.none import NullCaptchaProvider
from app.services.captcha.turnstile import TurnstileProvider


@lru_cache
def get_captcha_provider() -> CaptchaProvider:
    """Return the configured CAPTCHA provider."""
    if settings.captcha_provider == CAPTCHA_PROVIDER_NONE:
        return NullCaptchaProvider()
    if settings.captcha_provider == CAPTCHA_PROVIDER_TURNSTILE:
        return TurnstileProvider()
    raise CaptchaError(f"Unknown captcha provider: {settings.captcha_provider}")
