"""Agent skills: reusable instruction bundles (MongoDB ``agent_skills``).

A skill is the third thing a user can attach to their own agent, after catalog
tools and registered HTTP endpoints — and the only one that carries no runtime
at all. It contributes a delimited block to the subagent's system prompt and
nothing else: no action id, no budget, no outbound reach.

Stored in its own collection rather than as fields on the agent document, for
the reasons ``custom_api_service`` lists: one skill attaches to several agents,
so embedding means N copies and N-way editing, and the agent document then
carries only *ids*, which is what makes a marketplace publish unable to move a
skill between accounts.

Two contracts:

* **Write-time gate.** :func:`create_skill` is the single insert point —
  marketplace installs and plugin installs included — so it is where
  ``AGENT_SKILLS_MAX`` and the injection scan are enforced.
* **Load-time re-scan.** :func:`load_skills` never raises and re-runs
  ``prompt_guard`` with the *current* pattern set on every load, so nothing is
  grandfathered by having been clean when it was written. A skill that trips the
  scanner is dropped from that run rather than failing the task: an agent losing
  one of five bundles is a degraded answer, while a hard failure would take the
  whole task down over text the agent may not even need.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.constants import AGENT_SKILLS_MAX, MongoCollection
from app.core.database import get_mongo_db
from app.schemas.skill import SkillCreate, SkillUpdate
from app.utils import prompt_guard

logger = logging.getLogger(__name__)

# ``_id`` is Mongo's own; ``user_id`` is never echoed to a caller. There is no
# ciphertext to hide here, unlike custom_api_tools -- a skill holds no secret.
_PUBLIC_PROJECTION = {"_id": 0, "user_id": 0}

# The fields whose change makes a stored skill a different bundle, and so bumps
# ``version``. Renaming or re-describing one does not: a plugin upgrade diffs on
# content, and a cosmetic edit should not read as a new revision.
_VERSIONED_FIELDS = ("instructions", "output_format", "required_tools")


class SkillValidationError(ValueError):
    """Raised when a skill fails validation or its security scan."""


@dataclass(frozen=True, slots=True)
class Skill:
    """One loaded, re-scanned skill, ready to be rendered into a prompt.

    Deliberately has no ``repr=False`` field, unlike ``CustomApiTool``: a skill
    holds no credential, so there is nothing to keep out of a traceback. The
    absence is documented rather than silent so nobody adds a secret here later
    and inherits a permissive ``repr``.
    """

    id: str
    slug: str
    name: str
    description: str
    instructions: str
    output_format: str
    required_tools: tuple[str, ...]
    version: int


def _collection():
    return get_mongo_db()[MongoCollection.AGENT_SKILLS.value]


def _guard_text(*values: str) -> None:
    """Reject text that trips the injection scanner.

    The same gate ``agent_service._guard_prompt`` applies to a system prompt,
    for the same reason: this text ends up inside one.
    """
    for value in values:
        if value and prompt_guard.scan_prompt(value):
            raise SkillValidationError(
                "The skill failed the security scan (possible prompt injection)."
            )


def _public(doc: dict[str, Any]) -> dict[str, Any]:
    """Shape a stored document for a response.

    Flattens ``security_scan`` into the one boolean the API exposes. The stored
    ``passed`` alone would always be ``True`` — a failing bundle never gets
    written — so it is only trusted while the stamped scanner version still
    matches. After a ``SCANNER_VERSION`` bump the text is re-scanned here, which
    is what makes the flag agree with what :func:`load_skills` will actually do
    at run time. That re-scan costs nothing on the common path, because the
    versions match until someone changes the pattern set.
    """
    shaped = {k: v for k, v in doc.items() if k not in ("_id", "user_id")}
    scan = shaped.pop("security_scan", None) or {}
    if scan.get("version") == prompt_guard.SCANNER_VERSION:
        passed = bool(scan.get("passed", True))
    else:
        passed = not (
            prompt_guard.scan_prompt(shaped.get("instructions", ""))
            or prompt_guard.scan_prompt(shaped.get("name", ""))
        )
    shaped["security_scan_passed"] = passed
    return shaped


def _to_skill(doc: dict[str, Any]) -> Skill:
    return Skill(
        id=doc["id"],
        slug=doc.get("slug", ""),
        name=doc.get("name", ""),
        description=doc.get("description", ""),
        instructions=doc.get("instructions", ""),
        output_format=doc.get("output_format", ""),
        required_tools=tuple(doc.get("required_tools") or ()),
        version=int(doc.get("version", 1)),
    )


# --- CRUD ------------------------------------------------------------------


async def list_skills(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """The user's skills, newest first."""
    cursor = (
        _collection()
        .find({"user_id": str(user_id)}, _PUBLIC_PROJECTION)
        .sort("created_at", -1)
        .limit(AGENT_SKILLS_MAX)
    )
    return [_public(doc) async for doc in cursor]


