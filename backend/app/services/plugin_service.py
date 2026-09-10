"""Plugins: install a bundle of skills, MCP servers and agents in one action.

Two collections. ``plugins`` is the catalog, field-for-field parallel to
``marketplace_items`` — same three projections, same ``$nin`` visibility filter,
same moderation sub-document, so the admin surface works unchanged.
``plugin_installs`` is one row per installed bundle per user, and unlike
``marketplace_installs`` it **does** carry ``user_id``: it records which records
the install created, which is what lets an uninstall know exactly what it owns.

A separate module from ``marketplace_service`` rather than an extension of it.
That service's ``install`` creates one agent in twenty-five lines and its whole
documented story is "installing copies the item into the caller's own account".
This one creates up to twenty-five records across three collections with a
compensating rollback, and bolting that on would put a new set of failure modes
inside the code path the existing marketplace tests pin. What *is* shared is the
shape, and the two things worth sharing in code: ``bucket_install_history`` and
the moderation sub-document.

Three invariants worth stating out loud:

* **A manifest never carries a credential.** The schema has no field for one, so
  it is a 422 rather than a silent drop. An MCP server a plugin creates lands
  with ``encrypted_secret=None`` and, when it needs one, ``enabled=False``.
* **Every member goes through its own service's create function.** Not a direct
  insert — so ``CUSTOM_AGENTS_MAX``, ``AGENT_SKILLS_MAX``, ``MCP_SERVERS_MAX``
  and the injection scan all apply to an install exactly as to the wizard.
* **A partial install leaves nothing behind.** Mongo has no transaction here, so
  a failure compensates by deleting what it created, and the ``plugin_installs``
  row is written *last* — the same ordering argument as ``purge_user_data``
  deleting the PostgreSQL row last.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.constants import (
    AGENT_SKILLS_MAX,
    CUSTOM_AGENTS_MAX,
    MARKETPLACE_COMMUNITY_AUTHOR,
    MCP_SERVERS_MAX,
    PLUGIN_MANIFEST_MAX_BYTES,
    PLUGINS_MAX,
    MarketplaceStatus,
    MongoCollection,
)
from app.core.database import get_mongo_db
from app.schemas.agent import AgentConfigCreate
from app.schemas.mcp_server import McpServerCreate
from app.schemas.plugin import (
    PluginInstallMember,
    PluginManifest,
    PluginUninstallPreview,
)
from app.schemas.skill import SkillCreate
from app.services import (
    agent_service,
    connected_common,
    mcp_service,
    skill_service,
)
from app.utils import prompt_guard
from app.utils.url_guard import check_public_url

logger = logging.getLogger(__name__)

# The author's identity never leaves the service for a non-admin caller, exactly
# as in marketplace_service. The manifest is dropped from list responses too:
# it is large, and the browse view has no use for it.
_PUBLIC_PROJECTION = {"_id": 0, "author_id": 0, "manifest": 0}
_DETAIL_PROJECTION = {"_id": 0, "author_id": 0}
_ADMIN_PROJECTION = {"_id": 0}

# `$nin` also matches a document with no `status` field, so an entry written
# before the field existed stays visible rather than silently vanishing.
_VISIBLE_FILTER = {
    "status": {
        "$nin": [MarketplaceStatus.HIDDEN.value, MarketplaceStatus.REMOVED.value]
    }
}


class PluginValidationError(ValueError):
    """Raised when a manifest or an install fails validation."""


class PluginSecurityError(ValueError):
    """Raised when a manifest fails the mandatory security scan."""


def _collection():
    return get_mongo_db()[MongoCollection.PLUGINS.value]


def _installs():
    return get_mongo_db()[MongoCollection.PLUGIN_INSTALLS.value]


def manifest_digest(manifest: PluginManifest) -> str:
    """A stable fingerprint of a bundle's content.

    Sorted keys and no whitespace, so the same manifest formatted two ways
    digests identically. Stored on the install so a re-import that yields a
    different digest can be reported as "this changed since you installed it".
    """
    payload = json.dumps(
        manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _scan(manifest: PluginManifest) -> None:
    """Reject a bundle any of whose text trips the injection scanner.

    All or nothing, unlike a skill dropped at load time or an MCP tool withheld
    at discovery. Those are one attachment among several in an account the user
    already controls; a bundle is a single thing a user chose to trust, and
    "installed, but three of its parts are missing" is not a state anyone can
    reason about. Mirrors ``marketplace_service._security_scan``.
    """
    texts: list[str] = [manifest.name, manifest.description, manifest.author]
    for skill in manifest.skills:
        texts += [skill.name, skill.description, skill.instructions]
    for server in manifest.mcp_servers:
        texts += [server.name, server.description]
    for agent in manifest.agents:
        texts += [agent.name, agent.description, agent.system_prompt]
    for text in texts:
        if text and prompt_guard.scan_prompt(text):
            raise PluginSecurityError(
                "This plugin failed the mandatory security scan "
                "(possible prompt injection)."
            )


# --- the catalog ------------------------------------------------------------


async def list_plugins(limit: int = 50) -> list[dict[str, Any]]:
    """Published bundles, newest first. Never the author, never the manifest."""
    cursor = (
        _collection()
        .find(_VISIBLE_FILTER, _PUBLIC_PROJECTION)
        .sort("created_at", -1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def get_plugin(catalog_id: str) -> dict[str, Any] | None:
    """One visible catalog entry, with its manifest, or None."""
    return await _collection().find_one(
        {"id": catalog_id, **_VISIBLE_FILTER}, _DETAIL_PROJECTION
    )


async def publish(user_id: uuid.UUID, manifest: PluginManifest) -> dict[str, Any]:
    """Publish a bundle. The security scan is never skipped (CLAUDE.md §9.3)."""
    _scan(manifest)
    now = datetime.now(UTC)
    doc = {
        "id": str(uuid.uuid4()),
        "author_id": str(user_id),
        "plugin_id": manifest.id,
        "name": manifest.name,
        "description": manifest.description,
        "version": manifest.version,
        "manifest": manifest.model_dump(mode="json"),
        "manifest_digest": manifest_digest(manifest),
        "installs": 0,
        # A literal, like marketplace_service: MarketplacePublish has no such
        # field, so an author cannot promote themselves.
        "featured": False,
        "author_label": MARKETPLACE_COMMUNITY_AUTHOR,
        "security_scan": {"status": "passed", "findings": [], "scanned_at": now},
        "status": MarketplaceStatus.PUBLISHED.value,
        "created_at": now,
        "updated_at": now,
    }
    await _collection().insert_one(dict(doc))
    return {k: v for k, v in doc.items() if k not in ("author_id", "manifest")}


# --- installing -------------------------------------------------------------


async def _preflight(user_id: uuid.UUID, manifest: PluginManifest) -> None:
    """Refuse a bundle that cannot fit, before anything is written.

    Every insert point enforces its own cap anyway — that is the contract that
    makes a one-click install unable to route around the wizard's limits. This
    exists so the refusal is one useful message instead of a half-built install
    that fails on its ninth record.
    """
    installed = await _installs().count_documents({"user_id": str(user_id)})
    if installed >= PLUGINS_MAX:
        raise PluginValidationError(
            f"You can have at most {PLUGINS_MAX} plugins installed."
        )

    for label, wanted, ceiling, existing in (
        (
            "skills",
            len(manifest.skills),
            AGENT_SKILLS_MAX,
            len(await skill_service.list_skills(user_id)),
        ),
        (
            "MCP servers",
            len(manifest.mcp_servers),
            MCP_SERVERS_MAX,
            len(await mcp_service.list_servers(user_id)),
        ),
        (
            "agents",
            len(manifest.agents),
            CUSTOM_AGENTS_MAX,
            len(await agent_service.list_agents(user_id)),
        ),
    ):
        if existing + wanted > ceiling:
            raise PluginValidationError(
                f"This plugin needs {wanted} {label} and you can hold "
                f"{ceiling - existing} more. Remove some first."
            )


def _unique_slug(slug: str, taken: set[str]) -> str:
    """A free slug near ``slug``, or raise if there is no room nearby.

    Suffixed rather than refused, because a slug collision between two unrelated
    plugins is the user's bad luck rather than their mistake. Bounded at 9 so a
    pathological account cannot turn an install into a scan.
    """
    if slug not in taken:
        return slug
    for suffix in range(2, 10):
        candidate = f"{slug}-{suffix}"
        if candidate not in taken:
            return candidate
    raise PluginValidationError(
        f"You already have too many records named like '{slug}'."
    )


async def _rollback(user_id: uuid.UUID, created: dict[str, list[str]]) -> None:
    """Undo a partial install. Best effort per record, never raises.

    Mongo has no transaction here, so this is compensation rather than a
    rollback. It runs before the ``plugin_installs`` row exists, which is why
    the ids are held in memory: there is nothing on disk to read them back from.
    """
    for skill_id in created["skills"]:
        try:
            await skill_service.delete_skill(user_id, skill_id)
        except Exception:  # noqa: BLE001 - compensation must not mask the cause
            logger.warning("Rollback could not delete skill %s", skill_id)
    for server_id in created["mcp_servers"]:
        try:
            await mcp_service.delete_server(user_id, server_id)
        except Exception:  # noqa: BLE001
            logger.warning("Rollback could not delete MCP server %s", server_id)
    for agent_id in created["agents"]:
        try:
            await agent_service.delete_agent(user_id, agent_id)
        except Exception:  # noqa: BLE001
            logger.warning("Rollback could not delete agent %s", agent_id)


async def install(
    user_id: uuid.UUID,
    manifest: PluginManifest,
    *,
    source: str,
    catalog_item_id: str | None = None,
    origin_url: str | None = None,
) -> dict[str, Any]:
    """Create every member of a bundle in the caller's own account."""
    _scan(manifest)
    await _preflight(user_id, manifest)

    if await _installs().find_one({"user_id": str(user_id), "plugin_id": manifest.id}):
        raise PluginValidationError(
            f"'{manifest.name}' is already installed. Remove it first to reinstall."
        )

    created: dict[str, list[str]] = {"skills": [], "mcp_servers": [], "agents": []}
    skill_ids: dict[str, str] = {}
    server_ids: dict[str, str] = {}
    needs_credentials: list[str] = []
    plugin_row_id = str(uuid.uuid4())

    try:
        taken = {doc["slug"] for doc in await skill_service.list_skills(user_id)}
        for member in manifest.skills:
            slug = _unique_slug(member.slug, taken)
            taken.add(slug)
            record = await skill_service.create_skill(
                user_id,
                SkillCreate(**{**member.model_dump(), "slug": slug}),
                source="plugin",
                plugin_id=plugin_row_id,
            )
            skill_ids[member.slug] = record["id"]
            created["skills"].append(record["id"])

        taken = {doc["slug"] for doc in await mcp_service.list_servers(user_id)}
        for member in manifest.mcp_servers:
            slug = _unique_slug(member.slug, taken)
            taken.add(slug)
            # No secret, and disabled when one is needed. A manifest cannot
            # carry a credential, so a credentialed server would otherwise be
            # installed in a state where every call fails for an unclear reason.
            record = await mcp_service.create_server(
                user_id,
                McpServerCreate(
                    **{**member.model_dump(), "slug": slug},
                    secret=None,
                    enabled=member.auth_mode == "none",
                ),
                source="plugin",
                plugin_id=plugin_row_id,
            )
            server_ids[member.slug] = record["id"]
            created["mcp_servers"].append(record["id"])
            if member.auth_mode != "none":
                needs_credentials.append(record["id"])

        for member in manifest.agents:
            record = await agent_service.create_agent(
                user_id,
                AgentConfigCreate(
                    name=member.name,
                    domain=member.domain,
                    system_prompt=member.system_prompt,
                    tools=member.tools,
                    description=member.description,
                    routing_hint=member.routing_hint,
                    output_format=member.output_format,
                    routable=member.routable,
                    # A plugin's own records, resolved from manifest slugs.
                    # Never an id the manifest could have named directly: that
                    # is what stops a bundle attaching a record it does not own.
                    skill_ids=[skill_ids[s] for s in member.skill_slugs],
                    mcp_server_ids=[server_ids[s] for s in member.mcp_server_slugs],
                    custom_api_tool_ids=[],
                ),
                source="plugin",
                plugin_id=plugin_row_id,
            )
            created["agents"].append(record["id"])
    except Exception:
        await _rollback(user_id, created)
        raise

    now = datetime.now(UTC)
    doc = {
        "id": plugin_row_id,
        "user_id": str(user_id),
        "plugin_id": manifest.id,
        "name": manifest.name,
        "version": manifest.version,
        "source": source,
        "catalog_item_id": catalog_item_id,
        "origin_url": origin_url,
        "manifest_digest": manifest_digest(manifest),
        "created_skill_ids": created["skills"],
        "created_mcp_server_ids": created["mcp_servers"],
        "created_agent_ids": created["agents"],
        "needs_credentials": needs_credentials,
        "installed_at": now,
        "updated_at": now,
    }
    try:
        # Written last on purpose. Until this row exists the install is not
        # claimed, so a crash before it leaves records the rollback above owns
        # rather than a half-registered plugin nobody can remove.
        await _installs().insert_one(dict(doc))
    except DuplicateKeyError as exc:
        await _rollback(user_id, created)
        raise PluginValidationError(f"'{manifest.name}' is already installed.") from exc

    if catalog_item_id:
        await _collection().update_one(
            {"id": catalog_item_id}, {"$inc": {"installs": 1}}
        )
    return {k: v for k, v in doc.items() if k != "user_id"}


