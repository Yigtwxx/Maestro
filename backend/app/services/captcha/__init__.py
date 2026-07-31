"""Provider-agnostic CAPTCHA verification layer."""

from app.services.captcha.base import CaptchaError, CaptchaProvider
from app.services.captcha.none import NullCaptchaProvider
from app.services.captcha.registry import get_captcha_provider
from app.services.captcha.turnstile import TurnstileProvider

__all__ = [
    "CaptchaError",
    "CaptchaProvider",
    "NullCaptchaProvider",
    "TurnstileProvider",
    "get_captcha_provider",
]
