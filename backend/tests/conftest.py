"""Shared test fixtures.

Sets required secrets and a SQLite backend *before* importing the app, then
provides an httpx client wired to an in-memory database.
"""

from __future__ import annotations

import base64
import os

# Must be set before any `app.*` import (settings are cached at import time).
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-that-is-long-enough-32b")
os.environ.setdefault("API_KEY_MASTER_KEY", base64.b64encode(b"0" * 32).decode("ascii"))
os.environ.setdefault("POSTGRES_URL", "sqlite+aiosqlite://")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services import (  # noqa: E402
    checkpoint_store,
    code_execution_service,
    email_service,
    question_store,
    quota_service,
    reconcile,
    task_run_store,
    usage_service,
)
from app.services.email import EmailMessage  # noqa: E402
from app.utils.rate_limiter import limiter  # noqa: E402

_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _no_docker_probe(monkeypatch):
    """Tests never touch the Docker CLI; the sandbox reads as unavailable.

    Tests that need the tool enabled monkeypatch ``is_available`` themselves.
    """
    monkeypatch.setattr(code_execution_service, "_availability", False)


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """Buckets are process-wide; the suite's repeated auth calls would trip 429s.

    Tests that exercise the limiter itself request the ``rate_limited`` fixture.
    """
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    limiter.reset()


@pytest.fixture
def rate_limited(_no_rate_limit, monkeypatch):
    """Re-enable rate limiting for one test, against empty buckets."""
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    limiter.reset()
    yield limiter
    limiter.reset()


@pytest.fixture(autouse=True)
def _engine_stores_use_test_db(monkeypatch):
    """Services that run outside a request open their own session; point every
    one at the in-memory test database (mirrors the app's ``get_db`` override)."""
    for module in (
        usage_service,
        task_run_store,
        checkpoint_store,
        question_store,
        quota_service,
        reconcile,
    ):
        monkeypatch.setattr(module, "SessionLocal", _TestSession)


@pytest.fixture(autouse=True)
async def _setup_database():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session():
    """A session against the same in-memory database the app under test uses."""
    async with _TestSession() as session:
        yield session


@pytest.fixture
async def client():
    async def _override_get_db():
        async with _TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class RecordingEmailProvider:
    """Captures outbound email so tests can extract action links."""

    name = "recording"

    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def send(self, message) -> None:  # noqa: ANN001 - EmailMessage
        self.messages.append(message)


@pytest.fixture(autouse=True)
def _email_gate_off(monkeypatch):
    """The soft verification gate is opt-in per test (mirrors _no_rate_limit).

    Without this, every existing test that starts a task or adds an API key
    would need a verification step. Gate behaviour itself is covered by tests
    that request the ``email_gate`` fixture.
    """
    monkeypatch.setattr(settings, "email_verification_required", False)


@pytest.fixture
def email_gate(monkeypatch):
    """Re-enable the soft verification gate for one test."""
    monkeypatch.setattr(settings, "email_verification_required", True)


@pytest.fixture
def sent_emails(monkeypatch):
    """Swap the provider for a recorder; returns the captured message list."""
    provider = RecordingEmailProvider()
    monkeypatch.setattr(email_service, "get_email_provider", lambda: provider)
    return provider.messages
