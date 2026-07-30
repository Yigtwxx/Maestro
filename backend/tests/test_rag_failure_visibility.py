"""A degraded RAG backend must be visible to the operator.

Every RAG path is best-effort by design (CLAUDE.md §8: a cold Qdrant degrades to
"no results", never an error), and that stays true here — these tests assert the
degradation still happens. What they add is the other half: a failure must leave
a WARNING with a traceback behind, because an empty result is otherwise
indistinguishable from a user who genuinely has no stored data. A misconfigured
``EMBEDDING_ENDPOINT`` or an unreachable Qdrant would silently disable RAG for
every user with nothing in the logs and nothing failing in CI.

WARNING, not ERROR, on purpose: Sentry's ``LoggingIntegration`` captures at
ERROR, and a Qdrant outage would otherwise fire one event per retrieval.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import pytest

from app.core.constants import QDRANT_CONVERSATION_MEMORIES, QDRANT_DOCUMENT_CHUNKS
from app.services import memory_service, task_service

USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
VECTOR = [0.1, 0.2, 0.3]

MEMORY_LOGGER = "app.services.memory_service"
TASK_LOGGER = "app.services.task_service"


class FakeHit:
    def __init__(self, text: str) -> None:
        self.payload = {"text": text}


class FakeResponse:
    """What ``query_points`` returns: hits live under ``.points``."""

    def __init__(self, points: list[FakeHit]) -> None:
        self.points = points


class FakeQdrant:
    """A reachable Qdrant. Each operation can be told to raise instead.

    Mirrors the real client's method *names*: these tests assert that a failure
    is logged, and a fake carrying a method the client no longer has would make
    "the method is gone" indistinguishable from "the backend is down". The
    round-trip coverage against a real client lives in test_qdrant_roundtrip.py.
    """

    def __init__(self, *, hits: list[str] | None = None, fails: str = "") -> None:
        self._hits = hits or []
        self._fails = fails

    def _maybe_fail(self, op: str) -> None:
        if self._fails == op:
            raise ConnectionError(f"qdrant {op} unreachable")

    async def collection_exists(self, name: str) -> bool:
        return True

    async def query_points(self, **_: Any) -> FakeResponse:
        self._maybe_fail("search")
        return FakeResponse([FakeHit(text) for text in self._hits])

    async def scroll(self, **_: Any) -> tuple[list[Any], None]:
        self._maybe_fail("scroll")
        return [], None

    async def delete(self, **_: Any) -> None:
        self._maybe_fail("delete")

    async def upsert(self, **_: Any) -> None:
        self._maybe_fail("upsert")


@pytest.fixture
def warnings(caplog):
    """Capture both services at WARNING and above.

    Yields ``caplog`` rather than ``caplog.records``: that list is rebuilt per
    test phase, so a list grabbed during setup never sees the call-phase records.
    """
    caplog.set_level(logging.WARNING, logger=MEMORY_LOGGER)
    caplog.set_level(logging.WARNING, logger=TASK_LOGGER)
    return caplog


def _use_qdrant(monkeypatch, client: FakeQdrant) -> None:
    monkeypatch.setattr(memory_service, "get_qdrant_client", lambda: client)


def _embeds_ok(monkeypatch) -> None:
    async def fake_embed(texts: list[str]) -> list[list[float]]:
        return [VECTOR for _ in texts]

    monkeypatch.setattr(memory_service, "embed_texts", fake_embed)


def _embeds_broken(monkeypatch) -> None:
    async def fake_embed(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding endpoint returned 401")

    monkeypatch.setattr(memory_service, "embed_texts", fake_embed)


def _only(records: list[logging.LogRecord]) -> logging.LogRecord:
    assert len(records) == 1, f"Expected exactly one warning, got {records}"
    return records[0]


async def test_retrieve_memories_broken_embedding_logs_warning(monkeypatch, warnings):
    _use_qdrant(monkeypatch, FakeQdrant())
    _embeds_broken(monkeypatch)

    hits = await memory_service.retrieve_memories(USER_ID, "anything")

    assert hits == [], f"Expected graceful degradation, got {hits}"
    record = _only(warnings.records)
    assert "embedding" in record.message, record.message
    assert record.exc_info is not None, "Traceback must survive into the log"
    assert record.user_id == str(USER_ID), record.__dict__


async def test_retrieve_memories_broken_search_logs_warning(monkeypatch, warnings):
    _use_qdrant(monkeypatch, FakeQdrant(fails="search"))
    _embeds_ok(monkeypatch)

    hits = await memory_service.retrieve_memories(
        USER_ID, "anything", collection=QDRANT_DOCUMENT_CHUNKS
    )

    assert hits == [], f"Expected graceful degradation, got {hits}"
    record = _only(warnings.records)
    assert "search" in record.message, record.message
    assert record.exc_info is not None, "Traceback must survive into the log"
    assert record.collection == QDRANT_DOCUMENT_CHUNKS, record.__dict__


async def test_retrieve_memories_genuine_no_match_logs_nothing(monkeypatch, warnings):
    """The regression guard: no-data must stay distinguishable from broken."""
    _use_qdrant(monkeypatch, FakeQdrant(hits=[]))
    _embeds_ok(monkeypatch)

    hits = await memory_service.retrieve_memories(USER_ID, "anything")

    assert hits == [], f"Expected no hits, got {hits}"
    assert warnings.records == [], (
        f"An empty search is not a failure, got {warnings.records}"
    )


async def test_retrieve_memories_reused_vector_skips_embedding(monkeypatch, warnings):
    """A caller-supplied vector must not re-embed, so a broken embedder is moot."""
    _use_qdrant(monkeypatch, FakeQdrant(hits=["stored snippet"]))
    _embeds_broken(monkeypatch)

    hits = await memory_service.retrieve_memories(
        USER_ID, "anything", query_vector=VECTOR
    )

    assert hits == ["stored snippet"], hits
    assert warnings.records == [], f"Nothing failed, got {warnings.records}"


async def test_export_user_texts_broken_backend_logs_warning(monkeypatch, warnings):
    _use_qdrant(monkeypatch, FakeQdrant(fails="scroll"))

    texts = await memory_service.export_user_texts(
        USER_ID, QDRANT_CONVERSATION_MEMORIES
    )

    assert texts == [], f"Export must degrade, not raise, got {texts}"
    record = _only(warnings.records)
    assert "export" in record.message, record.message
    assert record.exc_info is not None, "Traceback must survive into the log"


async def test_delete_document_chunks_failure_logs_orphaned_vectors(
    monkeypatch, warnings
):
    _use_qdrant(monkeypatch, FakeQdrant(fails="delete"))

    await memory_service.delete_document_chunks(USER_ID, "doc-1")

    record = _only(warnings.records)
    assert "orphaned" in record.message, record.message
    assert record.document_id == "doc-1", record.__dict__
    assert record.exc_info is not None, "Traceback must survive into the log"


async def test_gather_context_broken_prompt_embedding_logs_warning(
    monkeypatch, warnings
):
    """task_service embeds the prompt once up front; that failure needs a line too."""
    from app.services import llm_service

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding endpoint unreachable")

    async def fake_retrieve(*_: Any, **__: Any) -> list[str]:
        return []

    monkeypatch.setattr(llm_service, "embed_texts", fake_embed)
    monkeypatch.setattr(memory_service, "retrieve_memories", fake_retrieve)

    context = await task_service._gather_context(USER_ID, "a prompt")

    assert context == [], f"Expected degraded context, got {context}"
    record = _only(warnings.records)
    assert "embedding" in record.message, record.message
    assert record.exc_info is not None, "Traceback must survive into the log"


async def test_remember_failure_logs_warning(monkeypatch, warnings):
    async def fake_add(*_: Any, **__: Any) -> str:
        raise ConnectionError("qdrant unreachable")

    monkeypatch.setattr(memory_service, "add_memory", fake_add)

    await task_service._remember(USER_ID, "prompt", "answer")

    record = _only(warnings.records)
    assert "memory" in record.message, record.message
    assert record.exc_info is not None, "Traceback must survive into the log"
