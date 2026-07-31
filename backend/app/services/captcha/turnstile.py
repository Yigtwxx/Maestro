"""Cloudflare Turnstile adapter."""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings
from app.core.constants import CAPTCHA_PROVIDER_TURNSTILE, TURNSTILE_VERIFY_URL

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0


class TurnstileProvider:
    """Verifies a client token against Cloudflare's siteverify endpoint.

    The host is a constant in `constants.py`, never model- or user-supplied, so
    like the other connected-API clients this has no SSRF surface and
    deliberately does not go through `url_guard`. Redirects are not followed:
    there is no legitimate hop, and one would carry the secret to another origin.
    """

    name = CAPTCHA_PROVIDER_TURNSTILE

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """`transport` is an injection point for tests; production passes None."""
        self._transport = transport

    async def verify(self, token: str | None, remote_ip: str | None) -> bool:
        """Report whether Cloudflare accepts `token`.

        Fails closed on every error path. If siteverify is unreachable the
        widget did not load for real users either, so they hold no token
        regardless -- failing open would relax the gate only for the automated
        clients that never needed the widget.
        """
        if not token:
            return False
        form = {"secret": settings.captcha_secret_key, "response": token}
        if remote_ip:
            form["remoteip"] = remote_ip
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT_SECONDS,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.post(TURNSTILE_VERIFY_URL, data=form)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Logged by exception *class*, never by message: an httpx error can
            # echo the request, and the request body carries the secret.
            logger.warning(
                "Turnstile verification failed (%s); rejecting the submission",
                type(exc).__name__,
            )
            return False
        return bool(body.get("success"))
