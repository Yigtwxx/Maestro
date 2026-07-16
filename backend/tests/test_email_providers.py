"""Email provider adapters: console logging, Resend retry/backoff, registry."""

from __future__ import annotations

import logging

import httpx
import pytest

from app.core.config import settings
from app.services.email import (
    ConsoleEmailProvider,
    EmailError,
    EmailMessage,
    ResendProvider,
    get_email_provider,
)


def _message() -> EmailMessage:
    return EmailMessage(
        to="user@example.com",
        subject="Test subject",
        html="<p>Hello</p>",
        text="Hello http://localhost:3000/verify-email?token=abc",
    )


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    """Retry backoff must not slow the suite down."""

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.services.email.resend.asyncio.sleep", _no_sleep)


async def test_console_provider_logs_the_full_text_body(caplog) -> None:
    provider = ConsoleEmailProvider()
    with caplog.at_level(logging.INFO):
        await provider.send(_message())
    assert "verify-email?token=abc" in caplog.text, "dev link must appear in logs"


async def test_resend_provider_success_posts_once(monkeypatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"id": "email_1"})

    provider = ResendProvider(transport=httpx.MockTransport(handler))
    await provider.send(_message())
    assert len(calls) == 1
    assert calls[0].headers["authorization"].startswith("Bearer ")


async def test_resend_provider_retries_transient_500_then_succeeds() -> None:
    statuses = iter([500, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses))

    provider = ResendProvider(transport=httpx.MockTransport(handler))
    await provider.send(_message())  # must not raise


async def test_resend_provider_permanent_4xx_raises_without_retry() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(422)

    provider = ResendProvider(transport=httpx.MockTransport(handler))
    with pytest.raises(EmailError):
        await provider.send(_message())
    assert len(calls) == 1, "a permanent rejection must not be retried"


async def test_resend_provider_exhausted_retries_raises_email_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = ResendProvider(transport=httpx.MockTransport(handler))
    with pytest.raises(EmailError):
        await provider.send(_message())


def test_registry_returns_console_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "email_provider", "console")
    get_email_provider.cache_clear()
    assert isinstance(get_email_provider(), ConsoleEmailProvider)
    get_email_provider.cache_clear()
