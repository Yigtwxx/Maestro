"""Remote MCP servers, exposed to their owner's agents as tools.

Stored in MongoDB (``mcp_servers``), one collection rather than fields on the
agent document, for the reasons ``custom_api_service`` gives: a server attaches
to several agents, embedding means N copies and N-way rotation, and the agent
document then carries only *ids*, which is what makes a marketplace publish
unable to move a server between accounts.

Three contracts, the first two shared with ``custom_api_service``:

* **Never raises out of the tool path.** ``subagent._execute`` has no
  ``try/except``, so an exception escaping :func:`call` fails the whole subtask.
  Every failure becomes a sentence the model can act on.
* **Never leaks.** :class:`McpServer` keeps its secret out of ``repr``; every
  read used for a response projects the ciphertext away; the decrypted value is
  applied at request-build time and never reaches a log or an event payload.
* **The catalog is cached, and sanitized before it is cached.** This is the new
  one, and it is a security property rather than a performance one. A tool's
  ``description`` and ``inputSchema`` are written by a third party and land in a
  subagent's *system prompt*; caching means that text is scanned and rebuilt
  once, at a bounded moment, instead of a live attacker-controlled string
  reaching a prompt on every task. See :func:`sanitize_tool`.

What is deliberately *not* supported: OAuth. A server needing a full OAuth 2.1
flow cannot be registered, only one accepting a static bearer or header token.
Retrofitting OAuth means a token store, refresh and a callback route — a feature
of its own, not a flag here.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.constants import (
    MCP_ACTION_MAX_CHARS,
    MCP_ACTION_PREFIX,
    MCP_ITEM_MAX_CHARS,
    MCP_LIST_PAGES_MAX,
    MCP_MAX_ENUM_VALUES,
    MCP_MAX_ITEMS,
    MCP_MAX_PARAMETERS,
    MCP_PREVIEW_MAX_CHARS,
    MCP_RESULT_CLOSE,
    MCP_RESULT_MAX_CHARS,
    MCP_RESULT_OPEN,
    MCP_SCHEMA_DESCRIPTION_MAX_CHARS,
    MCP_SCHEMA_KEYWORDS,
    MCP_SCHEMA_MAX_DEPTH,
    MCP_SERVERS_MAX,
    MCP_TOOL_DESCRIPTION_MAX_CHARS,
    MCP_TOOL_NAME_PATTERN,
    MCP_TOOL_TITLE_MAX_CHARS,
    MCP_TOOLS_CACHE_TTL_SECONDS,
    MCP_TOOLS_PER_SERVER_MAX,
    MongoCollection,
)
from app.core.database import get_mongo_db
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.schemas.mcp_server import (
    McpDiscoverResult,
    McpServerCreate,
    McpServerUpdate,
    McpToolPublic,
)
from app.services import connected_common, mcp_transport
from app.utils import prompt_guard

logger = logging.getLogger(__name__)

# Never returned to a caller and never logged. Belt (this projection) and braces
# (the explicit McpServerPublic field list).
_PUBLIC_PROJECTION = {"_id": 0, "user_id": 0, "encrypted_secret": 0}

# The JSON Schema types the rebuild will emit. Anything else — an inline object,
# a tuple-typed array, a $ref — drops the property, and a *required* property
# dropping withholds the whole tool.
_SCALAR_TYPES = frozenset({"string", "integer", "number", "boolean"})

_TOOL_NAME_RE = re.compile(MCP_TOOL_NAME_PATTERN)


class McpValidationError(ValueError):
    """Raised when a server registration fails validation."""


@dataclass(frozen=True, slots=True)
class McpTool:
    """One remote tool, already sanitized at discovery. Carries no credential."""

    action: str
    # The server's own spelling, verbatim: this is what ``tools/call`` sends.
    remote_name: str
    display_name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class McpServer:
    """One registered server, resolved and decrypted for a single run.

    ``secret`` is excluded from ``repr`` and the override keeps it out of every
    string form. Same contract as ``CustomApiTool``: do not add a field, a
    ``__str__`` or a ``dict()`` that undoes it.
    """

    id: str
    slug: str
    name: str
    url: str
    auth_mode: str
    auth_name: str
    headers: dict[str, str]
    timeout_seconds: int
    tools: tuple[McpTool, ...] = ()
    secret: str | None = field(default=None, repr=False)

    def endpoint(self) -> mcp_transport.McpEndpoint:
        return mcp_transport.McpEndpoint(
            url=self.url,
            auth_mode=self.auth_mode,
            auth_name=self.auth_name,
            headers=dict(self.headers),
            timeout_seconds=self.timeout_seconds,
            secret=self.secret,
        )

    def __repr__(self) -> str:
        return f"McpServer(slug={self.slug!r}, tools={len(self.tools)})"

    __str__ = __repr__


def _collection():
    return get_mongo_db()[MongoCollection.MCP_SERVERS.value]


def _single_line(value: object) -> str:
    """Collapse a string to one line.

    Load-bearing for the same reason as in ``custom_api_service``, one degree
    worse: this text was written by a stranger, and a newline in a tool's name
    or description is a new instruction line in the agent that uses it.
    """
    return " ".join(str(value or "").split())


# --- Discovery-time sanitization -------------------------------------------


def sanitize_schema(node: Any, depth: int = 0) -> dict[str, Any] | None:
    """Rebuild a remote JSON Schema, keeping only what we understand.

    Rebuilt rather than passed through, for two reasons that both matter. The
    schema is attacker-authored text that reaches a system prompt, so every
    ``description`` in it needs the same scan and cap the tool's own gets — and
    nested property descriptions are the slot people forget. And providers
    reject unusual schemas outright, so a ``$ref`` or an ``allOf`` from a server
    would fail the whole native tool call rather than just that tool.

    Returns None when the node cannot be expressed within the caps, which drops
    the property — and, if it was required, the tool.
    """
    if depth > MCP_SCHEMA_MAX_DEPTH or not isinstance(node, dict):
        return None

    declared = node.get("type")
    if isinstance(declared, list):
        # A union of types is legal JSON Schema and unsupported by several
        # providers. Take the first scalar member rather than refusing outright.
        declared = next((t for t in declared if t in _SCALAR_TYPES), None)
    if not isinstance(declared, str):
        # No usable ``type``, but the node may still be a *choice* between
        # concrete alternatives. ``anyOf``/``oneOf`` collapse soundly: pick the
        # first branch that rebuilds and describe that one, since anything the
        # branch accepts the union accepted too. This matters in practice —
        # ``anyOf: [string, array<string>]`` is what Pydantic emits for
        # ``str | list[str]``, and refusing it withheld a real, popular tool on
        # a live server.
        #
        # ``allOf`` is deliberately NOT collapsed. It is a conjunction, so
        # picking one branch changes the contract rather than narrowing it, and
        # merging branches is a rewrite whose result nobody validated.
        for keyword in ("anyOf", "oneOf"):
            branches = node.get(keyword)
            if not isinstance(branches, list):
                continue
            for branch in branches:
                rebuilt = sanitize_schema(branch, depth)
                if rebuilt is None:
                    continue
                # The parent usually carries the human-readable description
                # while the branches carry only types; keep the parent's, still
                # capped and scanned like any other.
                for inherited in ("title", "description"):
                    text = _single_line(node.get(inherited))
                    if text and inherited not in rebuilt:
                        rebuilt[inherited] = connected_common.truncate(
                            text, MCP_SCHEMA_DESCRIPTION_MAX_CHARS
                        )
                return rebuilt
        return None

    out: dict[str, Any] = {"type": declared}
    for keyword in ("title", "description"):
        if keyword in node:
            text = _single_line(node[keyword])
            if text:
                out[keyword] = connected_common.truncate(
                    text, MCP_SCHEMA_DESCRIPTION_MAX_CHARS
                )
    for keyword in ("default", "minimum", "maximum", "minLength", "maxLength"):
        if keyword in node and isinstance(node[keyword], int | float | str | bool):
            out[keyword] = node[keyword]
    if isinstance(node.get("enum"), list):
        values = [v for v in node["enum"] if isinstance(v, str | int | float | bool)]
        if values:
            out["enum"] = values[:MCP_MAX_ENUM_VALUES]

    if declared == "object":
        properties = node.get("properties")
        if not isinstance(properties, dict):
            return None
        rebuilt: dict[str, Any] = {}
        for name, child in list(properties.items())[:MCP_MAX_PARAMETERS]:
            if not isinstance(name, str) or not name:
                continue
            shaped = sanitize_schema(child, depth + 1)
            if shaped is not None:
                rebuilt[name] = shaped
        out["properties"] = rebuilt
        required = [
            name
            for name in node.get("required", [])
            if isinstance(name, str) and name in rebuilt
        ]
        # A required property we could not express means the tool cannot be
        # called correctly, so the caller drops it rather than offering a schema
        # the server will reject.
        if len(required) != len(
            [n for n in node.get("required", []) if isinstance(n, str)]
        ):
            return None
        if required:
            out["required"] = required
    elif declared == "array":
        items = sanitize_schema(node.get("items"), depth + 1)
        if items is None:
            return None
        out["items"] = items
    elif declared not in _SCALAR_TYPES:
        return None

    # Anything we did not recognise is dropped rather than carried through.
    return {k: v for k, v in out.items() if k in MCP_SCHEMA_KEYWORDS}


def _sanitize_name(remote_name: str) -> str:
    """Fold a remote tool name into the action alphabet."""
    lowered = re.sub(r"[^a-zA-Z0-9_-]", "_", remote_name.strip())
    lowered = re.sub(r"_{2,}", "_", lowered).strip("_-")
    return lowered[:38]


def sanitize_tool(
    raw: Any, slug: str, taken: set[str]
) -> tuple[McpTool | None, str | None]:
    """Turn one advertised tool into a cached one, or say why it was withheld.

    Returns ``(tool, None)`` or ``(None, reason)``. The reason is stored and
    shown, because a tool that silently vanishes from a server the user just
    connected is indistinguishable from a broken integration.
    """
    if not isinstance(raw, dict):
        return None, "the server advertised a malformed entry"
    remote_name = str(raw.get("name") or "")
    if not remote_name:
        return None, "the server advertised a tool with no name"

    sanitized = _sanitize_name(remote_name)
    if not sanitized or not _TOOL_NAME_RE.match(sanitized):
        return None, "the tool name cannot be expressed as an action id"
    action = f"{MCP_ACTION_PREFIX}{slug}__{sanitized}"
    if len(action) > MCP_ACTION_MAX_CHARS:
        return None, "the tool name is too long to address"
    if action in taken:
        # Never auto-suffix: a suffixed action needs a reverse map to call the
        # right remote name, and a reverse map drifts.
        return None, "another tool on this server sanitizes to the same id"

    display_name = connected_common.truncate(
        _single_line(raw.get("title") or remote_name), MCP_TOOL_TITLE_MAX_CHARS
    )
    description = connected_common.truncate(
        _single_line(raw.get("description")), MCP_TOOL_DESCRIPTION_MAX_CHARS
    )
    if prompt_guard.scan_prompt(description) or prompt_guard.scan_prompt(display_name):
        # Per tool, not per server: one hostile entry must not blank out a
        # server's legitimate ones (the connected-tool convention).
        return None, "the tool's description failed the injection scan"

    schema = raw.get("inputSchema") or raw.get("input_schema") or {}
    if not isinstance(schema, dict) or not schema:
        parameters: dict[str, Any] = {"type": "object", "properties": {}}
    else:
        rebuilt = sanitize_schema(schema)
        if rebuilt is None or rebuilt.get("type") != "object":
            return None, "the tool's input schema could not be safely rebuilt"
        parameters = rebuilt
    if prompt_guard.is_suspicious(json.dumps(parameters, ensure_ascii=False)):
        return None, "the tool's input schema failed the injection scan"

    return (
        McpTool(
            action=action,
            remote_name=remote_name,
            display_name=display_name or sanitized,
            description=description,
            parameters=parameters,
        ),
        None,
    )


# --- Prompt-facing builders -------------------------------------------------


def build_parameter_schema(tool: McpTool) -> dict[str, Any]:
    """The native function-calling schema for one remote tool.

    Nested under ``args`` for the reason ``custom_api_service`` gives: a remote
    parameter named ``action`` would otherwise collide with the directive's own
    key on the non-native path.
    """
    return {
        "type": "object",
        "properties": {"args": tool.parameters},
        "required": ["args"],
    }


def tool_description(server: McpServer, tool: McpTool) -> str:
    """One sentence for the model. Never the URL."""
    suffix = f" {tool.description}" if tool.description else ""
    return f'Call "{tool.display_name}" on the "{server.name}" MCP server.{suffix}'


def build_rule_line(server: McpServer, tool: McpTool, budget: int) -> str:
    """The finished JSON-directive prompt line for a non-native model.

    Returned already-formatted and stored on ``ToolSpec.rule``: this text is
    built from a stranger's tool name, and running ``str.format`` over
    attacker-influenced text is an attribute-traversal surface, not merely a
    ``KeyError`` risk. Never names the host.
    """
    properties = tool.parameters.get("properties", {})
    required = set(tool.parameters.get("required", []))
    example = ", ".join(f'"{name}": "<value>"' for name in list(properties)[:3])
    lines = [
        f'- Call "{tool.display_name}" on "{server.name}" (max {budget} uses): '
        f'{{"action": "{tool.action}", "args": {{{example}}}}}'
    ]
    if tool.description:
        lines.append(f"  {tool.description}")
    if properties:
        described = "; ".join(
            f"{name} ({schema.get('type', 'string')}, "
            f"{'required' if name in required else 'optional'})"
            + (f" — {schema['description']}" if schema.get("description") else "")
            for name, schema in list(properties.items())[:MCP_MAX_PARAMETERS]
        )
        lines.append(f"  Parameters: {described}")
    return "\n".join(lines)


# --- CRUD -------------------------------------------------------------------


async def list_servers(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """The user's registered servers, newest first. Never includes a secret."""
    cursor = (
        _collection()
        .find({"user_id": str(user_id)}, _PUBLIC_PROJECTION)
        .sort("created_at", -1)
        .limit(MCP_SERVERS_MAX)
    )
    return [_public(doc) async for doc in cursor]


