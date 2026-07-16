"""Task orchestration service.

Runs the Orchestrator → Main Agent → Subagent → (optional) Reviewer pipeline as
a background task, persisting state to MongoDB (``task_sessions``), streaming
live events over the event bus, and enforcing a total task timeout
(CLAUDE.md §9.2).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import DESCENDING

from app.agents import main_agent, orchestrator
from app.core.config import settings
from app.core.constants import (
    HITL_TIMEOUT_SECONDS,
    QDRANT_DOCUMENT_CHUNKS,
    TASK_EVENT_ENVELOPE_VERSION,
    TASK_EVENTS_MONGO_KEEP,
    AgentRole,
    EventType,
    LLMProvider,
    MongoCollection,
    TaskStatus,
)
from app.core.database import get_mongo_db
from app.schemas.task import TaskCreate
from app.services import question_store, task_engine, task_run_store
from app.utils import tracing
from app.utils.events import event_bus

logger = logging.getLogger(__name__)

# Per-worker cache of running background tasks, for local cancellation. The
# authoritative record is Postgres ``task_runs``; correctness never depends on
# this dict (a task owned by another worker simply is not here).
_running: dict[str, asyncio.Task] = {}

# Pending human-in-the-loop questions, keyed by task id (CLAUDE.md §12). The
# future delivers the answer to the locally-running agent; the durable record is
# the ``task_questions`` row (see ``question_store``).
_pending_questions: dict[str, asyncio.Future[str]] = {}
# Correlates the locally-awaited future with its persisted question row.
_pending_question_ids: dict[str, uuid.UUID] = {}

# Max RAG context snippets injected into the agent prompts.
_MAX_CONTEXT_ITEMS = 6
# Prompt characters kept in a history-list entry.
_PROMPT_PREVIEW_LEN = 140
# Fields the history list needs; `events` is deliberately excluded.
_SUMMARY_PROJECTION = {
    "_id": 0,
    "task_id": 1,
    "status": 1,
    "prompt": 1,
    "domain": 1,
    "error": 1,
    "created_at": 1,
    "updated_at": 1,
}


def _sessions_collection():
    return get_mongo_db()[MongoCollection.TASK_SESSIONS.value]


def _logs_collection():
    return get_mongo_db()[MongoCollection.AGENT_LOGS.value]


# Per-task, per-worker sequence counters. ``seq`` orders a task's event stream
# so a reconnecting client can resume with ``?after_seq=N``. Global monotonicity
# across workers (Redis ``INCR``) arrives with the Redis event bus; within a
# single worker this counter is authoritative and persisted into ``agent_logs``.
_seq_counters: dict[str, int] = {}
_seq_lock = asyncio.Lock()


async def _next_seq(task_id: str) -> int:
    async with _seq_lock:
        seq = _seq_counters.get(task_id, 0) + 1
        _seq_counters[task_id] = seq
        return seq


def _make_emit(task_id: str, user_id: uuid.UUID):
    """Build an emit callback that streams + persists an agent event.

    Each event is stamped with an envelope version and a monotonic ``seq``.
    ``agent_logs`` is the seq-ordered source of truth (backs the WebSocket
    snapshot/cursor); the ``task_sessions.events`` mirror is capped so a long
    task can no longer grow one Mongo document past the 16 MB BSON limit.
    Log documents carry `user_id` so an account purge can find them directly.
    """

    async def emit(event_type: EventType, payload: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        seq = await _next_seq(task_id)
        event = {
            "v": TASK_EVENT_ENVELOPE_VERSION,
            "seq": seq,
            "type": event_type.value,
            "ts": now.isoformat(),
            **payload,
        }
        # Correlate the event with the active trace span (Backend v2 §4.5); None
        # when tracing is off, so the wire shape is unchanged for existing clients.
        current_span = tracing.tracer.current()
        if current_span is not None:
            event["span_id"] = current_span.span_id
        await event_bus.publish(task_id, event)
        # The two persistence writes are independent — run them concurrently.
        # `created_at` is a BSON date (unlike the ISO-string `ts`) because the
        # retention TTL index only expires real date fields.
        await asyncio.gather(
            _sessions_collection().update_one(
                {"task_id": task_id},
                {
                    "$push": {
                        "events": {"$each": [event], "$slice": -TASK_EVENTS_MONGO_KEEP}
                    }
                },
            ),
            _logs_collection().insert_one(
                {
                    "task_id": task_id,
                    "user_id": str(user_id),
                    "created_at": now,
                    **event,
                }
            ),
        )

    return emit


async def events_since(
    task_id: str, user_id: uuid.UUID, after_seq: int, *, limit: int
) -> tuple[list[dict[str, Any]], int]:
    """Owner-scoped snapshot of a task's events with ``seq > after_seq``.

    Reads the ``agent_logs`` source of truth (not the capped session mirror),
    ordered by seq and capped at ``limit``. Returns the events (projected to the
    live wire shape) and the highest seq in the batch (the resume cursor).
    """
    # Ownership: the session doc is the authoritative owner record.
    if await get_task(task_id, user_id) is None:
        return [], after_seq
    cursor = (
        _logs_collection()
        .find(
            {"task_id": task_id, "seq": {"$gt": after_seq}},
            {"_id": 0, "task_id": 0, "user_id": 0, "created_at": 0},
        )
        .sort("seq", 1)
        .limit(limit)
    )
    events = [event async for event in cursor]
    last_seq = events[-1]["seq"] if events else after_seq
    return events, last_seq


async def start_task(
    *,
    user_id: uuid.UUID,
    payload: TaskCreate,
    api_key: str | None,
    base_url: str | None = None,
    model: str | None = None,
) -> str:
    """Create a task session and launch the orchestration in the background."""
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    document = {
        "task_id": task_id,
        "user_id": str(user_id),
        "status": TaskStatus.PENDING.value,
        "prompt": payload.prompt,
        "provider": payload.provider.value,
        "reviewer_enabled": payload.reviewer_enabled,
        "domain": payload.domain,
        "result": None,
        "error": None,
        "events": [],
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }
    await _sessions_collection().insert_one(document)

    # Durable run header: authoritative status + ownership lease + resume deadline.
    deadline_at = now + timedelta(seconds=settings.task_timeout_seconds)
    await task_run_store.create_run(
        task_id=task_id,
        user_id=user_id,
        payload=payload.model_dump(mode="json"),
        provider=payload.provider.value,
        deadline_at=deadline_at,
    )

    rc = task_engine.TaskRunContext(
        task_id=task_id,
        user_id=user_id,
        payload=payload,
        api_key=api_key,
        deadline_at=deadline_at,
        base_url=base_url,
        model=model,
    )
    runner = asyncio.create_task(task_engine.run(rc))
    _running[task_id] = runner
    runner.add_done_callback(lambda _t: _on_task_done(task_id))
    return task_id


def _on_task_done(task_id: str) -> None:
    """Clean up per-task registries when a task finishes or is cancelled."""
    _running.pop(task_id, None)
    _pending_question_ids.pop(task_id, None)
    _seq_counters.pop(task_id, None)
    future = _pending_questions.pop(task_id, None)
    if future is not None and not future.done():
        future.cancel()


async def _route(  # noqa: ANN001
    ctx, payload: TaskCreate, *, user_id: uuid.UUID | None = None
) -> orchestrator.RouteResult:
    """Resolve the task's domain + complexity: the user's explicit pick, else
    orchestrator routing. Split out of ``_pipeline`` so the engine can checkpoint
    the routing decision independently of execution. A user-picked domain skips
    classification and runs at the standard effort tier. When ``user_id`` is
    given, the caller's routable custom agents are merged into the routing
    catalog so the orchestrator can pick one (Backend v2 §4.3)."""
    if payload.domain:
        # User picked a domain agent explicitly — skip orchestrator routing.
        await ctx.emit(
            EventType.NODE_UPDATE,
            {
                "role": AgentRole.ORCHESTRATOR.value,
                "state": "done",
                "domain": payload.domain,
                "reason": "Selected by the user",
                "source": "user",
            },
        )
        # A user who picked the domain gets its full team (no effort reduction).
        return orchestrator.RouteResult(domain=payload.domain, complexity="complex")
    custom_agents: list[dict[str, Any]] = []
    if user_id is not None:
        from app.services import agent_service

        try:
            custom_agents = await agent_service.list_routable_agents(user_id)
        except Exception:  # noqa: BLE001 - custom-agent merge is best-effort
            logger.warning("routable custom agents lookup failed", exc_info=True)
    return await orchestrator.route_decision(
        ctx, payload.prompt, custom_agents=custom_agents
    )


async def _pipeline(ctx, payload: TaskCreate) -> dict[str, Any]:  # noqa: ANN001
    """Route then execute. Retained for direct/domain-selection tests; the engine
    drives the two steps separately so it can checkpoint between them."""
    decision = await _route(ctx, payload)
    return await main_agent.run(
        ctx,
        domain=decision.domain,
        prompt=payload.prompt,
        reviewer_enabled=payload.reviewer_enabled,
        complexity=decision.complexity,
    )


async def _gather_context(user_id: uuid.UUID, prompt: str) -> list[str]:
    """Retrieve per-user RAG context (conversations + documents). Best-effort."""
    from app.services import llm_service, memory_service

    # Embed the prompt once and reuse the vector across both collection
    # searches, which then run concurrently. Best-effort: any failure yields
    # no context rather than blocking the task.
    try:
        query_vector: list[float] | None = (await llm_service.embed_texts([prompt]))[0]
    except Exception:  # noqa: BLE001 - RAG is best-effort; degrade gracefully
        query_vector = None

    convo, docs = await asyncio.gather(
        memory_service.retrieve_memories(user_id, prompt, query_vector=query_vector),
        memory_service.retrieve_memories(
            user_id,
            prompt,
            collection=QDRANT_DOCUMENT_CHUNKS,
            query_vector=query_vector,
        ),
    )
    return (convo + docs)[:_MAX_CONTEXT_ITEMS]


def _make_ask_user(task_id: str):
    """Build a human-in-the-loop callback bound to a task (CLAUDE.md §12).

    The question is persisted (``task_questions``) and the run flips to
    ``awaiting_answer`` while waiting, so the pause is visible in durable state;
    the in-process future still delivers the answer to the local agent (Tur 8).
    """

    async def ask(question: str) -> str:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        _pending_questions[task_id] = future
        expires_at = datetime.now(UTC) + timedelta(seconds=HITL_TIMEOUT_SECONDS)
        question_id = await question_store.create_question(
            task_id=task_id, question=question, expires_at=expires_at
        )
        _pending_question_ids[task_id] = question_id
        await task_run_store.set_status(task_id, TaskStatus.AWAITING_ANSWER.value)
        await _set_status(task_id, TaskStatus.AWAITING_ANSWER)
        try:
            answer = await asyncio.wait_for(future, timeout=HITL_TIMEOUT_SECONDS)
            await _restore_running(task_id)
            return answer
        except TimeoutError:
            await question_store.expire_question(question_id)
            await _restore_running(task_id)
            return "(no answer provided; proceed with best effort)"
        finally:
            # No await here on the cancellation path: the engine's terminal
            # handler owns the authoritative status when the run is cancelled.
            _pending_questions.pop(task_id, None)
            _pending_question_ids.pop(task_id, None)

    return ask


async def _restore_running(task_id: str) -> None:
    """Return a run from ``awaiting_answer`` to ``running`` after HITL resolves."""
    await task_run_store.set_status(task_id, TaskStatus.RUNNING.value)
    await _set_status(task_id, TaskStatus.RUNNING)


async def submit_answer(task_id: str, user_id: uuid.UUID, answer: str) -> bool:
    """Deliver a user's answer to a task waiting on a question. Owner-only.

    Delivered locally when this worker runs the task; otherwise routed over the
    control channel to whichever worker owns it (the answer is persisted first so
    a concurrent resume sees it).
    """
    doc = await get_task(task_id, user_id)
    if doc is None:
        return False

    future = _pending_questions.get(task_id)
    if future is not None and not future.done():
        future.set_result(answer)
        question_id = _pending_question_ids.get(task_id)
        if question_id is not None:
            await question_store.answer_question(question_id, answer)
        await _make_emit(task_id, user_id)(EventType.USER_ANSWER, {"answer": answer})
        return True

    # Not awaited locally: another worker may own a task paused on a question.
    if doc.get("status") == TaskStatus.AWAITING_ANSWER.value:
        pending = await question_store.latest_pending(task_id)
        if pending is not None:
            await question_store.answer_question(pending.question_id, answer)
            await event_bus.publish_ctrl(task_id, {"op": "answer", "answer": answer})
            await _make_emit(task_id, user_id)(
                EventType.USER_ANSWER, {"answer": answer}
            )
            return True
    return False


async def _remember(user_id: uuid.UUID, prompt: str, answer: str) -> None:
    from app.services import memory_service

    try:
        await memory_service.add_memory(
            user_id, f"Q: {prompt}\nA: {answer}", metadata={"kind": "task"}
        )
    except Exception:  # noqa: BLE001 - memory is best-effort
        pass


async def _set_status(task_id: str, status: TaskStatus) -> None:
    await _sessions_collection().update_one(
        {"task_id": task_id},
        {"$set": {"status": status.value, "updated_at": datetime.now(UTC)}},
    )


async def _fail(task_id, emit, status: TaskStatus, message: str) -> None:  # noqa: ANN001
    await _sessions_collection().update_one(
        {"task_id": task_id},
        {
            "$set": {
                "status": status.value,
                "error": message,
                "updated_at": datetime.now(UTC),
            }
        },
    )
    # Carry the true terminal status so the live view freezes with the right
    # look (cancelled → orange, timeout/failed → red) even when this client did
    # not initiate the cancel, and on snapshot replay. A user-initiated cancel
    # is its own event type so the client can tell it apart from a failure.
    event_type = (
        EventType.TASK_CANCELLED
        if status is TaskStatus.CANCELLED
        else EventType.TASK_FAILED
    )
    await emit(event_type, {"error": message, "status": status.value})
    await event_bus.close(task_id)


async def get_task(task_id: str, user_id: uuid.UUID) -> dict[str, Any] | None:
    """Return a task session document owned by the user, or None."""
    return await _sessions_collection().find_one(
        {"task_id": task_id, "user_id": str(user_id)}, {"_id": 0}
    )


def build_summary(doc: dict[str, Any]) -> dict[str, Any]:
    """Project a task session onto the lightweight shape the history list needs.

    Pure (no I/O) so it can be unit-tested without a database.
    """
    prompt: str = doc.get("prompt", "")
    if len(prompt) > _PROMPT_PREVIEW_LEN:
        prompt = prompt[:_PROMPT_PREVIEW_LEN].rstrip() + "…"
    return {
        "task_id": doc["task_id"],
        "status": doc["status"],
        "prompt": prompt,
        "domain": doc.get("domain"),
        "error": doc.get("error"),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }


async def list_tasks(
    user_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    """Return one page of the user's task summaries (newest first) and the total.

    Never loads `events`: a finished session's event array can be megabytes.
    """
    query = {"user_id": str(user_id)}
    collection = _sessions_collection()
    cursor = (
        collection.find(query, _SUMMARY_PROJECTION)
        .sort("created_at", DESCENDING)
        .skip(offset)
        .limit(limit)
    )
    summaries = [build_summary(doc) async for doc in cursor]
    total = await collection.count_documents(query)
    return summaries, total


_LIVE_STATUSES = {
    TaskStatus.PENDING.value,
    TaskStatus.RUNNING.value,
    TaskStatus.AWAITING_ANSWER.value,
}


async def cancel_task(task_id: str, user_id: uuid.UUID) -> bool:
    """Cancel a live task owned by the user. Returns True if the cancel applies.

    The intent is persisted on ``task_runs`` so a task owned by another worker
    (or one that later resumes) honours it at the next step boundary; if the
    runner is local, it is cancelled immediately.
    """
    doc = await get_task(task_id, user_id)
    if doc is None:
        return False
    await task_run_store.request_cancel(task_id)
    runner = _running.get(task_id)
    if runner is not None and not runner.done():
        runner.cancel()
        return True
    # No local runner: the task may be owned by another worker. Signal it over
    # the control channel (its ctrl-listener cancels the local runner); the
    # persisted flag is the backstop, honoured at the next step boundary / on
    # resume. A terminal task cannot be cancelled.
    if doc.get("status") in _LIVE_STATUSES:
        await event_bus.publish_ctrl(task_id, {"op": "cancel"})
        return True
    return False


async def delete_task(task_id: str, user_id: uuid.UUID) -> bool:
    """Delete a task owned by the user, with its logs. Returns True if removed.

    A still-running task is cancelled first so its background runner stops
    writing to a session document that is about to disappear. The session and
    its `agent_logs` are removed together (both keyed by `task_id`); the
    conversation memory written on success is not tagged per task, so it is
    left to the account-purge path (CLAUDE.md §Tur 4).
    """
    doc = await get_task(task_id, user_id)
    if doc is None:
        return False
    runner = _running.get(task_id)
    if runner is not None and not runner.done():
        runner.cancel()
    await asyncio.gather(
        _sessions_collection().delete_one(
            {"task_id": task_id, "user_id": str(user_id)}
        ),
        _logs_collection().delete_many({"task_id": task_id, "user_id": str(user_id)}),
    )
    # Drop the durable run header too (checkpoints/questions cascade), so the
    # reconciliation sweep can never resurrect a deleted task.
    await task_run_store.delete_run(task_id, user_id)
    return True


def requires_api_key(provider: LLMProvider) -> bool:
    """Whether a provider needs a BYOK key (the free Ollama tier does not)."""
    return provider is not LLMProvider.OLLAMA
