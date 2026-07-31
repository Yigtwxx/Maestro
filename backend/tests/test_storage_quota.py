"""Storage quotas: what an account may *keep*, as opposed to what it spends.

The token quota bounds a billing period and the concurrency cap bounds a
moment; neither says anything about the disk and Qdrant RAM an account holds
forever. Before these caps a user could upload unbounded 5 MB documents, own
unbounded custom agents, and accumulate one conversation memory per completed
task with nothing ever removing them.

Each of the three has a different shape, and that is what these tests pin:
documents are per-plan and refused at the gate, agents are a flat ceiling at the
single insert point, and memories are a ring buffer -- the newest write always
lands and the oldest is dropped.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.core.constants import (
    CUSTOM_AGENTS_MAX,
    PLAN_MAX_DOCUMENT_BYTES,
    PLAN_MAX_DOCUMENTS,
    QDRANT_CONVERSATION_MEMORIES,
    SubscriptionPlan,
    UserRole,
)
from app.models import User
from app.schemas.agent import AgentConfigCreate
from app.services import (
    agent_service,
    document_service,
    memory_service,
    quota_service,
)
from app.services.agent_service import AgentValidationError
from tests.conftest import FakeMongoCollection

ALICE = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOB = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

FREE_MAX_DOCUMENTS = PLAN_MAX_DOCUMENTS[SubscriptionPlan.FREE.value]
FREE_MAX_BYTES = PLAN_MAX_DOCUMENT_BYTES[SubscriptionPlan.FREE.value]


@pytest.fixture
def documents_db(monkeypatch) -> FakeMongoCollection:
    """Point ``document_service`` at an in-memory metadata collection."""
    collection = FakeMongoCollection()
    monkeypatch.setattr(document_service, "_collection", lambda: collection)
    return collection


@pytest.fixture
def agents_db(monkeypatch) -> FakeMongoCollection:
    """Point ``agent_service`` at an in-memory configuration collection."""
    collection = FakeMongoCollection()
    monkeypatch.setattr(agent_service, "_collection", lambda: collection)
    return collection


async def _make_user(db_session, email: str, *, role: UserRole = UserRole.USER) -> User:
    user = User(email=email, hashed_password="x", role=role.value)
    db_session.add(user)
    await db_session.commit()
    return user


def _stored(user_id: uuid.UUID, *, size_bytes: int) -> dict:
    """A document row as ``ingest`` writes it."""
    return {
        "id": str(uuid.uuid4()),
        "user_id": str(user_id),
        "filename": "note.md",
        "chunk_count": 1,
        "size_bytes": size_bytes,
    }


# --- Plan table ------------------------------------------------------------


def test_every_plan_declares_a_storage_allowance() -> None:
    """A plan missing from either map would KeyError on upload, not default."""
    plans = {plan.value for plan in SubscriptionPlan}
    assert set(PLAN_MAX_DOCUMENTS) == plans
    assert set(PLAN_MAX_DOCUMENT_BYTES) == plans
    assert all(limit >= 1 for limit in PLAN_MAX_DOCUMENTS.values()), (
        "A zero ceiling would refuse a brand-new account's first upload"
    )


def test_storage_allowances_grow_with_price() -> None:
    """A dearer plan that stored less would be a pricing bug, not a cap."""
    ladder = [
        SubscriptionPlan.FREE.value,
        SubscriptionPlan.STARTER.value,
        SubscriptionPlan.PRO.value,
        SubscriptionPlan.SCALE.value,
    ]
    counts = [PLAN_MAX_DOCUMENTS[plan] for plan in ladder]
    sizes = [PLAN_MAX_DOCUMENT_BYTES[plan] for plan in ladder]
    assert counts == sorted(counts), counts
    assert sizes == sorted(sizes), sizes


# --- Usage accounting ------------------------------------------------------


async def test_storage_usage_sums_only_the_owner(documents_db) -> None:
    documents_db.docs.extend(
        [
            _stored(ALICE, size_bytes=100),
            _stored(ALICE, size_bytes=250),
            _stored(BOB, size_bytes=9_000),
        ]
    )

    usage = await document_service.storage_usage(ALICE)

    assert usage.documents == 2, "another user's uploads must not be billed here"
    assert usage.bytes == 350


async def test_storage_usage_tolerates_rows_written_before_the_cap(
    documents_db,
) -> None:
    """A legacy row has no ``size_bytes``; it must not crash or count as huge."""
    legacy = _stored(ALICE, size_bytes=0)
    del legacy["size_bytes"]
    documents_db.docs.append(legacy)

    usage = await document_service.storage_usage(ALICE)

    assert usage.documents == 1, "it still occupies a slot against the count cap"
    assert usage.bytes == 0


async def test_ingest_records_the_upload_size(qdrant, documents_db) -> None:
    """Without this the byte cap has nothing to sum."""
    body = b"# Notes\n\nThe travel policy allows economy fares."

    document = await document_service.ingest(ALICE, "notes.md", body)

    assert document["size_bytes"] == len(body)
    assert documents_db.docs[0]["size_bytes"] == len(body)


# --- The upload gate -------------------------------------------------------


async def test_upload_is_refused_at_the_document_count(
    db_session, documents_db
) -> None:
    user = await _make_user(db_session, "count@storage.example.com")
    documents_db.docs.extend(
        _stored(user.id, size_bytes=1) for _ in range(FREE_MAX_DOCUMENTS)
    )

    with pytest.raises(HTTPException) as excinfo:
        await quota_service.enforce_can_upload_document(
            db_session, user, incoming_bytes=1
        )

    assert excinfo.value.status_code == 402
    assert str(FREE_MAX_DOCUMENTS) in excinfo.value.detail


async def test_upload_is_refused_when_it_would_cross_the_byte_cap(
    db_session, documents_db
) -> None:
    """The check is on the *sum*, not on the incoming file alone."""
    user = await _make_user(db_session, "bytes@storage.example.com")
    documents_db.docs.append(_stored(user.id, size_bytes=FREE_MAX_BYTES - 10))

    with pytest.raises(HTTPException) as excinfo:
        await quota_service.enforce_can_upload_document(
            db_session, user, incoming_bytes=11
        )

    assert excinfo.value.status_code == 402
    await quota_service.enforce_can_upload_document(db_session, user, incoming_bytes=10)


async def test_a_user_under_both_ceilings_may_upload(db_session, documents_db) -> None:
    user = await _make_user(db_session, "ok@storage.example.com")
    documents_db.docs.append(_stored(user.id, size_bytes=1_000))

    await quota_service.enforce_can_upload_document(
        db_session, user, incoming_bytes=1_000
    )


async def test_one_users_documents_do_not_fill_anothers_quota(
    db_session, documents_db
) -> None:
    owner = await _make_user(db_session, "owner@storage.example.com")
    other = await _make_user(db_session, "other@storage.example.com")
    documents_db.docs.extend(
        _stored(owner.id, size_bytes=1) for _ in range(FREE_MAX_DOCUMENTS)
    )

    await quota_service.enforce_can_upload_document(db_session, other, incoming_bytes=1)


async def test_admins_are_unmetered_for_storage(db_session, documents_db) -> None:
    """As they are for tokens and concurrency: the operator must be able to test."""
    admin = await _make_user(
        db_session, "admin@storage.example.com", role=UserRole.ADMIN
    )
    documents_db.docs.extend(
        _stored(admin.id, size_bytes=FREE_MAX_BYTES)
        for _ in range(FREE_MAX_DOCUMENTS + 5)
    )

    await quota_service.enforce_can_upload_document(
        db_session, admin, incoming_bytes=FREE_MAX_BYTES
    )

    snapshot = await quota_service.get_storage_snapshot(db_session, admin)
    assert snapshot.max_documents is None, "None means no ceiling, never zero"
    assert snapshot.max_bytes is None


async def test_snapshot_reports_usage_against_the_plan(
    db_session, documents_db
) -> None:
    user = await _make_user(db_session, "snapshot@storage.example.com")
    documents_db.docs.append(_stored(user.id, size_bytes=4_096))

    snapshot = await quota_service.get_storage_snapshot(db_session, user)

    assert snapshot.documents == 1
    assert snapshot.bytes == 4_096
    assert snapshot.max_documents == FREE_MAX_DOCUMENTS
    assert snapshot.max_bytes == FREE_MAX_BYTES


async def test_upload_route_reports_the_ceiling(client, documents_db) -> None:
    """End to end: the cap has to reach the user as a 402, not a 500."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "route@storage.example.com", "password": "password123"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "route@storage.example.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    usage = await client.get("/api/v1/documents/storage", headers=headers)
    assert usage.status_code == 200
    assert usage.json()["max_documents"] == FREE_MAX_DOCUMENTS

    me = await client.get("/api/v1/users/me", headers=headers)
    documents_db.docs.extend(
        _stored(uuid.UUID(me.json()["id"]), size_bytes=1)
        for _ in range(FREE_MAX_DOCUMENTS)
    )
    refused = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("note.md", b"hello", "text/markdown")},
    )

    assert refused.status_code == 402, refused.text
    assert str(FREE_MAX_DOCUMENTS) in refused.json()["detail"]
    assert len(documents_db.docs) == FREE_MAX_DOCUMENTS, (
        "A refused upload must leave no metadata row behind"
    )