async def get_server(user_id: uuid.UUID, server_id: str) -> dict[str, Any] | None:
    """One server owned by the user, or None. Never includes a secret."""
    doc = await _collection().find_one(
        {"id": server_id, "user_id": str(user_id)}, _PUBLIC_PROJECTION
    )
    return None if doc is None else _public(doc)


async def get_server_ids(user_id: uuid.UUID, server_ids: list[str]) -> set[str]:
    """Which of ``server_ids`` this user actually owns."""
    if not server_ids:
        return set()
    cursor = _collection().find(
        {"user_id": str(user_id), "id": {"$in": server_ids}}, {"_id": 0, "id": 1}
    )
    return {doc["id"] async for doc in cursor}


def _is_stale(doc: dict[str, Any]) -> bool:
    fetched = doc.get("tools_fetched_at")
    if not isinstance(fetched, datetime):
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    return datetime.now(UTC) - fetched > timedelta(seconds=MCP_TOOLS_CACHE_TTL_SECONDS)


def _public(doc: dict[str, Any]) -> dict[str, Any]:
    """Shape a stored document for a response, adding the computed staleness."""
    shaped = {k: v for k, v in doc.items() if k not in ("_id", "user_id")}
    shaped["tools_stale"] = bool(doc.get("tools_stale")) or _is_stale(doc)
    return shaped