async def get_skill(user_id: uuid.UUID, skill_id: str) -> dict[str, Any] | None:
    """One skill owned by the user, or None."""
    doc = await _collection().find_one(
        {"id": skill_id, "user_id": str(user_id)}, _PUBLIC_PROJECTION
    )
    return None if doc is None else _public(doc)


async def get_skill_ids(user_id: uuid.UUID, skill_ids: list[str]) -> set[str]:
    """Which of ``skill_ids`` this user actually owns.

    The ownership gate for attaching a skill to an agent: a caller naming
    someone else's id gets a validation error rather than a silent attach.
    """
    if not skill_ids:
        return set()
    cursor = _collection().find(
        {"user_id": str(user_id), "id": {"$in": skill_ids}}, {"_id": 0, "id": 1}
    )
    return {doc["id"] async for doc in cursor}


async def get_required_tools(
    user_id: uuid.UUID, skill_ids: list[str]
) -> dict[str, list[str]]:
    """The advisory tool requirements of the named skills, keyed by skill id.

    Projected down to two fields because the only caller
    (``agent_service.annotate_missing_tools``) needs nothing else, and it runs on
    every agent read.
    """
    if not skill_ids:
        return {}
    cursor = _collection().find(
        {"user_id": str(user_id), "id": {"$in": skill_ids}},
        {"_id": 0, "id": 1, "required_tools": 1},
    )
    return {doc["id"]: list(doc.get("required_tools") or []) async for doc in cursor}


async def create_skill(
    user_id: uuid.UUID,
    payload: SkillCreate,
    *,
    source: str = "custom",
    marketplace_item_id: str | None = None,
    plugin_id: str | None = None,
) -> dict[str, Any]:
    """Create and persist a validated skill.

    The single insert point, marketplace and plugin installs included, so it is
    where ``AGENT_SKILLS_MAX`` is enforced — a one-click install must not be the
    way around a cap the wizard respects (the argument
    ``agent_service.create_agent`` makes for custom agents).
    """
    _guard_text(payload.name, payload.description, payload.instructions)

    owned = await _collection().count_documents({"user_id": str(user_id)})
    if owned >= AGENT_SKILLS_MAX:
        raise SkillValidationError(
            f"You can own at most {AGENT_SKILLS_MAX} skills. Delete one to make room."
        )
    # Explicit, because the unique index is built best-effort at startup and is
    # allowed to be missing (core/database.ensure_indexes swallows failures).
    if await _collection().find_one({"user_id": str(user_id), "slug": payload.slug}):
        raise SkillValidationError(
            f"You already have a skill with the slug '{payload.slug}'."
        )

    now = datetime.now(UTC)
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": str(user_id),
        "slug": payload.slug,
        "name": payload.name,
        "description": payload.description,
        "instructions": payload.instructions,
        "output_format": payload.output_format,
        "required_tools": payload.required_tools,
        "version": 1,
        "source": source,
        "marketplace_item_id": marketplace_item_id,
        "plugin_id": plugin_id,
        "security_scan": {"version": prompt_guard.SCANNER_VERSION, "passed": True},
        "created_at": now,
        "updated_at": now,
    }
    try:
        await _collection().insert_one(dict(doc))
    except DuplicateKeyError as exc:
        # The checks above are read-then-write, so two concurrent POSTs can both
        # pass them. The unique index is the authoritative gate; this translates
        # its error into the same message the friendly path produces.
        raise SkillValidationError(
            f"You already have a skill with the slug '{payload.slug}'."
        ) from exc
    return _public(doc)


