"""Durable task-execution engine (Backend v2 §4.1).

Walks a task through explicit steps (ROUTE -> EXECUTE -> FINALIZE), writing a
Postgres checkpoint after each. A step whose checkpoint already exists is
*replayed* (its result is loaded, zero LLM calls); only the step in flight when
a worker died re-runs. ``task_runs`` is the authoritative status record and
carries a heartbeat-renewed ownership lease, so a crashed task is reclaimed and
resumed (or finalized) by the reconciliation sweep instead of hanging at
``running`` forever.

``task_service`` keeps its public API and delegates the run loop here; the
step handlers reuse ``task_service``'s Mongo/emit/RAG/HITL helpers.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.agents import main_agent
from app.agents.base import AgentContext
from app.agents.registry import resolve_domain_info
from app.core.config import settings
from app.core.constants import (
    DEFAULT_TASK_COMPLEXITY,
    LEASE_RENEW_SECONDS,
    LEASE_TTL_SECONDS,
    EventType,
    LLMProvider,
    SpanKind,
    TaskStatus,
    TaskStep,
)
from app.schemas.task import TaskCreate
from app.services import checkpoint_store, quota_service, task_run_store, usage_service
from app.services.llm_service import AdapterPool, set_retry_observer
from app.services.service_key_service import load_service_credentials
from app.utils import tracing
from app.utils.events import event_bus

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TaskRunContext:
    """Everything the engine needs to (re-)run one task. Never holds a raw key
    across a restart — a resumed run re-decrypts from ``api_keys``."""

    task_id: str
    user_id: uuid.UUID
    payload: TaskCreate
    api_key: str | None
    deadline_at: datetime
    base_url: str | None = None
    model: str | None = None
    resumed: bool = False


def _build_pool(rc: TaskRunContext, emit) -> AdapterPool:  # noqa: ANN001
    """Build the per-role adapter pool (identical fresh or on resume).

    Each agent role resolves its own model from the frozen payload's
    (preference-merged) overrides and the provider tier default, all sharing one
    token counter. A custom endpoint's fixed ``model`` overrides role resolution.
    TracedAdapter sits under the meter (a pass-through when tracing is off).
    """

    async def _notify_fallback(reason: str) -> None:
        # Gemini free-tier quota can run out mid-task; degrade to the local model
        # per call and tell the user instead of failing the whole task.
        await emit(
            EventType.AGENT_MESSAGE,
            {
                "from": "system",
                "to": "user",
                "content": (
                    f"Gemini unavailable ({reason}); falling back to the local model."
                ),
            },
        )

    return AdapterPool(
        provider=rc.payload.provider,
        api_key=rc.api_key,
        base_url=rc.base_url,
        model=rc.model,
        overrides=rc.payload.model_overrides,
        on_fallback=_notify_fallback,
        # Frozen on the payload at task start (request > user default > server).
        # TracedAdapter can only be installed here, so a run that opted out
        # records no llm.chat spans even if the server-wide flag is on.
        traced=bool(rc.payload.tracing_enabled),
    )


async def _heartbeat(task_id: str) -> None:
    """Renew this worker's ownership lease until cancelled."""
    while True:
        await asyncio.sleep(LEASE_RENEW_SECONDS)
        try:
            await task_run_store.renew_lease(task_id, LEASE_TTL_SECONDS)
        except Exception:  # noqa: BLE001 - a missed renewal only risks a reclaim
            logger.warning("lease renewal failed for task %s", task_id, exc_info=True)


async def _raise_if_cancelled(task_id: str) -> None:
    """Honour a persisted cancel request at a step boundary (works even when the
    request landed on another worker and only set the flag)."""
    if await task_run_store.is_cancel_requested(task_id):
        raise asyncio.CancelledError


async def _ctrl_listener(task_id: str) -> None:
    """Act on control messages (cancel / HITL answer) for a locally-owned task.

    Lets a request that landed on *another* worker reach the worker actually
    running the task: cancel interrupts the local runner immediately (instead of
    waiting for the next step-boundary flag check), and an answer resolves the
    local HITL future. A no-op on a single worker, where the request already
    finds the runner/future in-process.
    """
    from app.services import task_service

    async with event_bus.subscribe_ctrl(task_id) as queue:
        while True:
            message = await queue.get()
            op = message.get("op")
            if op == "cancel":
                runner = task_service._running.get(task_id)
                if runner is not None and not runner.done():
                    runner.cancel()
            elif op == "answer":
                future = task_service._pending_questions.get(task_id)
                if future is not None and not future.done():
                    future.set_result(message.get("answer", ""))