async def create_server(
    user_id: uuid.UUID,
    payload: McpServerCreate,
    *,
    source: str = "custom",
    plugin_id: str | None = None,
) -> dict[str, Any]:
    """Register a server for this user. Discovery is a separate, explicit step."""
    owned = await _collection().count_documents({"user_id": str(user_id)})
    if owned >= MCP_SERVERS_MAX:
        raise McpValidationError(
            f"You can register at most {MCP_SERVERS_MAX} MCP servers."
        )
    # Explicit, because the unique index is built best-effort at startup and is
    # allowed to be missing (core/database.ensure_indexes swallows failures).
    if await _collection().find_one({"user_id": str(user_id), "slug": payload.slug}):
        raise McpValidationError(
            f"You already have an MCP server with the slug '{payload.slug}'."
        )

    now = datetime.now(UTC)
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": str(user_id),
        "slug": payload.slug,
        "name": _single_line(payload.name),
        "description": _single_line(payload.description),
        "url": payload.url,
        "transport": payload.transport,
        "headers": payload.headers,
        "auth_mode": payload.auth_mode,
        "auth_name": payload.auth_name,
        "encrypted_secret": (
            encrypt_secret(payload.secret) if payload.secret else None
        ),
        "secret_hint": mask_secret(payload.secret) if payload.secret else None,
        "timeout_seconds": payload.timeout_seconds,
        "enabled": payload.enabled,
        "tool_allowlist": [],
        "tools": [],
        "tools_fetched_at": None,
        "tools_stale": True,
        "protocol_version": "",
        "server_name": "",
        "server_version": "",
        "source": source,
        "plugin_id": plugin_id,
        "created_at": now,
        "updated_at": now,
    }
    try:
        await _collection().insert_one(dict(doc))
    except DuplicateKeyError as exc:
        # The checks above are read-then-write, so two concurrent POSTs can both
        # pass them. The unique index is the authoritative gate.
        raise McpValidationError(
            f"You already have an MCP server with the slug '{payload.slug}'."
        ) from exc
    return _public(doc)


