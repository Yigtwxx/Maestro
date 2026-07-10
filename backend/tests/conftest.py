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
from app.services import code_execution_service, usage_service  # noqa: E402
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
def _usage_ledger_uses_test_db(monkeypatch):
    """usage_service opens its own session (it runs outside any request)."""
    monkeypatch.setattr(usage_service, "SessionLocal", _TestSession)


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