async def update_skill(
    user_id: uuid.UUID, skill_id: str, payload: SkillUpdate
) -> dict[str, Any] | None:
    """Apply a partial update to a user-owned skill; returns the new state."""
    changes: dict[str, Any] = {}
    if payload.name is not None:
        changes["name"] = payload.name
    if payload.description is not None:
        changes["description"] = payload.description
    if payload.instructions is not None:
        changes["instructions"] = payload.instructions
    if payload.output_format is not None:
        changes["output_format"] = payload.output_format
    if payload.required_tools is not None:
        changes["required_tools"] = payload.required_tools

    _guard_text(
        changes.get("name", ""),
        changes.get("description", ""),
        changes.get("instructions", ""),
    )
    if not changes:
        return await get_skill(user_id, skill_id)

    if payload.instructions is not None:
        # Re-record the passing scan under the current scanner version, so a
        # later scanner bump is what forces a re-scan rather than an edit.
        changes["security_scan"] = {
            "version": prompt_guard.SCANNER_VERSION,
            "passed": True,
        }
    changes["updated_at"] = datetime.now(UTC)

    update: dict[str, Any] = {"$set": changes}
    if any(field in changes for field in _VERSIONED_FIELDS):
        update["$inc"] = {"version": 1}
    result = await _collection().update_one(
        {"id": skill_id, "user_id": str(user_id)}, update
    )
    if result.matched_count == 0:
        return None
    return await get_skill(user_id, skill_id)


async def delete_skill(user_id: uuid.UUID, skill_id: str) -> bool:
    """Delete a user-owned skill. Returns True if one was removed."""
    result = await _collection().delete_one({"id": skill_id, "user_id": str(user_id)})
    return result.deleted_count > 0


# --- Engine edge -----------------------------------------------------------


async def load_skills(
    user_id: uuid.UUID, skill_ids: list[str] | None = None
) -> tuple[Skill, ...]:
    """Load and re-scan a user's skills. Never raises.

    Called once per task run at the engine edge, alongside
    ``custom_api_service.load_tools``, so the agent layer receives plain values
    and never touches the database.

    Every bundle is re-scanned with the *current* ``prompt_guard`` patterns, not
    the ones that passed at write time — the same non-grandfathering rule
    ``registry.resolve_domain_info`` applies to a custom agent's own prompt. The
    difference is what a failure means: a poisoned agent prompt makes the agent
    unrunnable, while a poisoned skill is one attachment among several, so it is
    dropped and logged by slug rather than failing the run.

    ``skill_ids`` restricts the load to the ids an agent attached; the
    ``user_id`` filter still applies, so an id belonging to someone else
    resolves to nothing.
    """
    query: dict[str, Any] = {"user_id": str(user_id)}
    if skill_ids is not None:
        if not skill_ids:
            return ()
        query["id"] = {"$in": skill_ids}
    try:
        cursor = _collection().find(query).limit(AGENT_SKILLS_MAX)
        docs = [doc async for doc in cursor]
    except Exception:  # noqa: BLE001 - a DB hiccup must not fail the task
        logger.warning("Could not load agent skills", exc_info=True)
        return ()

    skills: list[Skill] = []
    for doc in docs:
        try:
            skill = _to_skill(doc)
        except Exception:  # noqa: BLE001 - a malformed document skips, not fails
            logger.warning("Skipping malformed skill %s", doc.get("slug"))
            continue
        if prompt_guard.scan_prompt(skill.instructions) or prompt_guard.scan_prompt(
            skill.name
        ):
            # Slug only. The matched pattern would tell a caller which heuristic
            # to write around, and the instructions are the payload itself.
            logger.warning(
                "Withholding skill %s: failed the injection scan", skill.slug
            )
            continue
        skills.append(skill)
    return tuple(skills)