async def update_server(
    user_id: uuid.UUID, server_id: str, payload: McpServerUpdate
) -> dict[str, Any] | None:
    """Apply a partial update; returns the new state."""
    changes: dict[str, Any] = {}
    for field_name in (
        "description",
        "headers",
        "auth_mode",
        "auth_name",
        "timeout_seconds",
        "enabled",
        "tool_allowlist",
    ):
        value = getattr(payload, field_name)
        if value is not None:
            changes[field_name] = value
    if payload.name is not None:
        changes["name"] = _single_line(payload.name)
    if payload.description is not None:
        changes["description"] = _single_line(payload.description)
    if payload.secret is not None:
        changes["encrypted_secret"] = encrypt_secret(payload.secret)
        changes["secret_hint"] = mask_secret(payload.secret)
    if payload.url is not None:
        changes["url"] = payload.url
        # A new address is a new server as far as the catalog is concerned: the
        # cached tools describe whatever used to answer there. Keeping them
        # would let a URL change silently repoint every prompt line.
        changes["tools"] = []
        changes["tools_fetched_at"] = None
        changes["tools_stale"] = True

    if not changes:
        return await get_server(user_id, server_id)
    changes["updated_at"] = datetime.now(UTC)
    result = await _collection().update_one(
        {"id": server_id, "user_id": str(user_id)}, {"$set": changes}
    )
    if result.matched_count == 0:
        return None
    return await get_server(user_id, server_id)


