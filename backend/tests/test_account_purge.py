"""Cross-store account erasure: purge_user_data and the purge sweep.

MongoDB and Qdrant are never real in the suite (see conftest), so both are
replaced with in-memory doubles that record what the purge asked them to do.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.core.constants import (
    ACCOUNT_DELETION_GRACE_DAYS,
    MARKETPLACE_COMMUNITY_AUTHOR,
    QDRANT_CONVERSATION_MEMORIES,
    QDRANT_DOCUMENT_CHUNKS,
    EventType,
    MongoCollection,
)
from app.models.user import User
from app.scripts.purge_deleted_accounts import purge_due_accounts
from app.services import memory_service, user_service

_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_OTHER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_TASK_ID = "task-abc"


# --- Minimal Mongo double -----------------------------------------------------


def _matches(document: dict[str, Any], criteria: dict[str, Any]) -> bool:
    """Support the subset of query operators the purge actually uses."""
    for key, expected in criteria.items():
        if key == "$or":
            if not any(_matches(document, sub) for sub in expected):
                return False
        elif isinstance(expected, dict) and "$in" in expected:
            if document.get(key) not in expected["$in"]:
                return False
        elif document.get(key) != expected:
            return False
    return True


class FakeCollection:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents

    async def distinct(self, field: str, criteria: dict[str, Any]) -> list[Any]:
        return sorted({doc[field] for doc in self.documents if _matches(doc, criteria)})

    async def delete_many(self, criteria: dict[str, Any]) -> None:
        self.documents[:] = [
            doc for doc in self.documents if not _matches(doc, criteria)
        ]

    async def update_many(
        self, criteria: dict[str, Any], update: dict[str, Any]
    ) -> None:
        for doc in self.documents:
            if not _matches(doc, criteria):
                continue
            for field in update.get("$unset", {}):
                doc.pop(field, None)
            doc.update(update.get("$set", {}))


class FakeMongo:
    def __init__(self, collections: dict[str, list[dict[str, Any]]]) -> None:
        self._collections = {
            name: FakeCollection(docs) for name, docs in collections.items()
        }

    def __getitem__(self, name: str) -> FakeCollection:
        return self._collections.setdefault(name, FakeCollection([]))

    def documents(self, collection: MongoCollection) -> list[dict[str, Any]]:
        return self[collection.value].documents


class FakeQdrant:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, *, collection_name: str, points_selector: Any) -> None:
        self.deleted.append(collection_name)


class BrokenQdrant:
    async def delete(self, *, collection_name: str, points_selector: Any) -> None:
        raise ConnectionError("qdrant unreachable")


def _seed_mongo() -> FakeMongo:
    """One user's data across every collection, plus a bystander's."""
    return FakeMongo(
        {
            MongoCollection.TASK_SESSIONS.value: [
                {"task_id": _TASK_ID, "user_id": str(_USER_ID)},
                {"task_id": "task-other", "user_id": str(_OTHER_ID)},
            ],
            MongoCollection.AGENT_LOGS.value: [
                # Written before the write path stamped `user_id`: only reachable
                # through the owner's task sessions.
                {"task_id": _TASK_ID, "type": "legacy_event"},
                {"task_id": _TASK_ID, "user_id": str(_USER_ID), "type": "new_event"},
                {"task_id": "task-other", "user_id": str(_OTHER_ID)},
            ],
            MongoCollection.AGENT_CONFIGURATIONS.value: [
                {"id": "a1", "user_id": str(_USER_ID)},
                {"id": "a2", "user_id": str(_OTHER_ID)},
            ],
            MongoCollection.DOCUMENTS.value: [
                {"id": "d1", "user_id": str(_USER_ID)},
            ],
            MongoCollection.MARKETPLACE_ITEMS.value: [
                {"id": "m1", "author_id": str(_USER_ID), "author_label": "whoever"},
                {"id": "m2", "author_id": str(_OTHER_ID), "author_label": "whoever"},
            ],
        }
    )


@pytest.fixture
def stores(monkeypatch):
    """Wire the purge path to in-memory Mongo + Qdrant doubles."""
    mongo = _seed_mongo()
    qdrant = FakeQdrant()
    monkeypatch.setattr(user_service, "get_mongo_db", lambda: mongo)
    monkeypatch.setattr(memory_service, "get_qdrant_client", lambda: qdrant)
    return mongo, qdrant


async def test_purge_deletes_agent_logs_including_rows_without_user_id(stores):
    mongo, _ = stores
    await user_service.purge_user_data(_USER_ID)

    remaining = mongo.documents(MongoCollection.AGENT_LOGS)
    assert remaining == [{"task_id": "task-other", "user_id": str(_OTHER_ID)}], (
        f"Both the legacy and the stamped log must go, got {remaining}"
    )


async def test_purge_clears_every_user_scoped_collection(stores):
    mongo, _ = stores
    await user_service.purge_user_data(_USER_ID)

    for collection in (
        MongoCollection.TASK_SESSIONS,
        MongoCollection.AGENT_CONFIGURATIONS,
        MongoCollection.DOCUMENTS,
    ):
        owners = [doc.get("user_id") for doc in mongo.documents(collection)]
        assert str(_USER_ID) not in owners, f"{collection.value} still holds the user"


async def test_purge_leaves_other_users_data_untouched(stores):
    mongo, _ = stores
    await user_service.purge_user_data(_USER_ID)

    sessions = mongo.documents(MongoCollection.TASK_SESSIONS)
    assert sessions == [{"task_id": "task-other", "user_id": str(_OTHER_ID)}]


async def test_purge_anonymizes_marketplace_items_instead_of_deleting_them(stores):
    mongo, _ = stores
    await user_service.purge_user_data(_USER_ID)

    published = mongo.documents(MongoCollection.MARKETPLACE_ITEMS)
    items = {doc["id"]: doc for doc in published}
    assert set(items) == {"m1", "m2"}, "Published items must survive their author"
    assert "author_id" not in items["m1"], "The identifying link must be severed"
    assert items["m1"]["author_label"] == MARKETPLACE_COMMUNITY_AUTHOR
    assert items["m2"]["author_id"] == str(_OTHER_ID), "Bystander item untouched"


async def test_purge_deletes_vectors_from_both_qdrant_collections(stores):
    _, qdrant = stores
    await user_service.purge_user_data(_USER_ID)

    assert sorted(qdrant.deleted) == sorted(
        [QDRANT_CONVERSATION_MEMORIES, QDRANT_DOCUMENT_CHUNKS]
    ), f"Expected both collections purged, got {qdrant.deleted}"


async def test_purge_raises_when_a_store_is_unreachable(monkeypatch):
    monkeypatch.setattr(user_service, "get_mongo_db", _seed_mongo)
    monkeypatch.setattr(memory_service, "get_qdrant_client", BrokenQdrant)

    with pytest.raises(ConnectionError):
        await user_service.purge_user_data(_USER_ID)


# --- The sweep ----------------------------------------------------------------


async def _make_user(db, email: str, requested_days_ago: int | None) -> uuid.UUID:  # noqa: ANN001
    requested_at = (
        None
        if requested_days_ago is None
        else datetime.now(UTC) - timedelta(days=requested_days_ago)
    )
    user = User(
        email=email,
        hashed_password="x",
        deletion_requested_at=requested_at,
    )
    db.add(user)
    await db.commit()
    return user.id


async def _emails(db) -> set[str]:  # noqa: ANN001
    return set((await db.scalars(select(User.email))).all())


async def test_sweep_purges_only_accounts_past_the_grace_period(
    db_session, monkeypatch
):
    purged: list[uuid.UUID] = []

    async def fake_purge(user_id: uuid.UUID) -> None:
        purged.append(user_id)

    monkeypatch.setattr(user_service, "purge_user_data", fake_purge)

    overdue = await _make_user(
        db_session, "overdue@x.com", ACCOUNT_DELETION_GRACE_DAYS + 1
    )
    await _make_user(db_session, "recent@x.com", 5)
    await _make_user(db_session, "active@x.com", None)

    count = await purge_due_accounts(db_session)

    assert count == 1, f"Expected exactly one purge, got {count}"
    assert purged == [overdue]
    assert await _emails(db_session) == {"recent@x.com", "active@x.com"}


async def test_agent_log_is_written_with_its_owner(monkeypatch):
    """Regression: logs used to carry only `task_id`, so the purge missed them."""
    from app.services import task_service

    logs = FakeCollection([])
    sessions = FakeCollection([])

    async def noop_update_one(*args: Any, **kwargs: Any) -> None:
        return None

    sessions.update_one = noop_update_one  # type: ignore[attr-defined]
    inserted: list[dict[str, Any]] = []

    async def insert_one(document: dict[str, Any]) -> None:
        inserted.append(document)

    logs.insert_one = insert_one  # type: ignore[attr-defined]
    monkeypatch.setattr(task_service, "_logs_collection", lambda: logs)
    monkeypatch.setattr(task_service, "_sessions_collection", lambda: sessions)

    emit = task_service._make_emit(_TASK_ID, _USER_ID)
    await emit(EventType.TASK_STARTED, {"prompt": "hi"})

    assert inserted[0]["user_id"] == str(_USER_ID), (
        f"Agent logs must record their owner, got {inserted[0]}"
    )
    assert inserted[0]["task_id"] == _TASK_ID


async def test_sweep_keeps_the_account_when_the_purge_fails(db_session, monkeypatch):
    async def failing_purge(user_id: uuid.UUID) -> None:
        raise ConnectionError("mongo unreachable")

    monkeypatch.setattr(user_service, "purge_user_data", failing_purge)

    await _make_user(db_session, "overdue@x.com", ACCOUNT_DELETION_GRACE_DAYS + 1)

    count = await purge_due_accounts(db_session)

    assert count == 0, "A failed purge must not be counted"
    survivor = await db_session.scalar(
        select(User).where(User.email == "overdue@x.com")
    )
    assert survivor is not None, "PostgreSQL row must outlive a failed purge"
    assert survivor.deletion_requested_at is not None, (
        "The flag must stay set so the next run retries"
    )
