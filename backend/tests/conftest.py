"""Shared test fixtures.

Sets required secrets and a SQLite backend *before* importing the app, then
provides an httpx client wired to an in-memory database.
"""

from __future__ import annotations

import base64
import os
from types import SimpleNamespace

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
    community_read_service,
    connected_common,
    custom_api_service,
    data_fetch_service,
    email_service,
    places_intel_service,
    question_store,
    quota_service,
    reconcile,
    repo_intel_service,
    service_key_service,
    social_search_service,
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
def _no_browser_probe(monkeypatch):
    """Tests never touch browser binaries; the render tier reads as unavailable.

    Mirrors ``_no_docker_probe``. The two import-cache globals are reset because
    they are process-wide: a fake fetcher installed by one module would
    otherwise leak into every test that ran after it. Tests that exercise
    rendering set ``_render_availability`` themselves.
    """
    monkeypatch.setattr(data_fetch_service, "_render_availability", False)
    monkeypatch.setattr(data_fetch_service, "_static_fetcher", None)
    monkeypatch.setattr(data_fetch_service, "_stealthy_fetcher", None)
    monkeypatch.setattr(data_fetch_service, "_import_error", None)


@pytest.fixture(autouse=True)
def _no_connected_http(monkeypatch):
    """The connected-API tools share one module-global httpx client.

    Same reasoning as ``_no_browser_probe``: the client is process-wide, so a
    fake installed by one test module would otherwise serve every module that
    ran after it. Tests that exercise these tools patch ``request_json`` or the
    client themselves.
    """
    monkeypatch.setattr(connected_common, "_client", None)


class FakeConnectedHTTP:
    """Records every connected-API request and replays queued responses in order.

    A queued item is a raw JSON body, served as 200; queue an ``ApiResult``
    instead when a test needs a particular status. ``None`` is a dead provider,
    and so is an exhausted queue — an unstubbed call must not look like success.
    """

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def __call__(self, url: str, **kwargs: object) -> object:
        return (await self.api(url, **kwargs)).data

    async def api(self, url: str, **kwargs: object) -> connected_common.ApiResult:
        self.calls.append({"url": url, **kwargs})
        queued = self.responses.pop(0) if self.responses else None
        if isinstance(queued, connected_common.ApiResult):
            return queued
        if queued is None:
            return connected_common.ApiResult()
        return connected_common.ApiResult(data=queued, status=200)


@pytest.fixture
def http(monkeypatch):
    """Install a fake HTTP boundary into every connected-API service.

    Both seams are patched: ``request_json`` for the three services that only
    want a body, and ``request_api`` for ``repo_intel``, whose recovery ladder
    branches on the status. Patching one and not the other is how a test quietly
    reaches the real network, so ``raising=False`` covers the modules that
    import only one of them.
    """

    def _install(*responses: object) -> FakeConnectedHTTP:
        fake = FakeConnectedHTTP(*responses)
        for module in (
            repo_intel_service,
            social_search_service,
            community_read_service,
            places_intel_service,
        ):
            monkeypatch.setattr(module, "request_json", fake, raising=False)
            monkeypatch.setattr(module, "request_api", fake.api, raising=False)
        return fake

    return _install


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
        service_key_service,
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


# --- In-memory Mongo collection (custom API tools) --------------------------


def _mongo_matches(doc: dict, criteria: dict) -> bool:
    """The subset of Motor's query language the custom-API paths use."""
    for key, value in criteria.items():
        actual = doc.get(key)
        if isinstance(value, dict):
            for operator, operand in value.items():
                if operator == "$in":
                    if actual not in operand:
                        return False
                else:  # pragma: no cover - unmodelled operator
                    raise NotImplementedError(operator)
        elif actual != value:
            return False
    return True


class FakeMongoCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, field: str, direction: int) -> FakeMongoCursor:
        self._docs.sort(key=lambda d: d[field], reverse=direction < 0)
        return self

    def limit(self, count: int) -> FakeMongoCursor:
        self._docs = self._docs[:count]
        return self

    async def __aiter__(self):
        for doc in self._docs:
            yield doc


class FakeMongoCollection:
    """The slice of Motor the custom-API service uses, projections included.

    Projections are honoured for real, which is the point: the service relies on
    them to keep ``encrypted_secret`` out of every response, and a fake that
    ignored them would let that regression pass.
    """

    def __init__(self, docs: list[dict] | None = None) -> None:
        self.docs: list[dict] = docs if docs is not None else []

    def _project(self, doc: dict, projection: dict | None) -> dict:
        if not projection:
            return dict(doc)
        included = {k for k, v in projection.items() if v == 1}
        excluded = {k for k, v in projection.items() if v == 0}
        if included:
            return {k: v for k, v in doc.items() if k in included}
        return {k: v for k, v in doc.items() if k not in excluded}

    async def find_one(self, criteria: dict, projection: dict | None = None):
        for doc in self.docs:
            if _mongo_matches(doc, criteria):
                return self._project(doc, projection)
        return None

    def find(self, criteria: dict, projection: dict | None = None) -> FakeMongoCursor:
        return FakeMongoCursor(
            [
                self._project(d, projection)
                for d in self.docs
                if _mongo_matches(d, criteria)
            ]
        )

    async def count_documents(self, criteria: dict) -> int:
        return sum(1 for doc in self.docs if _mongo_matches(doc, criteria))

    async def insert_one(self, doc: dict) -> None:
        self.docs.append(dict(doc))

    async def update_one(self, criteria: dict, update: dict):
        for doc in self.docs:
            if _mongo_matches(doc, criteria):
                doc.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    async def delete_one(self, criteria: dict):
        for index, doc in enumerate(self.docs):
            if _mongo_matches(doc, criteria):
                del self.docs[index]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


@pytest.fixture
def custom_api_db(monkeypatch) -> FakeMongoCollection:
    """Point custom_api_service at an in-memory collection."""
    collection = FakeMongoCollection()
    monkeypatch.setattr(custom_api_service, "_collection", lambda: collection)
    return collection
