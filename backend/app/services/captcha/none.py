"""The no-op adapter: the shipping default."""

from __future__ import annotations

from app.core.constants import CAPTCHA_PROVIDER_NONE


class NullCaptchaProvider:
    """Passes every request, performing no I/O.

    Not a gate everyone happens to pass -- it is the *absence* of the CAPTCHA
    layer, leaving the honeypot and challenge-nonce layers to carry the check.
    A self-hosted instance runs this and sends no bytes to any third party.
    """

    name = CAPTCHA_PROVIDER_NONE

    async def verify(self, token: str | None, remote_ip: str | None) -> bool:
        """Always True. `token` and `remote_ip` are deliberately unused."""
        return True
