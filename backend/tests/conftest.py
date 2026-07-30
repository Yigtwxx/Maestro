"""Shared test fixtures.

Sets required secrets and a SQLite backend *before* importing the app, then
provides an httpx client wired to an in-memory database.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from types import SimpleNamespace

# Must be set before any `app.*` import (settings are cached at import time).
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-that-is-long-enough-32b")
os.environ.setdefault("API_KEY_MASTER_KEY", base64.b64encode(b"0" * 32).decode("ascii"))
os.environ.setdefault("POSTGRES_URL", "sqlite+aiosqlite://")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from qdrant_client import AsyncQdrantClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core import database  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.cookies import (  # noqa: E402
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
)
from app.core.database import get_db  # noqa: E402
from app.core.metrics import metrics  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services import (  # noqa: E402
    alert_service,
    checkpoint_store,
    code_execution_service,
    community_read_service,
    connected_common,
    custom_api_service,
    data_fetch_service,
    email_service,
    memory_service,
    places_intel_service,
    question_store,
    quota_service,
    reconcile,
    repo_intel_service,
    service_key_service,
    social_search_service,
    task_run_store,
    usage_service,
    watchdog,
)
from app.services.alerts import get_alert_channels  # noqa: E402
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
async def other_db_session():
    """A second, independent session on the same in-memory database.

    For exercising two callers racing over one row. StaticPool means both
    sessions share a single SQLite connection, so this proves a claim is
    issued as SQL immediately rather than deferred to pending ORM state --
    it cannot reproduce real cross-connection locking (PostgreSQL only).
    """
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


@pytest.fixture
def send_refresh_cookie(client):
    """Pin a specific refresh token into the client's jar for the next request.

    The refresh token only travels as an httpOnly cookie now, and ``client`` is
    one AsyncClient with one shared jar: a second login overwrites the first,
    and rotation evicts the value a replay test needs. Capturing
    ``resp.cookies[REFRESH_COOKIE_NAME]`` and putting it back explicitly is how
    a test controls *which* token it presents. Setting it on the client rather
    than per-request because httpx deprecated the latter.
    """

    def _set(token: str) -> None:
        client.cookies.set(REFRESH_COOKIE_NAME, token, path=REFRESH_COOKIE_PATH)

    return _set


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


@pytest.fixture(autouse=True)
def _billing_on(monkeypatch):
    """Paid plans are reachable by default, so the flow stays under test.

    Shipping config parks them behind ``BILLING_ENABLED=false`` while no real
    processor exists, but the subscribe/cancel machinery still has to work the
    day it is switched on. Tests of the parked state request ``billing_off``.
    """
    monkeypatch.setattr(settings, "billing_enabled", True)


@pytest.fixture
def billing_off(monkeypatch):
    """Park paid plans for one test (the shipping default)."""
    monkeypatch.setattr(settings, "billing_enabled", False)


@pytest.fixture
def sent_emails(monkeypatch):
    """Swap the provider for a recorder; returns the captured message list."""
    provider = RecordingEmailProvider()
    monkeypatch.setattr(email_service, "get_email_provider", lambda: provider)
    return provider.messages


@pytest.fixture(autouse=True)
def _no_alerting(monkeypatch):
    """Operator alerting is opt-in per test (mirrors ``_no_rate_limit``).

    The channel registry is ``lru_cache``d and the watchdog holds process-wide
    state, so both are cleared here — otherwise one test's configuration serves
    every test that runs after it, and a stale state machine makes the
    transition assertions in ``test_watchdog.py`` order-dependent.
    """
    monkeypatch.setattr(settings, "alert_webhook_url", "")
    monkeypatch.setattr(settings, "alert_email_to", "")
    get_alert_channels.cache_clear()
    alert_service.reset()
    watchdog.watchdog.reset()
    yield
    get_alert_channels.cache_clear()
    alert_service.reset()
    watchdog.watchdog.reset()


@pytest.fixture(autouse=True)
def _reset_metrics():
    """Counters are process-wide, like the rate limiter's buckets."""
    metrics.reset()
    yield
    metrics.reset()


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


# --- Real Qdrant round-trips ------------------------------------------------
#
# Every Qdrant double in this suite used to hand-define the methods it needed,
# so when qdrant-client removed `search` the fakes kept answering and
# `retrieve_memories` — which degrades to [] on any exception — reported "no
# results" for every user in production while CI stayed green. The fixtures
# below run the real client instead: local mode is qdrant-client's own
# implementation, so filters are genuinely evaluated and vector dimensions
# genuinely validated, and a removed method fails loudly.

# Small on purpose: nothing here depends on the real 768-wide model, and a
# narrow vector keeps the local-mode collections cheap.
TEST_EMBEDDING_DIM = 8


