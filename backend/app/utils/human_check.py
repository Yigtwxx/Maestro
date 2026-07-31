"""Anti-automation checks for the two unauthenticated mail endpoints.

Three layers behind one call, ordered cheapest first:

1. **Honeypot.** A form field a human never sees and a naive scraper fills.
2. **Challenge nonce.** A server-signed timestamp from GET /auth/challenge,
   valid only after `SIGNUP_MIN_FORM_SECONDS` and before its own `exp`. This is
   the weakest layer and is not pretending otherwise: a client that fetches the
   challenge, waits two seconds and posts defeats it. Its value is that it
   breaks the one-shot `curl` loop and forces the attacker to hold state.
3. **CAPTCHA.** Delegated to the provider seam, which is `none` by default so a
   self-hosted instance needs no third-party account.

Every rejection is **silent**: this returns False and the caller answers with
its normal fixed body. `/register` and `/forgot-password` are built so their
response reveals nothing, and a distinct status or message would both break that
guarantee and tell an automated client which layer caught it -- the one piece of
information needed to tune around it.

The cost is that a false positive is invisible to the user: someone who trips
the honeypot sees the success screen and gets no account. That is why every
rejection increments `maestro_abuse_rejected_total`; the metric is the only
place the false-positive rate becomes visible, which is what keeps these layers
falsifiable rather than merely reassuring.

Only the *unauthenticated* endpoints go through this. `POST /users/me/email` and
`POST /auth/resend-verification` both require a session, which is a stronger gate
than a CAPTCHA; they take the per-recipient mail budget alone.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import jwt

from app.core.constants import SIGNUP_MIN_FORM_SECONDS
from app.core.metrics import metrics
from app.core.security import decode_token
from app.services.captcha import get_captcha_provider


class HumanCheckPayload(Protocol):
    """The fields ``schemas.auth.HumanCheckFields`` contributes to a request."""

    website_url: str | None
    challenge: str | None
    captcha_token: str | None


async def passes(payload: HumanCheckPayload, remote_ip: str | None) -> bool:
    """Report whether this submission looks like a human using a browser.

    Returns True to proceed. On False the caller must still answer with its
    normal response body -- see the module docstring.
    """
    if payload.website_url:
        return _reject("honeypot")
    if not _challenge_is_valid(payload.challenge):
        return _reject("challenge")
    provider = get_captcha_provider()
    if not await provider.verify(payload.captcha_token, remote_ip):
        return _reject("captcha")
    return True


def _reject(reason: str) -> bool:
    """Count the rejection and report failure, so call sites stay one-liners."""
    metrics.record_abuse_rejection(reason)
    return False


def _challenge_is_valid(token: str | None) -> bool:
    """Verify the nonce's signature, type, expiry and minimum age.

    `expected_type` is load-bearing: without it any valid access or refresh
    token would satisfy this, and every signed-in caller already holds one.
    """
    if not token:
        return False
    try:
        claims = decode_token(token, expected_type="challenge")
    except jwt.InvalidTokenError:
        return False
    issued_at = claims.get("iat")
    if not isinstance(issued_at, (int, float)):
        return False
    age_seconds = datetime.now(UTC).timestamp() - float(issued_at)
    # Only a floor is checked here: the ceiling is the token's own `exp`, which
    # `decode_token` already enforced.
    return age_seconds >= SIGNUP_MIN_FORM_SECONDS