async def delete_server(user_id: uuid.UUID, server_id: str) -> bool:
    """Delete a user-owned server. Returns True if one was removed."""
    result = await _collection().delete_one({"id": server_id, "user_id": str(user_id)})
    return result.deleted_count > 0


# --- Loading and discovery --------------------------------------------------


def _to_server(doc: dict[str, Any]) -> McpServer:
    encrypted = doc.get("encrypted_secret")
    allowlist = set(doc.get("tool_allowlist") or ())
    tools = tuple(
        McpTool(
            action=entry["action"],
            remote_name=entry["remote_name"],
            display_name=entry.get("display_name", ""),
            description=entry.get("description", ""),
            parameters=entry.get("parameters") or {},
        )
        for entry in doc.get("tools") or ()
        if entry.get("enabled", True)
        and not entry.get("blocked_reason")
        and (not allowlist or entry["action"] in allowlist)
    )
    return McpServer(
        id=doc["id"],
        slug=doc["slug"],
        name=doc.get("name", ""),
        url=doc["url"],
        auth_mode=doc.get("auth_mode", "none"),
        auth_name=doc.get("auth_name", ""),
        headers=doc.get("headers") or {},
        timeout_seconds=int(doc.get("timeout_seconds", 30)),
        tools=tools,
        secret=decrypt_secret(encrypted) if encrypted else None,
    )


