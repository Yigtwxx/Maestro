"""Tests for MongoDB index/TTL setup (Mongo mocked; no live database)."""

from __future__ import annotations

from collections import defaultdict
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import OperationFailure

from app.core import database
from app.core.config import settings

_SECONDS_PER_DAY = 86_400


class _FakeCollection:
    def __init__(self) -> None:
        self.create_index = AsyncMock()
        self.drop_index = AsyncMock()


class _FakeDb:
    def __init__(self) -> None:
        self._collections: dict[str, _FakeCollection] = defaultdict(_FakeCollection)
        self.command = AsyncMock()

    def __getitem__(self, name: str) -> _FakeCollection:
        return self._collections[name]


def _ttl_calls(collection: _FakeCollection) -> list:
    """create_index calls that carry an expireAfterSeconds option."""
    return [
        call
        for call in collection.create_index.call_args_list
        if "expireAfterSeconds" in call.kwargs
    ]


@pytest.fixture
def fake_db(monkeypatch) -> _FakeDb:
    db = _FakeDb()
    monkeypatch.setattr(database, "get_mongo_db", lambda: db)
    return db


async def test_ensure_indexes_creates_ttl_from_retention_setting(fake_db):
    await database.ensure_indexes()

    expected = settings.task_retention_days * _SECONDS_PER_DAY
    for collection_name in ("task_sessions", "agent_logs"):
        calls = _ttl_calls(fake_db[collection_name])
        assert len(calls) == 1, f"{collection_name}: {calls}"
        assert calls[0].args[0] == "created_at", calls[0]
        assert calls[0].kwargs["expireAfterSeconds"] == expected, calls[0]


async def test_ensure_indexes_creates_owner_recency_index(fake_db):
    await database.ensure_indexes()

    keys = [c.args[0] for c in fake_db["task_sessions"].create_index.call_args_list]
    assert [("user_id", 1), ("created_at", -1)] in keys, keys
    assert [("task_id", 1)] in keys, keys


async def test_ensure_indexes_retunes_ttl_via_collmod_on_conflict(fake_db):
    def _conflict_on_ttl(*args, **kwargs):
        if "expireAfterSeconds" in kwargs:
            raise OperationFailure("index options conflict", 85)

    for name in ("task_sessions", "agent_logs"):
        fake_db[name].create_index.side_effect = _conflict_on_ttl

    await database.ensure_indexes()

    expected = settings.task_retention_days * _SECONDS_PER_DAY
    assert fake_db.command.await_count == 2, fake_db.command.call_args_list
    command = fake_db.command.call_args_list[0].args[0]
    assert command["index"]["expireAfterSeconds"] == expected, command
    assert command["index"]["name"] == "ttl_created_at", command
    # collMod succeeded, so the index is never dropped.
    assert fake_db["task_sessions"].drop_index.await_count == 0


async def test_ensure_indexes_recreates_ttl_when_collmod_fails(fake_db):
    def _conflict_on_ttl(*args, **kwargs):
        if "expireAfterSeconds" in kwargs and fake_db.command.await_count == 0:
            raise OperationFailure("index options conflict", 85)

    fake_db["task_sessions"].create_index.side_effect = _conflict_on_ttl
    fake_db.command.side_effect = OperationFailure("collMod unsupported", 59)

    await database.ensure_indexes()

    assert fake_db["task_sessions"].drop_index.await_count == 1
    fake_db["task_sessions"].drop_index.assert_awaited_with("ttl_created_at")


async def test_ensure_indexes_never_raises_when_mongo_is_down(monkeypatch):
    def _boom() -> None:
        raise RuntimeError("mongo unreachable")

    monkeypatch.setattr(database, "get_mongo_db", _boom)

    await database.ensure_indexes()  # must not raise: the API still has to boot


async def test_ensure_indexes_survives_a_failing_index(fake_db):
    fake_db["task_sessions"].create_index.side_effect = RuntimeError("no permission")

    await database.ensure_indexes()  # logged, swallowed

    # agent_logs is a separate collection and still gets its TTL.
    assert len(_ttl_calls(fake_db["agent_logs"])) == 1