# --- Custom agents ---------------------------------------------------------


def _agent_payload(index: int) -> AgentConfigCreate:
    return AgentConfigCreate(
        name=f"Agent {index}",
        domain="general",
        system_prompt="Be a helpful specialist.",
        description="d",
    )


async def test_custom_agents_are_capped_per_account(agents_db) -> None:
    for index in range(CUSTOM_AGENTS_MAX):
        await agent_service.create_agent(ALICE, _agent_payload(index))

    with pytest.raises(AgentValidationError) as excinfo:
        await agent_service.create_agent(ALICE, _agent_payload(CUSTOM_AGENTS_MAX))

    assert str(CUSTOM_AGENTS_MAX) in str(excinfo.value)
    assert len(agents_db.docs) == CUSTOM_AGENTS_MAX


async def test_the_agent_cap_is_per_owner(agents_db) -> None:
    for index in range(CUSTOM_AGENTS_MAX):
        await agent_service.create_agent(ALICE, _agent_payload(index))

    await agent_service.create_agent(BOB, _agent_payload(0))

    assert len(agents_db.docs) == CUSTOM_AGENTS_MAX + 1


async def test_marketplace_installs_count_against_the_same_cap(agents_db) -> None:
    """A one-click install must not be the way around the wizard's ceiling."""
    for index in range(CUSTOM_AGENTS_MAX):
        await agent_service.create_agent(ALICE, _agent_payload(index))

    with pytest.raises(AgentValidationError):
        await agent_service.create_agent(
            ALICE,
            _agent_payload(CUSTOM_AGENTS_MAX),
            source="marketplace",
            marketplace_item_id="item1",
        )