def deterministic_vector(text: str) -> list[float]:
    """A stable, non-zero vector derived from ``text``.

    Deterministic rather than random so a failure reproduces exactly. The
    ``1.0 +`` floor keeps every component positive: cosine distance is undefined
    for a zero vector and Qdrant rejects one.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [1.0 + digest[i] / 255.0 for i in range(TEST_EMBEDDING_DIM)]


@pytest.fixture(autouse=True)
def _clear_qdrant_collection_cache():
    """``memory_service._known_collections`` is process-wide.

    ``ensure_collection`` short-circuits on it, so a collection registered by
    one test would make the call a no-op for whichever test ran next — against a
    client that never saw it created. Autouse because the coupling is invisible
    at the call site.
    """
    memory_service._known_collections.clear()
    yield
    memory_service._known_collections.clear()


@pytest.fixture
def embeddings(monkeypatch) -> list[str]:
    """Swap the embedding endpoint for a deterministic in-process stub.

    The vectors are fake but their *width* is real — it matches the
    ``embedding_dim`` the collection is created with, so a mismatch between the
    two still fails the upsert rather than being quietly accepted. Returns the
    list of texts embedded, for tests that assert on call counts.
    """
    embedded: list[str] = []

    async def _embed(texts: list[str]) -> list[list[float]]:
        embedded.extend(texts)
        return [deterministic_vector(text) for text in texts]

    monkeypatch.setattr(memory_service, "embed_texts", _embed)
    return embedded


@pytest.fixture
async def qdrant(monkeypatch, embeddings) -> AsyncQdrantClient:
    """A real Qdrant, in-process, wired into ``memory_service``.

    ``:memory:`` runs qdrant-client's local implementation — no server, no
    docker, and no file lock (a disk path would take one via portalocker). Each
    client is fully isolated from every other, so tests cannot leak into one
    another through it.
    """
    client = AsyncQdrantClient(":memory:")
    monkeypatch.setattr(memory_service, "get_qdrant_client", lambda: client)
    monkeypatch.setattr(settings, "embedding_dim", TEST_EMBEDDING_DIM)
    yield client
    await client.close()


# --- Real servers (integration marker) --------------------------------------
#
# Ports default to the compose file's, which are deliberately offset: a native
# mongod bound to loopback beats Docker's wildcard bind, so Maestro publishes
# Mongo on 27018 rather than 27017. Never default to the stock port here.

INTEGRATION_MONGO_URL = os.environ.get("MONGODB_URL", "mongodb://localhost:27018")
INTEGRATION_QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")

# Long enough for a loaded CI runner, short enough that an absent server skips
# promptly. The app's own client passes no timeout at all, so it would inherit
# pymongo's 30-second default and stall the run instead.
_INTEGRATION_TIMEOUT_MS = 1500


def _skip_or_fail(reason: str) -> None:
    """An absent server skips locally but fails in CI.

    Skipping is right on a laptop: `pytest -m integration` without
    `docker compose up` should say what is missing, not fail a change that is
    fine. In CI the same skip is the worst outcome available — the job reports
    green having asserted nothing, which is precisely the failure mode this
    whole tier exists to remove — so the workflow sets the variable.
    """
    if os.environ.get("REQUIRE_INTEGRATION_SERVERS"):
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture
async def mongo_db(monkeypatch):
    """A throwaway database on a real MongoDB server, wired into the app.

    The seam is ``database._mongo_client``, not each service's accessor:
    ``get_mongo_db()`` reads that global at call time, so one patch redirects
    every consumer at once — task_service, document_service, custom_api_service
    and ``ensure_indexes`` included. Without it a service would quietly build
    its own client against ``settings.mongodb_url``, which is a developer's real
    ``maestro`` database, using pymongo's 30-second selection default.
    """
    client = AsyncIOMotorClient(
        INTEGRATION_MONGO_URL,
        tz_aware=True,
        serverSelectionTimeoutMS=_INTEGRATION_TIMEOUT_MS,
    )
    try:
        await client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001 - any failure means "not available"
        client.close()
        _skip_or_fail(f"No MongoDB at {INTEGRATION_MONGO_URL}: {exc}")
    # A unique name per test: repeated and concurrent runs must not collide, and
    # a dropped database leaves a developer's instance as it was found.
    name = f"maestro_test_{uuid.uuid4().hex}"
    monkeypatch.setattr(database, "_mongo_client", client)
    monkeypatch.setattr(settings, "mongodb_db_name", name)
    try:
        yield client[name]
    finally:
        await client.drop_database(name)
        client.close()


class QdrantScratch:
    """A real Qdrant client plus the scratch collections this test may use."""

    def __init__(
        self, client: AsyncQdrantClient, memories: str, documents: str
    ) -> None:
        self.client = client
        self.memories = memories
        self.documents = documents


@pytest.fixture
async def qdrant_server(monkeypatch, embeddings):
    """The same round-trips as ``qdrant``, against a real Qdrant over HTTP.

    Writes go to per-test scratch collections, never the production names: an
    integration run must not disturb the ``conversation_memories`` a developer
    keeps in their local instance, and two runs must not collide.

    Redirecting them takes both halves. ``memory_service`` reads the two
    collection constants as module globals *inside* function bodies
    (``add_document_chunks``, ``purge_user_vectors``), so monkeypatching the
    module attribute reaches those at call time. It does NOT reach the
    ``collection=`` default parameters, which Python bound at definition time —
    so tests calling ``add_memory``/``retrieve_memories`` pass
    ``collection=scratch.memories`` explicitly.
    """
    client = AsyncQdrantClient(url=INTEGRATION_QDRANT_URL, timeout=5)
    try:
        await client.get_collections()
    except Exception as exc:  # noqa: BLE001 - any failure means "not available"
        await client.close()
        _skip_or_fail(f"No Qdrant at {INTEGRATION_QDRANT_URL}: {exc}")

    suffix = uuid.uuid4().hex
    memories = f"maestro_test_memories_{suffix}"
    documents = f"maestro_test_documents_{suffix}"
    monkeypatch.setattr(memory_service, "get_qdrant_client", lambda: client)
    monkeypatch.setattr(settings, "embedding_dim", TEST_EMBEDDING_DIM)
    monkeypatch.setattr(memory_service, "QDRANT_CONVERSATION_MEMORIES", memories)
    monkeypatch.setattr(memory_service, "QDRANT_DOCUMENT_CHUNKS", documents)
    try:
        yield QdrantScratch(client, memories, documents)
    finally:
        for name in (memories, documents):
            if await client.collection_exists(name):
                await client.delete_collection(name)
        await client.close()
