"""Task endpoints: start, poll status, cancel."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.constants import (
    LLM_CHAT_PROVIDERS,
    RATE_LIMIT_EXPENSIVE,
    RATE_LIMIT_READ,
    RATE_LIMIT_WRITE,
    LLMProvider,
    TaskStatus,
)
from app.core.deps import ActiveUser, DbSession
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
from app.services import quota_service, task_service
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Starting a task is the expensive path; throttle it independently.
_start_task_rate_limit = rate_limit(RATE_LIMIT_EXPENSIVE, scope="tasks")
_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="tasks")
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="tasks")


async def _resolve_api_key(db: DbSession, user_id, provider: LLMProvider) -> str | None:  # noqa: ANN001
    """Return the decrypted BYOK key for a provider, or None for the free tier.

    Raises 400 if the provider requires a key and the user has none — the task
    is stopped and the user is warned to connect the missing API (CLAUDE.md §9.1).
    """
    if not task_service.requires_api_key(provider):
        return None
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
    return decrypt_secret(api_key.encrypted_key)


def _resolve_provider(payload: TaskCreate, user: ActiveUser) -> LLMProvider:
    """Effective brain: explicit payload > user's default brain > free tier."""
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
    payload: TaskCreate, user: ActiveUser, db: DbSession
) -> TaskCreated:
    """Start a new orchestration task; runs asynchronously in the background.

    This is the only place a task can begin, so it is where quota is enforced.
    """
    await quota_service.enforce_can_start_task(db, user)
    provider = _resolve_provider(payload, user)
    payload = payload.model_copy(update={"provider": provider})
    api_key = await _resolve_api_key(db, user.id, provider)
    task_id = await task_service.start_task(
        user_id=user.id, payload=payload, api_key=api_key
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
