"""Mongo-backed queries against a real MongoDB server.

The suite models Mongo with six independent hand-written doubles, each covering
the slice of the query language its own tests happen to use. conftest's, for
instance, raises ``NotImplementedError`` on any operator but ``$in`` and has no
``skip()`` at all — which is why ``test_task_list_api.py`` patches ``list_tasks``
wholesale rather than exercising it. A fake cannot fail the way a server does:
it accepts queries Mongo would reject, rejects queries Mongo would accept, and
never enforces an index or a projection it was not taught about.

These tests run the real service code paths against a real server, targeting
exactly the operators and behaviours the doubles cannot reach: ``$gt``, ``sort``,
``skip``/``limit``, ``count_documents``, field-exclusion projections, and index
creation including the TTL.

Deselected by default (see the ``integration`` marker in pyproject.toml); run
with ``docker compose up -d --wait mongo`` and ``pytest -m integration``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core import database
from app.core.constants import MongoCollection
from app.services import custom_api_service, document_service, task_service

pytestmark = pytest.mark.integration

ALICE = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOB = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def task_collections(mongo_db):
    """The scratch database's two task collections, for seeding.

    No monkeypatching needed: ``mongo_db`` already redirects the app's shared
    client, so ``task_service._sessions_collection()`` resolves to exactly these.
    """
    return (
        mongo_db[MongoCollection.TASK_SESSIONS.value],
        mongo_db[MongoCollection.AGENT_LOGS.value],
    )


def _session(task_id: str, user_id: uuid.UUID, *, created_at: datetime) -> dict:
    return {
        "task_id": task_id,
        "user_id": str(user_id),
        "status": "completed",
        "prompt": "summarise the quarterly numbers",
        "provider": "ollama",
        "reviewer_enabled": False,
        "domain": "finance",
        "result": None,
        "error": None,
        "events": [{"seq": 1, "type": "noise"}],
        "metadata": {},
        "created_at": created_at,
        "updated_at": created_at,
    }


async def test_ensure_indexes_creates_indexes_on_a_real_server(mongo_db):
    """Index creation is only ever exercised against a call-recording fake.

    A real server validates the key specs, enforces uniqueness, and rejects a
    TTL on a non-date field — none of which a recorder can do. ``ensure_indexes``
    swallows every failure by design, so without this the whole function could
    be silently failing on every boot and look identical to success.
    """
    await database.ensure_indexes()

    sessions = await mongo_db[MongoCollection.TASK_SESSIONS.value].index_information()
    assert any("task_id" in str(spec.get("key")) for spec in sessions.values()), (
        f"task_id lookups must be indexed, got {sessions}"
    )
    assert any("expireAfterSeconds" in spec for spec in sessions.values()), (
        f"The retention TTL must exist on task_sessions, got {sessions}"
    )
    logs = await mongo_db[MongoCollection.AGENT_LOGS.value].index_information()
    assert len(logs) > 1, f"agent_logs must carry indexes beyond _id, got {logs}"


async def test_ensure_indexes_is_idempotent(mongo_db):
    """It runs on every boot; a second call must not raise or duplicate."""
    await database.ensure_indexes()
    first = await mongo_db[MongoCollection.TASK_SESSIONS.value].index_information()
    await database.ensure_indexes()
    second = await mongo_db[MongoCollection.TASK_SESSIONS.value].index_information()

    assert set(first) == set(second), (
        f"A repeat run must not change the index set: {first} -> {second}"
    )


async def test_events_since_returns_only_later_events_in_seq_order(task_collections):
    """``$gt`` + ``sort`` + ``limit`` + an exclusion projection, all at once.

    conftest's double raises ``NotImplementedError`` on ``$gt``, so this resume
    cursor — the thing a reconnecting WebSocket client depends on — has never
    run against anything that implements it.
    """
    sessions, logs = task_collections
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    await sessions.insert_one(_session(task_id, ALICE, created_at=now))
    await logs.insert_many(
        [
            {
                "task_id": task_id,
                "user_id": str(ALICE),
                "created_at": now,
                "seq": seq,
                "type": "step",
            }
            for seq in (1, 2, 3, 4, 5)
        ]
    )

    events, last_seq = await task_service.events_since(task_id, ALICE, 2, limit=2)

    assert [event["seq"] for event in events] == [3, 4], (
        f"Only events after the cursor, in order, got {events}"
    )
    assert last_seq == 4, (
        f"The resume cursor must be the batch's highest seq, {last_seq}"
    )
    assert "user_id" not in events[0], f"Projection must drop user_id, got {events[0]}"
    assert "_id" not in events[0], f"Projection must drop _id, got {events[0]}"


async def test_events_since_for_a_non_owner_returns_nothing(task_collections):
    """Ownership is checked against the session doc before any log is read."""
    sessions, logs = task_collections
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    await sessions.insert_one(_session(task_id, ALICE, created_at=now))
    await logs.insert_one(
        {"task_id": task_id, "user_id": str(ALICE), "created_at": now, "seq": 1}
    )

    events, last_seq = await task_service.events_since(task_id, BOB, 0, limit=10)

    assert events == [], f"A non-owner must read no events, got {events}"
    assert last_seq == 0, last_seq


async def test_get_task_does_not_return_another_users_session(task_collections):
    sessions, _ = task_collections
    task_id = str(uuid.uuid4())
    await sessions.insert_one(_session(task_id, ALICE, created_at=datetime.now(UTC)))

    assert await task_service.get_task(task_id, BOB) is None, (
        "A session must never be readable by another account"
    )
    assert await task_service.get_task(task_id, ALICE) is not None, (
        "The owner must still be able to read it"
    )


async def test_list_tasks_paginates_newest_first_and_omits_events(task_collections):
    """``skip()`` does not exist on the in-memory cursor, so this path is untested.

    The ``events`` exclusion matters beyond correctness: a finished session's
    event array can be megabytes, and a projection that quietly stopped applying
    would only show up as a slow, memory-hungry history endpoint.
    """
    sessions, _ = task_collections
    base = datetime.now(UTC)
    for index in range(5):
        await sessions.insert_one(
            _session(f"task-{index}", ALICE, created_at=base + timedelta(minutes=index))
        )
    await sessions.insert_one(_session("bob-task", BOB, created_at=base))

    page, total = await task_service.list_tasks(ALICE, limit=2, offset=1)

    assert total == 5, f"The total must count only the owner's tasks, got {total}"
    assert [row["task_id"] for row in page] == ["task-3", "task-2"], (
        f"Newest first, offset by one, got {page}"
    )
    assert "events" not in page[0], f"list_tasks must never load events, got {page[0]}"


async def test_custom_api_tool_listing_hides_the_encrypted_secret(mongo_db):
    """The projection is the first of two defences over a stored credential.

    conftest's fake implements projections precisely because this assertion
    matters; running it against a real server is what proves the fake's version
    of the rule matches Mongo's.
    """
    collection = mongo_db[MongoCollection.CUSTOM_API_TOOLS.value]
    tool_id = str(uuid.uuid4())
    await collection.insert_one(
        {
            "id": tool_id,
            "user_id": str(ALICE),
            "slug": "weather",
            "name": "Weather",
            "encrypted_secret": "ciphertext-that-must-never-be-returned",
        }
    )

    listed = await custom_api_service.list_tools(ALICE)
    fetched = await custom_api_service.get_tool(ALICE, tool_id)

    assert len(listed) == 1, listed
    for doc in (listed[0], fetched):
        assert "encrypted_secret" not in doc, f"Secret must not be returned: {doc}"
        assert "user_id" not in doc, f"user_id must not be returned: {doc}"
    assert await custom_api_service.get_tool(BOB, tool_id) is None, (
        "A tool must not be readable by another account"
    )


async def test_document_metadata_round_trip_is_owner_scoped(mongo_db):
    """``list_documents`` sorts on a real BSON date, not a Python comparison."""
    collection = mongo_db[MongoCollection.DOCUMENTS.value]
    base = datetime.now(UTC)
    await collection.insert_many(
        [
            {
                "id": "older",
                "user_id": str(ALICE),
                "filename": "older.txt",
                "chunk_count": 1,
                "created_at": base,
            },
            {
                "id": "newer",
                "user_id": str(ALICE),
                "filename": "newer.txt",
                "chunk_count": 1,
                "created_at": base + timedelta(minutes=1),
            },
            {
                "id": "bobs",
                "user_id": str(BOB),
                "filename": "bobs.txt",
                "chunk_count": 1,
                "created_at": base,
            },
        ]
    )

    listed = await document_service.list_documents(ALICE)

    assert [doc["id"] for doc in listed] == ["newer", "older"], (
        f"Newest first, owner only, got {listed}"
    )
    assert all("_id" not in doc for doc in listed), (
        f"_id must be projected out: {listed}"
    )
