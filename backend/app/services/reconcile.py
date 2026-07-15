"""Startup and periodic reconciliation of crashed task runs (Backend v2 §4.1).

When a worker dies, its in-flight tasks are left owning a ``task_runs`` row whose
lease stops being renewed. The sweep atomically re-claims each orphan and either
*resumes* it (rebuild the context, re-decrypt the key, replay completed
checkpoints, re-run the interrupted step) or *finalizes* it (past its deadline,
over the resume-attempt cap, or unrecoverable). This is what turns "restart
orphans every in-flight task; sessions stuck at running forever" into a bounded,
billed terminal state — and what makes ``uvicorn --workers N`` safe, since the
claim is a single conditional UPDATE that exactly one worker wins.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.constants import (
    LEASE_TTL_SECONDS,
    RECLAIM_SWEEP_SECONDS,
    TASK_MAX_RESUME_ATTEMPTS,
    LLMProvider,
    TaskStatus,
)
from app.core.database import SessionLocal
from app.core.security import decrypt_secret
from app.models.api_key import ApiKey
from app.services import checkpoint_store, task_engine, task_run_store, usage_service
from app.services.task_run_store import RunRow

logger = logging.getLogger(__name__)


async def _resolve_credentials(
    run: RunRow,
) -> tuple[str | None, str | None, str | None] | None:
    """Re-fetch the BYOK material a resumed run needs, or None if unavailable.

    The local model needs no key. For every other provider the active key must
    still exist (and be decryptable); a rotated/removed key means the run cannot
    be resumed and must be failed with a clear message.
    """
    if run.provider == LLMProvider.OLLAMA.value:
        return (None, None, None)
    async with SessionLocal() as db:
        api_key = (
            await db.scalars(
                select(ApiKey).where(
                    ApiKey.user_id == run.user_id,
                    ApiKey.provider == run.provider,
                    ApiKey.is_active.is_(True),
                )
            )
        ).first()
    if api_key is None:
        return None
    try:
        secret = decrypt_secret(api_key.encrypted_key)
    except Exception:  # noqa: BLE001 - a corrupt/rotated key cannot resume
        return None
    return (secret, api_key.base_url, api_key.model)


async def _finalize_dead(run: RunRow, terminal: TaskStatus, message: str) -> None:
    """Drive an unrecoverable orphan to a terminal state and bill its spend.

    Idempotent: status writes are last-writer-wins and usage is upsert-max, so a
    finalize that races another (or a resumed run's own ``finally``) is safe.
    """
    from app.services import task_service

    tokens = await checkpoint_store.token_sum(run.task_id)
    billable = run.provider != LLMProvider.OLLAMA.value
    await task_run_store.set_status(run.task_id, terminal.value)
    emit = task_service._make_emit(run.task_id, run.user_id)
    await task_service._fail(run.task_id, emit, terminal, message)
    await usage_service.record_task_usage(
        user_id=run.user_id,
        task_id=run.task_id,
        tokens=tokens,
        provider=run.provider,
        status=terminal.value,
        billable=billable,
    )


async def _resume(run: RunRow) -> None:
    """Rebuild a run context from the header and re-launch the engine."""
    from app.schemas.task import TaskCreate
    from app.services import task_service

    creds = await _resolve_credentials(run)
    if creds is None:
        await _finalize_dead(
            run,
            TaskStatus.FAILED,
            "Cannot resume: the required API key is no longer available.",
        )
        return
    secret, base_url, model = creds
    payload = TaskCreate(**run.payload)
    rc = task_engine.TaskRunContext(
        task_id=run.task_id,
        user_id=run.user_id,
        payload=payload,
        api_key=secret,
        deadline_at=run.deadline_at,
        base_url=base_url,
        model=model,
        resumed=True,
    )
    runner = asyncio.create_task(task_engine.run(rc))
    task_service._running[run.task_id] = runner
    runner.add_done_callback(lambda _t: task_service._on_task_done(run.task_id))


async def sweep_once() -> int:
    """Run one reconciliation pass. Returns the number of runs acted on."""
    acted = 0

    # 1) Orphans over the attempt cap can never be reclaimed — fail them.
    for run in await task_run_store.list_dead_over_cap(
        max_attempts=TASK_MAX_RESUME_ATTEMPTS
    ):
        await _finalize_dead(
            run,
            TaskStatus.FAILED,
            "The worker running this task crashed repeatedly; task abandoned.",
        )
        acted += 1

    # 2) Claim reclaimable orphans (increments attempt atomically).
    now = datetime.now(UTC)
    for run in await task_run_store.claim_orphans(
        ttl_seconds=LEASE_TTL_SECONDS, max_attempts=TASK_MAX_RESUME_ATTEMPTS
    ):
        # SQLite hands datetimes back naive; treat a naive deadline as UTC so the
        # comparison is valid on both backends.
        deadline = run.deadline_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        if now >= deadline:
            await _finalize_dead(run, TaskStatus.TIMEOUT, "Task exceeded time limit.")
        else:
            await _resume(run)
        acted += 1

    return acted


async def startup_reclaim() -> None:
    """One best-effort sweep at boot (never blocks or crashes startup)."""
    try:
        count = await sweep_once()
        if count:
            logger.info("startup reconciliation acted on %d orphaned task(s)", count)
    except Exception:  # noqa: BLE001 - reconciliation must not block startup
        logger.warning("startup reconciliation failed", exc_info=True)


async def periodic_sweep() -> None:
    """Background loop reclaiming orphans every ``RECLAIM_SWEEP_SECONDS``."""
    while True:
        await asyncio.sleep(RECLAIM_SWEEP_SECONDS)
        try:
            await sweep_once()
        except Exception:  # noqa: BLE001 - a failed sweep retries next tick
            logger.warning("periodic reconciliation sweep failed", exc_info=True)
