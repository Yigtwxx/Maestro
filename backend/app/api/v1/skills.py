"""Agent skill endpoints: reusable instruction bundles a user attaches to agents.

The write paths require a verified account, mirroring ``custom_api_tools``: both
store text or configuration that a *later* run feeds to a model, so both are
abuse-sensitive in the way ``deps.get_verified_user`` exists for. Reads and
deletes stay on ``ActiveUser`` — neither creates anything.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.constants import RATE_LIMIT_READ, RATE_LIMIT_WRITE
from app.core.deps import ActiveUser, VerifiedUser
from app.schemas.skill import SkillCreate, SkillPublic, SkillUpdate
from app.services import skill_service
from app.services.skill_service import SkillValidationError
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/skills", tags=["skills"])

_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="skills")
# Writes run the bundle through the injection scanner.
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="skills")


@router.get("", response_model=list[SkillPublic], dependencies=[_read_rate_limit])
async def list_skills(user: ActiveUser) -> list[dict]:
    """List the current user's skills, newest first."""
    return await skill_service.list_skills(user.id)


@router.post(
    "",
    response_model=SkillPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_write_rate_limit],
)
async def create_skill(payload: SkillCreate, user: VerifiedUser) -> dict:
    """Create a skill this user's agents may attach."""
    try:
        return await skill_service.create_skill(user.id, payload)
    except SkillValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get("/{skill_id}", response_model=SkillPublic, dependencies=[_read_rate_limit])
async def get_skill(skill_id: str, user: ActiveUser) -> dict:
    """Return one of the user's skills."""
    skill = await skill_service.get_skill(user.id, skill_id)
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found."
        )
    return skill


@router.patch(
    "/{skill_id}", response_model=SkillPublic, dependencies=[_write_rate_limit]
)
async def update_skill(skill_id: str, payload: SkillUpdate, user: VerifiedUser) -> dict:
    """Update one skill. Changing its content bumps the stored version."""
    try:
        skill = await skill_service.update_skill(user.id, skill_id, payload)
    except SkillValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found."
        )
    return skill


@router.delete(
    "/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_write_rate_limit],
)
async def delete_skill(skill_id: str, user: ActiveUser) -> None:
    """Delete one of the user's skills.

    Agents that attached it keep the id in their ``skill_ids``; the runtime
    intersects against what actually loaded, so a deleted skill simply stops
    contributing rather than breaking the agent.
    """
    if not await skill_service.delete_skill(user.id, skill_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found."
        )