async def install_from_catalog(
    user_id: uuid.UUID, catalog_id: str
) -> dict[str, Any] | None:
    """Install a published bundle."""
    item = await get_plugin(catalog_id)
    if item is None:
        return None
    manifest = PluginManifest(**item["manifest"])
    return await install(
        user_id, manifest, source="catalog", catalog_item_id=catalog_id
    )


async def fetch_manifest(url: str) -> PluginManifest:
    """Read a manifest from a URL the user supplied. Never raises unexpectedly.

    Categorically riskier than a catalog install: this bundle has not passed
    Maestro's publish scan, has seen no moderation, and can change at any time.
    That is why it sits behind its own switch, and why the confirmation screen
    shows the host verbatim.

    ``url_guard`` runs here for the third time — schema, route, and now, because
    a URL the user typed a moment ago can still resolve somewhere else by the
    time it is fetched.
    """
    if settings.llm_ssrf_guard_enabled:
        reason = await check_public_url(url)
        if reason is not None:
            raise PluginValidationError(f"Manifest URL rejected: {reason}.")

    result = await connected_common.request_api(
        url,
        method="GET",
        timeout=float(settings.plugin_import_timeout_seconds),
        max_bytes=PLUGIN_MANIFEST_MAX_BYTES,
        log_target=urlsplit(url).netloc or "<manifest host>",
    )
    if result.oversized:
        raise PluginValidationError("That manifest is too large to read.")
    if result.data is None:
        raise PluginValidationError("That URL did not return a readable JSON manifest.")
    try:
        return PluginManifest(**result.data)
    except ValidationError as exc:
        # The first error only: a full pydantic dump of a stranger's document is
        # a lot of their text echoed back into our UI.
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        raise PluginValidationError(
            f"That manifest is not valid: {location} — {first['msg']}"
        ) from exc