async def load_servers(
    user_id: uuid.UUID, server_ids: list[str] | None = None
) -> tuple[McpServer, ...]:
    """Load a user's enabled servers from the cache. Never raises, never calls out.

    Called once per task run at the engine edge, alongside
    ``custom_api_service.load_tools``. Reads the *cached* catalog only: a
    ``tools/list`` here would put a network round trip per server on the
    critical path of every task, and — because this function may not raise — a
    discovery timeout would degrade into "this agent silently has no tools",
    which is the worst failure mode available.
    """
    query: dict[str, Any] = {"user_id": str(user_id), "enabled": True}
    if server_ids is not None:
        if not server_ids:
            return ()
        query["id"] = {"$in": server_ids}
    try:
        cursor = _collection().find(query).limit(MCP_SERVERS_MAX)
        docs = [doc async for doc in cursor]
    except Exception:  # noqa: BLE001 - a DB hiccup must not fail the task
        logger.warning("Could not load MCP servers", exc_info=True)
        return ()

    servers: list[McpServer] = []
    for doc in docs:
        try:
            servers.append(_to_server(doc))
        except Exception:  # noqa: BLE001 - corrupt/rotated secret: skip, don't fail
            # Slug only. The ciphertext and the exception detail could both
            # narrow an attack on the master key.
            logger.warning("Skipping unreadable MCP server %s", doc.get("slug"))
    return tuple(servers)


async def stale_server_ids(user_id: uuid.UUID) -> list[str]:
    """Ids whose cached catalog has aged past its TTL. Never raises."""
    try:
        cursor = _collection().find(
            {"user_id": str(user_id), "enabled": True},
            {"_id": 0, "id": 1, "tools_fetched_at": 1, "tools_stale": 1},
        )
        return [doc["id"] async for doc in cursor if _is_stale(doc)]
    except Exception:  # noqa: BLE001 - staleness is advisory
        return []


