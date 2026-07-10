"""Task orchestration service.

Runs the Orchestrator → Main Agent → Subagent → (optional) Reviewer pipeline as
a background task, persisting state to MongoDB (``task_sessions``), streaming
live events over the event bus, and enforcing a total task timeout
(CLAUDE.md §9.2).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from pymongo import DESCENDING

from app.agents import main_agent, orchestrator
from app.agents.base import AgentContext
from app.core.config import settings
from app.core.constants import (
    QDRANT_DOCUMENT_CHUNKS,
    AgentRole,
    EventType,
    LLMProvider,
    MongoCollection,
    TaskStatus,
)
from app.core.database import get_mongo_db
from app.schemas.task import TaskCreate
from app.services import usage_service
from app.services.llm_service import FallbackLLMAdapter, TokenMeter, get_adapter
from app.utils.events import event_bus

# Registry of running background tasks, for cancellation.
_running: dict[str, asyncio.Task] = {}

# Pending human-in-the-loop questions, keyed by task id (CLAUDE.md §12).
_pending_questions: dict[str, asyncio.Future[str]] = {}

# How long an agent waits for a user's answer before giving up.
_HITL_TIMEOUT_SECONDS = 180
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


def _make_emit(task_id: str, user_id: uuid.UUID):
    """Build an emit callback that streams + persists an agent event.

    Log documents carry `user_id` so an account purge can find them directly;
    the enclosing session document already stores the owner.
    """

    async def emit(event_type: EventType, payload: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        event = {
            "type": event_type.value,
            "ts": now.isoformat(),
            **payload,
        }
        await event_bus.publish(task_id, event)
        # The two persistence writes are independent — run them concurrently.
        # `created_at` is a BSON date (unlike the ISO-string `ts`) because the
        # retention TTL index only expires real date fields.
        await asyncio.gather(
            _sessions_collection().update_one(
                {"task_id": task_id}, {"$push": {"events": event}}
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


async def start_task(
    *,
    user_id: uuid.UUID,
    payload: TaskCreate,
    api_key: str | None,
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

    runner = asyncio.create_task(
        _run_task(task_id=task_id, user_id=user_id, payload=payload, api_key=api_key)
    )
    _running[task_id] = runner
    runner.add_done_callback(lambda _t: _on_task_done(task_id))
    return task_id


def _on_task_done(task_id: str) -> None:
    """Clean up per-task registries when a task finishes or is cancelled."""
    _running.pop(task_id, None)
    future = _pending_questions.pop(task_id, None)
    if future is not None and not future.done():
        future.cancel()


async def _run_task(
    *,
    task_id: str,
    user_id: uuid.UUID,
    payload: TaskCreate,
    api_key: str | None,
) -> None:
    """Execute the pipeline with timeout + error handling."""
    emit = _make_emit(task_id, user_id)

    adapter = get_adapter(payload.provider, api_key=api_key)
    if payload.provider is LLMProvider.GEMINI:
        # Free-tier quota can run out mid-task; degrade to the local model
        # per call and tell the user instead of failing the whole task.
        async def _notify_fallback(reason: str) -> None:
            await emit(
                EventType.AGENT_MESSAGE,
                {
                    "from": "system",
                    "to": "user",
                    "content": (
                        f"Gemini unavailable ({reason}); "
                        "falling back to the local model."
                    ),
                },
            )

        adapter = FallbackLLMAdapter(
            primary=adapter,
            fallback=get_adapter(LLMProvider.OLLAMA),
            on_fallback=_notify_fallback,
        )

    # Outermost wrapper: every LLM call the pipeline makes is billed.
    meter = TokenMeter(adapter)

    terminal = TaskStatus.FAILED
    # Every await lives inside this block. A cancellation or failure while
    # setting up -- notably the RAG lookup, which hits Qdrant and the embedding
    # model -- would otherwise kill the task silently: no terminal status, and
    # no usage record for the tokens it had already spent.
    try:
        await _set_status(task_id, TaskStatus.RUNNING)
        await emit(EventType.TASK_STARTED, {"prompt": payload.prompt})

        # Best-effort RAG grounding: prior conversations + document chunks.
        memory_context = await _gather_context(user_id, payload.prompt)

        ctx = AgentContext(
            adapter=meter,
            emit=emit,
            max_iterations=payload.max_iterations,
            max_review_iterations=payload.max_review_iterations,
            memory_context=memory_context,
            ask_user=_make_ask_user(task_id),
            allow_questions=payload.allow_questions,
            max_web_searches=settings.web_search_max_uses_per_subtask,
            max_data_fetches=settings.data_fetch_max_uses_per_subtask,
            max_code_executions=settings.code_execution_max_uses_per_subtask,
            max_tool_calls=settings.subagent_max_tool_calls,
            max_parallel_subagents=settings.subagent_max_parallel,
        )

        result = await asyncio.wait_for(
            _pipeline(ctx, payload),
            timeout=settings.task_timeout_seconds,
        )
    except TimeoutError:
        terminal = TaskStatus.TIMEOUT
        await _fail(task_id, emit, TaskStatus.TIMEOUT, "Task exceeded time limit.")
        return
    except asyncio.CancelledError:
        terminal = TaskStatus.CANCELLED
        await _fail(task_id, emit, TaskStatus.CANCELLED, "Task cancelled.")
        raise
    except Exception as exc:  # noqa: BLE001 - surface any pipeline failure
        terminal = TaskStatus.FAILED
        await _fail(task_id, emit, TaskStatus.FAILED, str(exc))
        return
    else:
        # A pipeline that returned is not automatically a success: if every
        # subtask errored (e.g. the chat model is unreachable), the task FAILED
        # -- otherwise the user sees an empty answer marked "completed".
        all_failed = result.get("all_subtasks_failed", False)
        terminal = TaskStatus.FAILED if all_failed else TaskStatus.COMPLETED
        error_message = (
            "All subtasks failed; no output was produced." if all_failed else None
        )
        # The meter, not the subagent sum, is the authoritative token count.
        metadata = {**result.get("metadata", {}), "total_tokens": meter.total_tokens}
        await _sessions_collection().update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": terminal.value,
                    "domain": result.get("domain"),
                    # Persisted even on failure so the architect view can render
                    # the failed subtask nodes.
                    "result": result,
                    "metadata": metadata,
                    "error": error_message,
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        if all_failed:
            await emit(EventType.TASK_FAILED, {"error": error_message})
        else:
            await emit(EventType.TASK_COMPLETED, {"answer": result.get("answer")})
            # Best-effort: remember the interaction for future RAG context.
            await _remember(user_id, payload.prompt, result.get("answer", ""))
        await event_bus.close(task_id)
    finally:
        # Tokens a doomed task already burned still count against the quota, so
        # this runs on every path -- including the re-raised cancellation.
        await usage_service.record_task_usage(
            user_id=user_id,
            task_id=task_id,
            tokens=meter.total_tokens,
            provider=meter.provider.value,
            status=terminal.value,
        )


async def _pipeline(ctx: AgentContext, payload: TaskCreate) -> dict[str, Any]:
    if payload.domain:
        # User picked a domain agent explicitly — skip orchestrator routing.
        domain = payload.domain
        await ctx.emit(
            EventType.NODE_UPDATE,
            {
                "role": AgentRole.ORCHESTRATOR.value,
                "state": "done",
                "domain": domain,
                "reason": "Selected by the user",
                "source": "user",
            },
        )
    else:
        domain = await orchestrator.route(ctx, payload.prompt)
    return await main_agent.run(
        ctx,
        domain=domain,
        prompt=payload.prompt,
        reviewer_enabled=payload.reviewer_enabled,
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
    """Build a human-in-the-loop callback bound to a task (CLAUDE.md §12)."""

    async def ask(question: str) -> str:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        _pending_questions[task_id] = future
        try:
            return await asyncio.wait_for(future, timeout=_HITL_TIMEOUT_SECONDS)
        except TimeoutError:
            return "(no answer provided; proceed with best effort)"
        finally:
            _pending_questions.pop(task_id, None)

    return ask


async def submit_answer(task_id: str, user_id: uuid.UUID, answer: str) -> bool:
    """Deliver a user's answer to a task waiting on a question. Owner-only."""
    doc = await get_task(task_id, user_id)
    if doc is None:
        return False
    future = _pending_questions.get(task_id)
    if future is None or future.done():
        return False
    future.set_result(answer)
    await _make_emit(task_id, user_id)(EventType.USER_ANSWER, {"answer": answer})
    return True


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
    await emit(EventType.TASK_FAILED, {"error": message})
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


async def cancel_task(task_id: str, user_id: uuid.UUID) -> bool:
    """Cancel a running task owned by the user. Returns True if cancelled."""
    doc = await get_task(task_id, user_id)
    if doc is None:
        return False
    runner = _running.get(task_id)
    if runner is not None and not runner.done():
        runner.cancel()
        return True
    return False


def requires_api_key(provider: LLMProvider) -> bool:
    """Whether a provider needs a BYOK key (the free Ollama tier does not)."""
    return provider is not LLMProvider.OLLAMA