# --- installed bundles ------------------------------------------------------


async def list_installs(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """The user's installed bundles, newest first."""
    cursor = (
        _installs()
        .find({"user_id": str(user_id)}, {"_id": 0, "user_id": 0})
        .sort("installed_at", -1)
        .limit(PLUGINS_MAX)
    )
    return [doc async for doc in cursor]


async def get_install(user_id: uuid.UUID, install_id: str) -> dict[str, Any] | None:
    return await _installs().find_one(
        {"id": install_id, "user_id": str(user_id)}, {"_id": 0, "user_id": 0}
    )


def _edited(record: dict[str, Any], installed_at: datetime) -> bool:
    updated = record.get("updated_at")
    if not isinstance(updated, datetime) or not isinstance(installed_at, datetime):
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    if installed_at.tzinfo is None:
        installed_at = installed_at.replace(tzinfo=UTC)
    # A one-second grace: the records are written moments apart during the
    # install itself, and reporting all of them as "edited" would make the
    # warning meaningless on the very first uninstall.
    return (updated - installed_at).total_seconds() > 1


async def uninstall_preview(
    user_id: uuid.UUID, install_id: str
) -> PluginUninstallPreview | None:
    """Everything a delete would remove, so the confirmation can list it.

    Records the user edited after installing are flagged. That is the whole
    point of asking first: deleting an agent whose prompt someone rewrote is
    destructive in a way an "Uninstall" button does not communicate on its own.
    """
    row = await get_install(user_id, install_id)
    if row is None:
        return None
    installed_at = row.get("installed_at")
    members: list[PluginInstallMember] = []

    for kind, ids, fetch in (
        ("skill", row.get("created_skill_ids", []), skill_service.get_skill),
        ("mcp_server", row.get("created_mcp_server_ids", []), mcp_service.get_server),
        ("agent", row.get("created_agent_ids", []), agent_service.get_agent),
    ):
        for record_id in ids:
            record = await fetch(user_id, record_id)
            if record is None:
                continue  # Already deleted by hand; nothing to warn about.
            members.append(
                PluginInstallMember(
                    kind=kind,
                    id=record_id,
                    name=record.get("name", record_id),
                    edited=_edited(record, installed_at),
                )
            )
    return PluginUninstallPreview(
        plugin_id=row["plugin_id"], name=row["name"], members=members
    )


async def uninstall(user_id: uuid.UUID, install_id: str) -> bool:
    """Delete a bundle and everything it created. Returns False if not found.

    Only records that still carry *this* install's ``plugin_id`` are removed.
    That guard is what makes the delete safe: a record the user detached, or one
    another plugin has since adopted, survives.
    """
    row = await get_install(user_id, install_id)
    if row is None:
        return False

    for ids, fetch, delete in (
        (
            row.get("created_skill_ids", []),
            skill_service.get_skill,
            skill_service.delete_skill,
        ),
        (
            row.get("created_mcp_server_ids", []),
            mcp_service.get_server,
            mcp_service.delete_server,
        ),
        (
            row.get("created_agent_ids", []),
            agent_service.get_agent,
            agent_service.delete_agent,
        ),
    ):
        for record_id in ids:
            record = await fetch(user_id, record_id)
            if record is None or record.get("plugin_id") != install_id:
                continue
            await delete(user_id, record_id)

    await _installs().delete_one({"id": install_id, "user_id": str(user_id)})
    return True


# --- admin ------------------------------------------------------------------


async def admin_list_plugins(limit: int = 100) -> list[dict[str, Any]]:
    """Every catalog entry, whatever its status, with the author id."""
    cursor = (
        _collection().find({}, _ADMIN_PROJECTION).sort("created_at", -1).limit(limit)
    )
    return [doc async for doc in cursor]


async def admin_set_status(
    catalog_id: str,
    status: MarketplaceStatus,
    *,
    moderator_id: uuid.UUID,
    reason: str,
) -> dict[str, Any] | None:
    """Hide, remove or reinstate a catalog entry.

    A taken-down entry stops being installable. **Copies already installed keep
    working** — the records live in the installer's own account and are theirs.
    That is the same behaviour a taken-down marketplace agent has, and it is
    stated here because the opposite is easy to assume.
    """
    result = await _collection().update_one(
        {"id": catalog_id},
        {
            "$set": {
                "status": status.value,
                "moderation": {
                    "actor_id": str(moderator_id),
                    "reason": reason,
                    "at": datetime.now(UTC),
                },
                "updated_at": datetime.now(UTC),
            }
        },
    )
    if result.matched_count == 0:
        return None
    return await _collection().find_one({"id": catalog_id}, _ADMIN_PROJECTION)