async def discover(user_id: uuid.UUID, server_id: str) -> McpDiscoverResult:
    """Refresh one server's tool catalog. Reports failure, never raises.

    Pointing at a server that is down, or that refuses the handshake, is an
    ordinary thing for a user to do; it is a message, not a 500.
    """
    started = time.perf_counter()
    doc = await _collection().find_one({"id": server_id, "user_id": str(user_id)})
    if doc is None:
        return McpDiscoverResult(ok=False, error="This server no longer exists.")

    server = _to_server(doc)
    endpoint = server.endpoint()
    deadline = time.monotonic() + settings.mcp_discovery_timeout_seconds
    session = None
    try:
        session = await mcp_transport.initialize(endpoint, deadline=deadline)
        raw_tools: list[Any] = []
        cursor: str | None = None
        for _ in range(MCP_LIST_PAGES_MAX):
            page = await mcp_transport.list_tools(
                endpoint, session, cursor=cursor, deadline=deadline
            )
            entries = page.get("tools")
            if isinstance(entries, list):
                raw_tools.extend(entries)
            cursor = page.get("nextCursor") or None
            if not cursor or len(raw_tools) >= MCP_TOOLS_PER_SERVER_MAX:
                break
    except mcp_transport.McpTransportError as exc:
        return McpDiscoverResult(
            ok=False,
            error=str(exc),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception:  # noqa: BLE001 - an unexpected shape is still a failure
        logger.warning("MCP discovery failed for %s", server.slug, exc_info=True)
        return McpDiscoverResult(
            ok=False,
            error="The server could not be read.",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    finally:
        if session is not None:
            await mcp_transport.close(endpoint, session)

    cached: list[dict[str, Any]] = []
    taken: set[str] = set()
    withheld = 0
    for raw in raw_tools[:MCP_TOOLS_PER_SERVER_MAX]:
        tool, reason = sanitize_tool(raw, server.slug, taken)
        if tool is None:
            withheld += 1
            name = _single_line(
                (raw or {}).get("name") if isinstance(raw, dict) else ""
            )
            cached.append(
                {
                    "action": "",
                    "remote_name": connected_common.truncate(name, 80),
                    "display_name": connected_common.truncate(name, 80),
                    "description": "",
                    "parameters": {},
                    "enabled": False,
                    "blocked_reason": reason,
                }
            )
            continue
        taken.add(tool.action)
        cached.append(
            {
                "action": tool.action,
                "remote_name": tool.remote_name,
                "display_name": tool.display_name,
                "description": tool.description,
                "parameters": tool.parameters,
                "enabled": True,
                "blocked_reason": None,
            }
        )

    await _collection().update_one(
        {"id": server_id, "user_id": str(user_id)},
        {
            "$set": {
                "tools": cached,
                "tools_fetched_at": datetime.now(UTC),
                "tools_stale": False,
                "protocol_version": session.protocol_version if session else "",
                "server_name": session.server_name if session else "",
                "server_version": session.server_version if session else "",
                "updated_at": datetime.now(UTC),
            }
        },
    )
    return McpDiscoverResult(
        ok=True,
        server_name=session.server_name if session else "",
        server_version=session.server_version if session else "",
        protocol_version=session.protocol_version if session else "",
        tools=[McpToolPublic(**entry) for entry in cached if entry["action"]],
        withheld=withheld,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


async def mark_stale(user_id: uuid.UUID, server_id: str) -> None:
    """Flag a catalog as out of date. Best effort; never raises.

    Called when a call names a tool the server no longer has — the cheap,
    self-healing signal that avoids paying a ``tools/list`` on every task just
    to notice a change that may never come.
    """
    try:
        await _collection().update_one(
            {"id": server_id, "user_id": str(user_id)},
            {"$set": {"tools_stale": True}},
        )
    except Exception:  # noqa: BLE001 - a hint, not a requirement
        logger.debug("Could not flag MCP catalog stale")


# --- The tool path ----------------------------------------------------------


def _render(server: McpServer, tool: McpTool, payload: dict[str, Any]) -> str:
    """Shape a CallToolResult into a delimited, capped, scanned prompt block."""
    blocks = payload.get("content")
    notes: list[str] = []
    texts: list[str] = []
    skipped = 0

    structured = payload.get("structuredContent")
    if isinstance(structured, dict | list):
        texts.append(json.dumps(structured, ensure_ascii=False, default=str))
    elif isinstance(blocks, list):
        for block in blocks[:MCP_MAX_ITEMS]:
            if not isinstance(block, dict):
                skipped += 1
                continue
            kind = block.get("type")
            if kind == "text":
                texts.append(str(block.get("text", "")))
            elif kind == "resource_link":
                texts.append(f"{block.get('name', 'resource')}: {block.get('uri', '')}")
            elif kind == "resource" and isinstance(block.get("resource"), dict):
                texts.append(str(block["resource"].get("text", "")))
            else:
                # Never inline an image or audio payload: a 5 MB base64 blob is
                # ~6.7 MB of tokens and carries nothing a model can read here.
                skipped += 1
    if skipped:
        notes.append(f"{skipped} non-text block(s) omitted")

    # Per-item, not whole-block: one hostile entry must not blank out the
    # legitimate ones (the connected-tool convention).
    kept = connected_common.drop_suspicious(texts, lambda text: text)
    dropped = len(texts) - len(kept)
    if dropped:
        notes.append(f"{dropped} block(s) withheld as suspicious")

    shaped = [connected_common.truncate(text, MCP_ITEM_MAX_CHARS) for text in kept]
    # The per-item cap alone lets MAX_ITEMS x ITEM_MAX_CHARS through, so drop
    # whole blocks until the rendered result fits (the custom_api convention).
    while shaped and sum(len(text) for text in shaped) > MCP_RESULT_MAX_CHARS:
        shaped.pop()
        notes.append("truncated to fit")

    # A structured payload, not a pre-joined string: ``render_block`` serializes
    # with the JSON encoder, so handing it a string would escape every quote in
    # the body and spend tokens on backslashes.
    payload_out: dict[str, Any] = {
        "content": shaped or ["(the server returned nothing readable)"]
    }
    if notes:
        payload_out["notes"] = sorted(set(notes))
    return connected_common.render_block(
        open_tag=MCP_RESULT_OPEN,
        close_tag=MCP_RESULT_CLOSE,
        header=f"{server.name} / {tool.display_name}",
        payload=payload_out,
    )


async def call(server: McpServer, tool: McpTool, args: dict[str, Any]) -> str:
    """Run one remote tool and return the prompt block. Never raises."""
    try:
        return await _call(server, tool, args)
    except Exception:  # noqa: BLE001 - an escape here fails the whole subtask
        # Slug and tool only. Never the URL, never the arguments.
        logger.warning(
            "MCP call failed: %s/%s", server.slug, tool.display_name, exc_info=True
        )
        return connected_common.failure(
            f"{server.name} / {tool.display_name}", "the call could not be completed"
        )


async def _call(server: McpServer, tool: McpTool, args: dict[str, Any]) -> str:
    # Second lock. ``resolve_enabled_tools`` already dropped these actions when
    # the switch is off, so reaching here means something bypassed that gate.
    if not settings.mcp_enabled:
        return connected_common.failure(
            f"{server.name} / {tool.display_name}",
            "MCP servers are disabled on this deployment",
        )

    endpoint = server.endpoint()
    # A deadline for the whole call, not a timeout per POST: one tool call is
    # three connections, and three independent timeouts would let a slow server
    # spend three times the budget the operator configured.
    deadline = time.monotonic() + min(
        server.timeout_seconds, settings.mcp_timeout_seconds
    )
    session = None
    try:
        session = await mcp_transport.initialize(endpoint, deadline=deadline)
        payload = await mcp_transport.call_tool(
            endpoint, session, tool.remote_name, args, deadline=deadline
        )
    except mcp_transport.McpTransportError as exc:
        return connected_common.failure(
            f"{server.name} / {tool.display_name}", str(exc)
        )
    finally:
        if session is not None:
            await mcp_transport.close(endpoint, session)

    if payload.get("isError"):
        blocks = payload.get("content")
        detail = ""
        if isinstance(blocks, list) and blocks and isinstance(blocks[0], dict):
            detail = connected_common.truncate(_single_line(blocks[0].get("text")), 200)
        return connected_common.failure(
            f"{server.name} / {tool.display_name}",
            detail or "the tool reported an error",
        )
    return _render(server, tool, payload)


async def dry_run(server: McpServer, tool: McpTool, args: dict[str, Any]) -> str:
    """One call, previewed for the UI. Runs the real path, not a shortcut."""
    return connected_common.truncate(
        await call(server, tool, args), MCP_PREVIEW_MAX_CHARS
    )
