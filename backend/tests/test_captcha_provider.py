"""CAPTCHA adapter seam: resolution, fail-closed behaviour, secret hygiene."""

from __future__ import annotations

import httpx
import pytest

from app.core.config import settings
from app.services.captcha import (
    NullCaptchaProvider,
    TurnstileProvider,
    get_captcha_provider,
)

_SECRET = "0xSUPERSECRET"


@pytest.fixture(autouse=True)
def _clear_provider_cache():  # noqa: ANN202
    """``get_captcha_provider`` is ``lru_cache``d, so a resolved provider would
    otherwise outlive the setting the next test monkeypatches."""
    get_captcha_provider.cache_clear()
    yield
    get_captcha_provider.cache_clear()


def _provider(monkeypatch, handler) -> TurnstileProvider:  # noqa: ANN001
    """A Turnstile adapter wired to `handler` instead of the network."""
    monkeypatch.setattr(settings, "captcha_secret_key", _SECRET)
    return TurnstileProvider(transport=httpx.MockTransport(handler))


def test_default_provider_is_the_null_one() -> None:
    provider = get_captcha_provider()
    assert isinstance(provider, NullCaptchaProvider), (
        "a self-hosted instance must reach no third party by default"
    )


def test_turnstile_is_resolved_when_configured(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "captcha_provider", "turnstile")
    assert isinstance(get_captcha_provider(), TurnstileProvider)


async def test_null_provider_passes_without_a_token() -> None:
    """`none` is the absence of the layer, not a gate everyone happens to pass."""
    assert await NullCaptchaProvider().verify(None, None) is True


async def test_turnstile_accepts_a_verified_token(monkeypatch) -> None:  # noqa: ANN001
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True})

    provider = _provider(monkeypatch, _handler)

    assert await provider.verify("token", "203.0.113.7") is True


async def test_turnstile_rejects_an_unverified_token(monkeypatch) -> None:  # noqa: ANN001
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"success": False, "error-codes": ["invalid-input-response"]}
        )

    provider = _provider(monkeypatch, _handler)

    assert await provider.verify("token", None) is False


async def test_turnstile_fails_closed_on_a_transport_error(monkeypatch) -> None:  # noqa: ANN001
    """An outage must not relax the gate.

    Fail-open is tempting and wrong: if Cloudflare is unreachable the widget did
    not load for real users either, so they hold no token regardless. Fail-open
    would relax the gate only for clients that never needed the widget.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    provider = _provider(monkeypatch, _handler)

    assert await provider.verify("token", None) is False


async def test_turnstile_fails_closed_on_a_server_error(monkeypatch) -> None:  # noqa: ANN001
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    provider = _provider(monkeypatch, _handler)

    assert await provider.verify("token", None) is False


async def test_turnstile_rejects_a_missing_token(monkeypatch) -> None:  # noqa: ANN001
    """No request is made at all -- there is nothing to verify."""

    def _handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("a missing token must not reach the network")

    provider = _provider(monkeypatch, _handler)

    assert await provider.verify(None, None) is False


async def test_the_secret_never_reaches_a_log(monkeypatch, caplog) -> None:  # noqa: ANN001
    """The secret is a credential; an error log is not a vault."""

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    provider = _provider(monkeypatch, _handler)

    with caplog.at_level("DEBUG"):
        await provider.verify("token", None)

    assert _SECRET not in caplog.text, "the secret leaked into a log record"