def test_the_agent_cap_leaves_room_beyond_the_routing_catalog() -> None:
    """Non-routable specialists exist; the cap must not be the routing bound."""
    from app.core.constants import ROUTING_CUSTOM_AGENTS_MAX

    assert CUSTOM_AGENTS_MAX > ROUTING_CUSTOM_AGENTS_MAX


# --- Conversation memories -------------------------------------------------


async def _memory_count(qdrant, user_id: uuid.UUID) -> int:
    result = await qdrant.count(
        collection_name=QDRANT_CONVERSATION_MEMORIES,
        count_filter=memory_service._user_filter(user_id),
        exact=True,
    )
    return result.count


async def test_memories_are_trimmed_to_the_cap(qdrant, monkeypatch) -> None:
    monkeypatch.setattr(memory_service, "MEMORY_MAX_POINTS_PER_USER", 3)

    for index in range(6):
        await memory_service.add_memory(ALICE, f"memory {index}")

    assert await _memory_count(qdrant, ALICE) == 3


async def test_the_newest_memory_survives_the_trim(qdrant, monkeypatch) -> None:
    """A cap that dropped the write it was triggered by would be useless."""
    monkeypatch.setattr(memory_service, "MEMORY_MAX_POINTS_PER_USER", 2)

    for index in range(5):
        await memory_service.add_memory(ALICE, f"memory {index}")

    hits = await memory_service.retrieve_memories(ALICE, "memory 4", limit=10)
    assert "memory 4" in hits, hits
    assert "memory 0" not in hits, "the oldest must be the one that goes"


async def test_trimming_is_scoped_to_one_user(qdrant, monkeypatch) -> None:
    monkeypatch.setattr(memory_service, "MEMORY_MAX_POINTS_PER_USER", 2)

    for index in range(4):
        await memory_service.add_memory(ALICE, f"alice {index}")
    await memory_service.add_memory(BOB, "bob 0")

    assert await _memory_count(qdrant, ALICE) == 2
    assert await _memory_count(qdrant, BOB) == 1, (
        "One user's overflow must never evict another's memories"
    )


async def test_document_chunks_are_not_trimmed_by_the_memory_cap(
    qdrant, documents_db, monkeypatch
) -> None:
    """Chunks are bounded by the byte quota; the ring buffer must not touch them."""
    monkeypatch.setattr(memory_service, "MEMORY_MAX_POINTS_PER_USER", 1)
    long_text = ("The travel policy allows economy fares. " * 200).encode()

    document = await document_service.ingest(ALICE, "handbook.md", long_text)

    assert document["chunk_count"] > 1
    result = await qdrant.count(
        collection_name="document_chunks",
        count_filter=memory_service._user_filter(ALICE),
        exact=True,
    )
    assert result.count == document["chunk_count"]