async def run(rc: TaskRunContext) -> None:
    """Execute (or resume) a task through the durable step loop."""
    from app.services import task_service  # lazy: avoids an import cycle

    # Pin the run's tracing choice onto this asyncio task's context before any
    # span opens, so the structural spans (task/step/agent) honour it too — not
    # just the llm.chat spans that TracedAdapter contributes.
    tracing.tracer.set_enabled(rc.payload.tracing_enabled)
    emit = task_service._make_emit(rc.task_id, rc.user_id)

    async def _on_llm_retry(info: dict[str, Any]) -> None:
        """Surface a degrading provider link while the task is still running."""
        await emit(
            EventType.AGENT_WARNING,
            {
                "kind": "retry",
                "message": (
                    f"Provider connection retry #{info['attempt']} ({info['cause']})"
                ),
            },
        )

    # Same context-pinning as tracing above: the observer rides this asyncio
    # task's context down into every subagent it spawns.
    set_retry_observer(_on_llm_retry)
    pool = _build_pool(rc, emit)
    if rc.resumed:
        # Seed billing with pre-crash spend so the pool's running total (and the
        # usage upsert-max) never lose already-counted tokens.
        pool.total_tokens = await checkpoint_store.token_sum(rc.task_id)
    # Free-tier (Ollama) tokens are recorded but not billed. Per-provider
    # attribution for a Gemini task that fell back to Ollama arrives in Tur 10.
    billable = rc.payload.provider is not LLMProvider.OLLAMA

    heartbeat = asyncio.create_task(_heartbeat(rc.task_id))
    ctrl = asyncio.create_task(_ctrl_listener(rc.task_id))
    terminal = TaskStatus.FAILED
    try:
        await task_run_store.set_status(
            rc.task_id, TaskStatus.RUNNING.value, current_step=TaskStep.ROUTE.value
        )
        await task_service._set_status(rc.task_id, TaskStatus.RUNNING)
        await emit(EventType.TASK_STARTED, {"prompt": rc.payload.prompt})

        remaining = (rc.deadline_at - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise TimeoutError
        async with tracing.tracer.span(
            "task",
            SpanKind.TASK,
            trace_id=rc.task_id,
            user_id=str(rc.user_id),
            **{
                "maestro.provider": rc.payload.provider.value,
                "maestro.resumed": rc.resumed,
            },
        ):
            result = await asyncio.wait_for(_walk(rc, pool, emit), timeout=remaining)
    except TimeoutError:
        terminal = TaskStatus.TIMEOUT
        logger.warning(
            "task %s timed out",
            rc.task_id,
            extra={"task_id": rc.task_id, "user_id": str(rc.user_id)},
        )
        await _finalize_failure(
            rc, emit, TaskStatus.TIMEOUT, "Task exceeded time limit."
        )
        return
    except asyncio.CancelledError:
        terminal = TaskStatus.CANCELLED
        logger.info(
            "task %s cancelled",
            rc.task_id,
            extra={"task_id": rc.task_id, "user_id": str(rc.user_id)},
        )
        await _finalize_failure(rc, emit, TaskStatus.CANCELLED, "Task cancelled.")
        raise
    except Exception as exc:  # noqa: BLE001 - surface any pipeline failure
        terminal = TaskStatus.FAILED
        logger.exception(
            "task %s failed with an unhandled error",
            rc.task_id,
            extra={"task_id": rc.task_id, "user_id": str(rc.user_id)},
        )
        await _finalize_failure(rc, emit, TaskStatus.FAILED, str(exc))
        return
    else:
        terminal = await _finalize_success(rc, emit, pool, result)
    finally:
        for sidecar in (heartbeat, ctrl):
            sidecar.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sidecar
        # Tokens a doomed task already burned still count, so this runs on every
        # path -- including the re-raised cancellation. Upsert-max + idempotent.
        await usage_service.record_task_usage(
            user_id=rc.user_id,
            task_id=rc.task_id,
            tokens=pool.total_tokens,
            provider=pool.provider.value,
            status=terminal.value,
            billable=billable,
        )
        # Land this task's spans promptly (best-effort; a no-op when off).
        await tracing.force_flush()


async def _walk(rc: TaskRunContext, pool: AdapterPool, emit) -> dict[str, Any]:  # noqa: ANN001
    """Route -> execute, replaying any step that already has a checkpoint."""
    from app.services import task_service

    await _raise_if_cancelled(rc.task_id)
    memory_context = await task_service._gather_context(rc.user_id, rc.payload.prompt)
    # Decrypt this user's BYOK service keys once, here at the engine edge, and
    # hand the agent layer plain data — the same shape as memory_context and the
    # LLM brain key. Never raises: an absent or unreadable key just means the
    # connected tools are withheld and the squad works from web_search.
    service_credentials = await load_service_credentials(rc.user_id)
    ctx = AgentContext(
        adapter=pool.for_role("main"),
        adapter_pool=pool,
        emit=emit,
        max_iterations=rc.payload.max_iterations,
        max_review_iterations=rc.payload.max_review_iterations,
        memory_context=memory_context,
        ask_user=task_service._make_ask_user(rc.task_id),
        allow_questions=rc.payload.allow_questions,
        max_web_searches=settings.web_search_max_uses_per_subtask,
        max_data_fetches=settings.data_fetch_max_uses_per_subtask,
        max_code_executions=settings.code_execution_max_uses_per_subtask,
        max_document_searches=settings.document_search_max_uses_per_subtask,
        max_memory_recalls=settings.memory_recall_max_uses_per_subtask,
        max_repo_lookups=settings.repo_intel_max_uses_per_subtask,
        max_social_searches=settings.social_search_max_uses_per_subtask,
        max_community_reads=settings.community_read_max_uses_per_subtask,
        max_places_lookups=settings.places_intel_max_uses_per_subtask,
        max_tool_calls=settings.subagent_max_tool_calls,
        max_tool_grants=settings.subagent_max_tool_grants,
        max_parallel_subagents=settings.subagent_max_parallel,
        service_credentials=service_credentials,
        user_id=rc.user_id,
    )

    # --- ROUTE ---
    await _raise_if_cancelled(rc.task_id)
    async with tracing.tracer.span(
        "step:route", SpanKind.STEP, **{"maestro.step": TaskStep.ROUTE.value}
    ) as route_span:
        route_cp = await checkpoint_store.load(rc.task_id, TaskStep.ROUTE.value)
        if route_cp is not None:
            domain = route_cp["domain"]
            complexity = route_cp.get("complexity", DEFAULT_TASK_COMPLEXITY)
            route_span.set_attribute("maestro.replayed", True)
            await emit(
                EventType.NODE_UPDATE,
                {
                    "role": "orchestrator",
                    "state": "done",
                    "domain": domain,
                    "source": route_cp.get("source"),
                    "replayed": True,
                },
            )
        else:
            before = pool.total_tokens
            decision = await task_service._route(ctx, rc.payload, user_id=rc.user_id)
            domain = decision.domain
            complexity = decision.complexity
            await checkpoint_store.write(
                rc.task_id,
                TaskStep.ROUTE.value,
                {
                    "v": 1,
                    "domain": domain,
                    "complexity": complexity,
                    "source": "user" if rc.payload.domain else "orchestrator",
                },
                pool.total_tokens - before,
            )
            await task_run_store.set_status(
                rc.task_id,
                TaskStatus.RUNNING.value,
                current_step=TaskStep.EXECUTE.value,
            )
        route_span.set_attribute("maestro.domain", domain)
        route_span.set_attribute("maestro.complexity", complexity)

    # Resolve the effective domain agent once the domain is known. For a custom
    # (``custom:{id}``) agent this loads and sandboxes the user's config; raises
    # CustomAgentUnavailable (a normal task failure) if it is gone or now unsafe.
    ctx.domain_info = await resolve_domain_info(rc.user_id, domain)

    # Step-boundary quota re-check (D19): cap this task's spend at the remaining
    # monthly quota (or the default budget, whichever is lower). Recomputed here
    # so a resumed run reflects tokens spent before the crash.
    ctx.token_budget = await quota_service.resolve_task_token_budget(rc.user_id)

    # --- EXECUTE (plan + subagent waves + reviewer + synthesis) ---
    await _raise_if_cancelled(rc.task_id)
    async with tracing.tracer.span(
        "step:execute",
        SpanKind.STEP,
        **{"maestro.step": TaskStep.EXECUTE.value, "maestro.domain": domain},
    ) as exec_span:
        exec_cp = await checkpoint_store.load(rc.task_id, TaskStep.EXECUTE.value)
        if exec_cp is not None:
            exec_span.set_attribute("maestro.replayed", True)
            return exec_cp["result"]

        before = pool.total_tokens
        result = await main_agent.run(
            ctx,
            domain=domain,
            prompt=rc.payload.prompt,
            reviewer_enabled=rc.payload.reviewer_enabled,
            complexity=complexity,
        )
        await checkpoint_store.write(
            rc.task_id,
            TaskStep.EXECUTE.value,
            {"v": 1, "result": result},
            pool.total_tokens - before,
        )
        await task_run_store.set_status(
            rc.task_id, TaskStatus.RUNNING.value, current_step=TaskStep.FINALIZE.value
        )
        return result


async def _finalize_success(
    rc: TaskRunContext,
    emit,  # noqa: ANN001
    pool: AdapterPool,
    result: dict[str, Any],
) -> TaskStatus:
    """Persist the result, emit the terminal event, record memory (FINALIZE)."""
    from app.services import task_service

    all_failed = result.get("all_subtasks_failed", False)
    failed_subtasks = result.get("failed_subtasks", [])
    # None failed -> completed; some -> completed_with_warnings; all -> failed.
    if all_failed:
        terminal = TaskStatus.FAILED
    elif failed_subtasks:
        terminal = TaskStatus.COMPLETED_WITH_WARNINGS
    else:
        terminal = TaskStatus.COMPLETED

    error_message = None
    if all_failed:
        reason = result.get("failure_reason")
        error_message = (
            f"All subtasks failed: {reason}"
            if reason
            else "All subtasks failed; no output was produced."
        )
        logger.error(
            "task %s failed (provider=%s): %s",
            rc.task_id,
            rc.payload.provider.value,
            error_message,
            extra={"task_id": rc.task_id, "user_id": str(rc.user_id)},
        )

    warnings = [
        f"{f.get('member_name', f.get('member_id', 'A subtask'))} did not complete: "
        f"{f.get('error') or 'unknown error'}"
        for f in failed_subtasks
    ]
    metadata = {**result.get("metadata", {}), "total_tokens": pool.total_tokens}
    await task_service._sessions_collection().update_one(
        {"task_id": rc.task_id},
        {
            "$set": {
                "status": terminal.value,
                "domain": result.get("domain"),
                "result": result,
                "metadata": metadata,
                "error": error_message,
                "warnings": warnings,
                "updated_at": datetime.now(UTC),
            }
        },
    )
    await task_run_store.set_status(
        rc.task_id, terminal.value, current_step=TaskStep.FINALIZE.value
    )
    if all_failed:
        await emit(
            EventType.TASK_FAILED,
            {"error": error_message, "status": terminal.value},
        )
    elif terminal is TaskStatus.COMPLETED_WITH_WARNINGS:
        await emit(
            EventType.TASK_COMPLETED_WITH_WARNINGS,
            {"answer": result.get("answer"), "warnings": warnings},
        )
        await task_service._remember(
            rc.user_id, rc.payload.prompt, result.get("answer", "")
        )
    else:
        await emit(EventType.TASK_COMPLETED, {"answer": result.get("answer")})
        await task_service._remember(
            rc.user_id, rc.payload.prompt, result.get("answer", "")
        )
    await event_bus.close(rc.task_id)
    return terminal


async def _finalize_failure(
    rc: TaskRunContext,
    emit,  # noqa: ANN001
    terminal: TaskStatus,
    message: str,
) -> None:
    """Terminal failure/timeout/cancel path: Mongo status, terminal event, bus
    close, and the authoritative Postgres status."""
    from app.services import task_service

    await task_service._fail(rc.task_id, emit, terminal, message)
    await task_run_store.set_status(rc.task_id, terminal.value)
