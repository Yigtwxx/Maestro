"""Task endpoints: start, poll status, cancel."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.constants import LLMProvider, TaskStatus
from app.core.deps import CurrentUser, DbSession
from app.core.security import decrypt_secret
from app.models.api_key import ApiKey
from app.schemas.task import TaskAnswer, TaskCreate, TaskCreated, TaskState
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


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


@router.post("", response_model=TaskCreated, status_code=status.HTTP_202_ACCEPTED)
async def start_task(
    payload: TaskCreate, user: CurrentUser, db: DbSession
) -> TaskCreated:
    """Start a new orchestration task; runs asynchronously in the background."""
    api_key = await _resolve_api_key(db, user.id, payload.provider)
    task_id = await task_service.start_task(
        user_id=user.id, payload=payload, api_key=api_key
    )
    return TaskCreated(task_id=task_id, status=TaskStatus.PENDING)


@router.get("/{task_id}", response_model=TaskState)
async def get_task(task_id: str, user: CurrentUser) -> TaskState:
    """Return the current state of a task owned by the user."""
    doc = await task_service.get_task(task_id, user.id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found."
        )
    return TaskState(**doc)


@router.post("/{task_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_task(task_id: str, user: CurrentUser) -> dict[str, bool]:
    """Cancel a running task owned by the user."""
    cancelled = await task_service.cancel_task(task_id, user.id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task is not running or does not exist.",
        )
    return {"cancelled": True}


@router.post("/{task_id}/answer", status_code=status.HTTP_200_OK)
async def answer_task(
    task_id: str, payload: TaskAnswer, user: CurrentUser
) -> dict[str, bool]:
    """Answer an agent's clarifying question (human-in-the-loop, CLAUDE.md §12)."""
    delivered = await task_service.submit_answer(task_id, user.id, payload.answer)
    if not delivered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task is not awaiting an answer.",
        )
    return {"delivered": True}
