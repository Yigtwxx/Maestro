"""Task endpoints: start, poll status, cancel."""

from __future__ import annotations

from typing import NamedTuple

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.agents.registry import CUSTOM_DOMAIN_PREFIX, is_custom_domain
from app.core.config import settings
from app.core.constants import (
    LLM_CHAT_PROVIDERS,
    RATE_LIMIT_EXPENSIVE,
    RATE_LIMIT_READ,
    RATE_LIMIT_WRITE,
    LLMProvider,
    TaskStatus,
)
from app.core.deps import ActiveUser, DbSession, VerifiedUser
from app.core.security import decrypt_secret
from app.models.api_key import ApiKey
from app.schemas.task import (
    TaskAnswer,
    TaskCreate,
    TaskCreated,
    TaskListResponse,
    TaskState,
    TaskSummary,
)
from app.services import agent_service, quota_service, task_service, trace_service
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Starting a task is the expensive path; throttle it independently.
_start_task_rate_limit = rate_limit(RATE_LIMIT_EXPENSIVE, scope="tasks")
_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="tasks")
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="tasks")

OLLAMA_CHAT_DISABLED_DETAIL = (
    "The local model is not available on this server. "
    "Connect your own provider API key under Settings > API Keys, "
    "or self-host Maestro with Ollama and a chat model to use it."
)


class _Credentials(NamedTuple):
    """Resolved BYOK material for a task's brain provider."""

    secret: str | None
    base_url: str | None  # set only for the custom OpenAI-compatible provider
    model: str | None


async def _resolve_credentials(
    db: DbSession,
    user_id,  # noqa: ANN001
    provider: LLMProvider,
) -> _Credentials:
    """Return the decrypted key (+ custom endpoint/model) for a provider.

    The local model needs no key. Raises 400 if the provider requires a key and
    the user has none — the task is stopped and the user is warned to connect
    the missing API (CLAUDE.md §9.1).
    """
    if not task_service.requires_api_key(provider):
        return _Credentials(secret=None, base_url=None, model=None)
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.user_id == user_id,
            ApiKey.provider == provider.value,
            ApiKey.is_active.is_(True),
        )
    )
    api_key = result.scalars().first()
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This task requires a '{provider.value}' API key. "
                "Please connect one under Settings > API Keys."
            ),
        )
    return _Credentials(
        secret=decrypt_secret(api_key.encrypted_key),
        base_url=api_key.base_url,
        model=api_key.model,
    )


def _resolve_provider(payload: TaskCreate, user: ActiveUser) -> LLMProvider:
    """Effective brain: explicit payload > user's default brain > local model."""
    if payload.provider is not None:
        provider = payload.provider
    elif user.default_provider:
        provider = LLMProvider(user.default_provider)
    else:
        return LLMProvider.OLLAMA
    if provider not in LLM_CHAT_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider.value}' cannot drive tasks.",
        )
    return provider


@router.post(
    "",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[_start_task_rate_limit],
)
async def start_task(
    payload: TaskCreate, user: VerifiedUser, db: DbSession
) -> TaskCreated:
    """Start a new orchestration task; runs asynchronously in the background.

    This is the only place a task can begin, so it is where quota is enforced.
    """
    await quota_service.enforce_can_start_task(db, user)
    # A custom agent selector must name an agent the caller owns (per-user
    # isolation); the syntax was already checked by the schema validator.
    if payload.domain and is_custom_domain(payload.domain):
        agent_id = payload.domain[len(CUSTOM_DOMAIN_PREFIX) :]
        if await agent_service.get_agent(user.id, agent_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Custom agent not found.",
            )
    provider = _resolve_provider(payload, user)
    if provider is LLMProvider.OLLAMA and not settings.ollama_chat_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=OLLAMA_CHAT_DISABLED_DETAIL,
        )
    # An unset reviewer flag inherits the user's preference (defaults False).
    reviewer_enabled = (
        payload.reviewer_enabled
        if payload.reviewer_enabled is not None
        else user.default_reviewer_enabled
    )
    # Bake the user's saved per-role model preferences into the task's overrides
    # (request wins per role), so model resolution is deterministic on the frozen
    # payload — including on a resumed run, which has no access to the user row.
    merged_models = {
        **(user.model_preferences or {}),
        **(payload.model_overrides or {}),
    }
    payload = payload.model_copy(
        update={
            "provider": provider,
            "reviewer_enabled": reviewer_enabled,
            "model_overrides": merged_models or None,
        }
    )
    creds = await _resolve_credentials(db, user.id, provider)
    task_id = await task_service.start_task(
        user_id=user.id,
        payload=payload,
        api_key=creds.secret,
        base_url=creds.base_url,
        model=creds.model,
    )
    return TaskCreated(task_id=task_id, status=TaskStatus.PENDING)


@router.get("", response_model=TaskListResponse, dependencies=[_read_rate_limit])
async def list_tasks(
    user: ActiveUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TaskListResponse:
    """List the user's tasks, newest first (history sidebar)."""
    summaries, total = await task_service.list_tasks(
        user.id, limit=limit, offset=offset
    )
    return TaskListResponse(
        items=[TaskSummary(**summary) for summary in summaries],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{task_id}", response_model=TaskState, dependencies=[_read_rate_limit])
async def get_task(task_id: str, user: ActiveUser) -> TaskState:
    """Return the current state of a task owned by the user."""
    doc = await task_service.get_task(task_id, user.id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found."
        )
    return TaskState(**doc)


@router.get("/{task_id}/trace", dependencies=[_read_rate_limit])
async def get_task_trace(task_id: str, user: ActiveUser) -> dict:
    """Return the ordered span tree for a task (trace waterfall, §4.5)."""
    spans = await trace_service.get_trace(task_id, user.id)
    if spans is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found."
        )
    return {"task_id": task_id, "spans": spans}


@router.get("/{task_id}/trace/summary", dependencies=[_read_rate_limit])
async def get_task_trace_summary(task_id: str, user: ActiveUser) -> dict:
    """Per-node token/cost rollup for a task's trace (§4.5)."""
    summary = await trace_service.get_trace_summary(task_id, user.id)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found."
        )
    return summary


@router.post(
    "/{task_id}/cancel",
    status_code=status.HTTP_200_OK,
    dependencies=[_write_rate_limit],
)
async def cancel_task(task_id: str, user: ActiveUser) -> dict[str, bool]:
    """Cancel a running task owned by the user."""
    cancelled = await task_service.cancel_task(task_id, user.id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task is not running or does not exist.",
        )
    return {"cancelled": True}


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_write_rate_limit],
)
async def delete_task(task_id: str, user: ActiveUser) -> None:
    """Delete a task (and its logs) owned by the user from the history."""
    deleted = await task_service.delete_task(task_id, user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found."
        )


@router.post(
    "/{task_id}/answer",
    status_code=status.HTTP_200_OK,
    dependencies=[_write_rate_limit],
)
async def answer_task(
    task_id: str, payload: TaskAnswer, user: ActiveUser
) -> dict[str, bool]:
    """Answer an agent's clarifying question (human-in-the-loop, CLAUDE.md §12)."""
    delivered = await task_service.submit_answer(task_id, user.id, payload.answer)
    if not delivered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task is not awaiting an answer.",
        )
    return {"delivered": True}
