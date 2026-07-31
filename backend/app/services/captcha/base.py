"""CAPTCHA provider seam.

Mirrors the email and payment adapters (``services/email``, ``services/payment``):
adding a provider -- hCaptcha, reCAPTCHA -- means adding one adapter module, not
editing the code that calls it. The null adapter keeps dev and self-host working
with zero dependencies and zero network, which is what lets `CAPTCHA_PROVIDER`
default to "none" without any call site having to branch on it.
"""

from __future__ import annotations

from typing import Protocol


class CaptchaError(RuntimeError):
    """Raised when the configured provider name cannot be resolved."""


class CaptchaProvider(Protocol):
    """Interface every CAPTCHA adapter must implement."""

    name: str

    async def verify(self, token: str | None, remote_ip: str | None) -> bool:
        """Report whether `token` is a genuine, unspent client solution.

        Must never raise: a provider outage is answered False (fail closed), so
        the call sites stay branch-free.
        """
        ...
