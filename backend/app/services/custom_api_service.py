"""User-registered HTTP endpoints, exposed to that user's own agents as tools.

Stored in MongoDB (``custom_api_tools``), one collection rather than fields on
the agent document, for three reasons that are easy to lose later:

1. ``agent_service.list_agents`` returns whole documents and ``GET /agents`` has
   no ``response_model``, so an ``encrypted_secret`` embedded in an agent would
   reach the browser on the next page load.
2. One endpoint attaches to several agents; embedding means N copies and N-way
   rotation.
3. The agent document then carries only *ids*, which is what makes marketplace
   publish/install unable to move an endpoint between accounts.

Two contracts, mirroring :mod:`app.services.service_key_service`:

* **Never raises out of the tool path.** ``subagent._execute`` has no
  ``try/except``, so an exception escaping :func:`call` fails the whole subtask.
  Every failure becomes a sentence the model can act on.
* **Never leaks.** :class:`CustomApiTool` keeps its secret out of ``repr``; every
  read used for an HTTP response projects the ciphertext away; the decrypted
  value is applied at request-build time and never reaches a log, an event
  payload or the returned block.

This is the only tool whose host comes from user input, so it validates through
``url_guard`` twice — at registration and again per call — and never follows a
redirect. See the note in :mod:`app.services.connected_common`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from app.core.config import settings
from app.core.constants import (
    CUSTOM_API_ACTION_PREFIX,
    CUSTOM_API_ITEM_MAX_CHARS,
    CUSTOM_API_MAX_BYTES,
    CUSTOM_API_MAX_ITEMS,
    CUSTOM_API_PREVIEW_MAX_CHARS,
    CUSTOM_API_RESULT_CLOSE,
    CUSTOM_API_RESULT_OPEN,
    CUSTOM_API_TOOLS_MAX,
    MongoCollection,
)
from app.core.database import get_mongo_db
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.schemas.custom_api_tool import (
    CustomApiToolCreate,
    CustomApiToolTestResult,
    CustomApiToolUpdate,
)
from app.services import connected_common
from app.utils import prompt_guard
from app.utils.url_guard import check_public_url

logger = logging.getLogger(__name__)

# Never returned to a caller and never logged. Belt (this projection) and
# braces (the explicit CustomApiToolPublic field list).
_PUBLIC_PROJECTION = {"_id": 0, "user_id": 0, "encrypted_secret": 0}

_JSON_TYPES = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
}


class CustomApiValidationError(ValueError):
    """Raised when a custom API tool fails validation or a security scan."""


@dataclass(frozen=True, slots=True)
class CustomApiTool:
    """One registered endpoint, resolved and decrypted for a single run.

    ``secret`` is excluded from the generated ``repr`` and the override below
    keeps it out of any string form, so the object can appear in a traceback, a
    log record or a debugger without exposing a credential. Do not add a field,
    a ``__str__`` or a ``dict()`` that undoes this.
    """

    id: str
    slug: str
    name: str
    description: str
    method: str
    base_url: str
    path_template: str
    query_template: dict[str, str]
    headers: dict[str, str]
    auth_mode: str
    auth_name: str
    parameters: list[dict[str, Any]]
    body_template: dict[str, Any] | None
    response_json_path: str
    response_max_chars: int
    timeout_seconds: int
    secret: str | None = field(default=None, repr=False)

    @property
    def action(self) -> str:
        """The directive action name this tool answers to."""
        return f"{CUSTOM_API_ACTION_PREFIX}{self.slug}"

    def __repr__(self) -> str:
        return f"CustomApiTool(slug={self.slug!r}, method={self.method!r})"

    __str__ = __repr__


def _collection():
    return get_mongo_db()[MongoCollection.CUSTOM_API_TOOLS.value]


def _single_line(value: str) -> str:
    """Collapse a user string to one line.

    Load-bearing, not cosmetic: ``name`` and ``description`` are interpolated
    into the *subagent's own system prompt* by :func:`build_rule_line`. A newline
    would let a registration inject a new instruction line into the agent that
    uses it.
    """
    return " ".join(str(value).split())


def _guard_text(*values: str) -> None:
    """Reject text that trips the injection scanner.

    Same gate ``agent_service._guard_prompt`` applies to a system prompt, and for
    the same reason: this text ends up inside one.
    """
    for value in values:
        if value and prompt_guard.scan_prompt(value):
            raise CustomApiValidationError(
                "The tool name or description failed the security scan "
                "(possible prompt injection)."
            )


# --- CRUD ------------------------------------------------------------------


async def list_tools(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """The user's registered endpoints, newest first. Never includes a secret."""
    cursor = (
        _collection()
        .find({"user_id": str(user_id)}, _PUBLIC_PROJECTION)
        .sort("created_at", -1)
        .limit(CUSTOM_API_TOOLS_MAX)
    )
    return [doc async for doc in cursor]


async def get_tool(user_id: uuid.UUID, tool_id: str) -> dict[str, Any] | None:
    """One endpoint owned by the user, or None. Never includes a secret."""
    return await _collection().find_one(
        {"id": tool_id, "user_id": str(user_id)}, _PUBLIC_PROJECTION
    )


async def get_tool_ids(user_id: uuid.UUID, tool_ids: list[str]) -> set[str]:
    """Which of ``tool_ids`` this user actually owns.

    The ownership gate for attaching endpoints to an agent: a caller naming
    someone else's id gets a validation error rather than a silent attach.
    """
    if not tool_ids:
        return set()
    cursor = _collection().find(
        {"user_id": str(user_id), "id": {"$in": tool_ids}}, {"_id": 0, "id": 1}
    )
    return {doc["id"] async for doc in cursor}


async def create_tool(
    user_id: uuid.UUID, payload: CustomApiToolCreate
) -> dict[str, Any]:
    """Register an endpoint for this user."""
    name = _single_line(payload.name)
    description = _single_line(payload.description)
    _guard_text(name, description)

    owned = await _collection().count_documents({"user_id": str(user_id)})
    if owned >= CUSTOM_API_TOOLS_MAX:
        raise CustomApiValidationError(
            f"You can register at most {CUSTOM_API_TOOLS_MAX} API tools."
        )
    # Explicit, because the unique index is built best-effort at startup and is
    # allowed to be missing (core/database.ensure_indexes swallows failures).
    if await _collection().find_one({"user_id": str(user_id), "slug": payload.slug}):
        raise CustomApiValidationError(
            f"You already have an API tool with the slug '{payload.slug}'."
        )

    now = datetime.now(UTC)
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": str(user_id),
        "slug": payload.slug,
        "name": name,
        "description": description,
        "method": payload.method,
        "base_url": payload.base_url.rstrip("/"),
        "path_template": payload.path_template,
        "query_template": payload.query_template,
        "headers": payload.headers,
        "auth_mode": payload.auth_mode,
        "auth_name": payload.auth_name,
        "encrypted_secret": (
            encrypt_secret(payload.secret) if payload.secret else None
        ),
        "secret_hint": mask_secret(payload.secret) if payload.secret else None,
        "parameters": [p.model_dump() for p in payload.parameters],
        "body_template": payload.body_template,
        "response_json_path": payload.response_json_path,
        "response_max_chars": payload.response_max_chars,
        "timeout_seconds": payload.timeout_seconds,
        "enabled": payload.enabled,
        "created_at": now,
        "updated_at": now,
    }
    await _collection().insert_one(dict(doc))
    return {k: v for k, v in doc.items() if k not in ("user_id", "encrypted_secret")}


async def update_tool(
    user_id: uuid.UUID, tool_id: str, payload: CustomApiToolUpdate
) -> dict[str, Any] | None:
    """Apply a partial update. Returns None when the user owns no such tool."""
    changes: dict[str, Any] = {}
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None and key != "body_template":
            # An omitted field means "leave it alone". body_template is the one
            # field whose null is a real value (clear the body).
            continue
        if key == "secret":
            # Reached only when a non-null secret was sent: a null secret is a
            # rotation the caller did not ask for, and would break a live tool.
            changes["encrypted_secret"] = encrypt_secret(value)
            changes["secret_hint"] = mask_secret(value)
            continue
        if key in ("name", "description"):
            value = _single_line(value)
        if key == "base_url":
            value = value.rstrip("/")
        if key == "parameters":
            value = [dict(p) for p in value]
        changes[key] = value

    _guard_text(changes.get("name", ""), changes.get("description", ""))
    if not changes:
        return await get_tool(user_id, tool_id)

    changes["updated_at"] = datetime.now(UTC)
    result = await _collection().update_one(
        {"id": tool_id, "user_id": str(user_id)}, {"$set": changes}
    )
    if result.matched_count == 0:
        return None
    return await get_tool(user_id, tool_id)


async def delete_tool(user_id: uuid.UUID, tool_id: str) -> bool:
    """Delete one endpoint owned by the user."""
    result = await _collection().delete_one({"id": tool_id, "user_id": str(user_id)})
    return result.deleted_count > 0


# --- Loading for a run -----------------------------------------------------


def _to_tool(doc: dict[str, Any]) -> CustomApiTool:
    encrypted = doc.get("encrypted_secret")
    return CustomApiTool(
        id=doc["id"],
        slug=doc["slug"],
        name=doc.get("name", doc["slug"]),
        description=doc.get("description", ""),
        method=doc.get("method", "GET"),
        base_url=doc["base_url"],
        path_template=doc.get("path_template", "/"),
        query_template=doc.get("query_template") or {},
        headers=doc.get("headers") or {},
        auth_mode=doc.get("auth_mode", "none"),
        auth_name=doc.get("auth_name", ""),
        parameters=list(doc.get("parameters") or []),
        body_template=doc.get("body_template"),
        response_json_path=doc.get("response_json_path", ""),
        response_max_chars=doc.get("response_max_chars", 8000),
        timeout_seconds=doc.get("timeout_seconds", 15),
        secret=decrypt_secret(encrypted) if encrypted else None,
    )


async def load_tools(
    user_id: uuid.UUID, tool_ids: list[str] | None = None
) -> tuple[CustomApiTool, ...]:
    """Load and decrypt a user's enabled endpoints. Never raises.

    Called once per task run at the engine edge, alongside
    ``load_service_credentials``, so the agent layer receives plain values and
    never touches the database or the master key. A rotated or corrupt secret is
    logged by slug only and that one tool is skipped — a broken credential must
    not fail the task, exactly as for a service key.

    ``tool_ids`` restricts the load to the ids an agent attached; the ``user_id``
    filter still applies, so an id belonging to someone else resolves to nothing.
    """
    query: dict[str, Any] = {"user_id": str(user_id), "enabled": True}
    if tool_ids is not None:
        if not tool_ids:
            return ()
        query["id"] = {"$in": tool_ids}
    try:
        cursor = _collection().find(query).limit(CUSTOM_API_TOOLS_MAX)
        docs = [doc async for doc in cursor]
    except Exception:  # noqa: BLE001 - a DB hiccup must not fail the task
        logger.warning("Could not load custom API tools", exc_info=True)
        return ()

    tools: list[CustomApiTool] = []
    for doc in docs:
        try:
            tools.append(_to_tool(doc))
        except Exception:  # noqa: BLE001 - corrupt/rotated secret: skip, don't fail
            # Slug only. The ciphertext and the exception detail could both
            # narrow an attack on the master key.
            logger.warning("Skipping undecryptable custom API tool %s", doc.get("slug"))
    return tuple(tools)


# --- Pure builders (schema + prompt text) ----------------------------------


def build_parameter_schema(tool: CustomApiTool) -> dict[str, Any]:
    """JSON Schema for native function calling.

    Lives on the per-run ``ToolSpec`` rather than in the module-level
    ``_TOOL_PARAMETERS``: that dict is process-wide, and putting one user's
    endpoint in it would leak the shape across users in a multi-worker server.
    """
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in tool.parameters:
        entry: dict[str, Any] = {
            "type": _JSON_TYPES.get(param.get("type", "string"), "string"),
            "description": _single_line(param.get("description", "")),
        }
        if param.get("enum"):
            entry["enum"] = list(param["enum"])
        properties[param["name"]] = entry
        if param.get("required"):
            required.append(param["name"])
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "args": {
                "type": "object",
                "properties": properties,
                # Nested under "args" rather than flattened so a parameter named
                # "action" cannot collide with the directive's own key.
                "required": required,
            }
        },
        "required": ["args"] if required else [],
    }
    return schema


def build_rule_line(tool: CustomApiTool, budget: int) -> str:
    """The prompt line teaching a non-native model to call this endpoint.

    Without one, a tool is invisible to every model that drives the JSON
    directive loop rather than native function calling — the failure
    ``tests/test_subagent_connected_tools.py`` pins for the built-in tools.
    """
    args = ", ".join(f'"{p["name"]}": "<value>"' for p in tool.parameters)
    described = "; ".join(
        f"{p['name']} ({p.get('type', 'string')}"
        + (", required" if p.get("required") else ", optional")
        + (f") — {_single_line(p['description'])}" if p.get("description") else ")")
        for p in tool.parameters
    )
    lines = [
        f'- Call the "{tool.name}" API (max {budget} uses): '
        f'{{"action": "{tool.action}", "args": {{{args}}}}}'
    ]
    if tool.description:
        lines.append(f"  {tool.description}")
    if described:
        lines.append(f"  Parameters: {described}")
    return "\n".join(lines)


# --- Calling ---------------------------------------------------------------


def _coerce(value: str, declared_type: str) -> Any:
    """Best-effort typing of a model-supplied string. Raises on a real mismatch."""
    text = value.strip()
    if declared_type == "integer":
        return int(text)
    if declared_type == "number":
        return float(text)
    if declared_type == "boolean":
        if text.lower() in ("true", "yes", "1", "on"):
            return True
        if text.lower() in ("false", "no", "0", "off"):
            return False
        raise ValueError(f"{value!r} is not a boolean")
    return text


def _validate_args(tool: CustomApiTool, args: dict[str, str]) -> dict[str, Any]:
    """Check the model's arguments against the declared schema.

    Raises :class:`CustomApiValidationError`, which :func:`call` turns into a
    sentence rather than letting it escape.
    """
    resolved: dict[str, Any] = {}
    declared = {p["name"]: p for p in tool.parameters}
    for name, param in declared.items():
        raw = args.get(name)
        if raw is None or raw == "":
            if param.get("required"):
                raise CustomApiValidationError(f"missing required parameter '{name}'")
            continue
        if param.get("enum") and raw not in param["enum"]:
            allowed = ", ".join(param["enum"])
            raise CustomApiValidationError(
                f"parameter '{name}' must be one of: {allowed}"
            )
        try:
            resolved[name] = _coerce(raw, param.get("type", "string"))
        except ValueError:
            raise CustomApiValidationError(
                f"parameter '{name}' is not a valid {param.get('type', 'string')}"
            ) from None
    return resolved


def _fill(template: str, values: dict[str, Any], *, encode: bool) -> str:
    """Substitute ``{name}`` placeholders.

    ``encode`` percent-encodes with an empty safe set, which is what stops a
    model-supplied value from adding a path segment, escaping upward with
    ``../``, or starting a query. ``urljoin`` is deliberately not used: it would
    happily let an absolute-looking value replace the whole base.
    """
    out = template
    for name, value in values.items():
        text = str(value)
        out = out.replace(f"{{{name}}}", quote(text, safe="") if encode else text)
    return out


def _fill_body(node: Any, values: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        return {k: _fill_body(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [_fill_body(v, values) for v in node]
    if isinstance(node, str):
        # A whole-value placeholder keeps the parameter's real JSON type
        # (an integer stays an integer) instead of stringifying it.
        stripped = node.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            key = stripped[1:-1]
            if key in values:
                return values[key]
        return _fill(node, values, encode=False)
    return node


def _extract_path(payload: Any, path: str) -> tuple[Any, bool]:
    """Follow a dotted path into the payload. Returns (value, found)."""
    if not path:
        return payload, True
    node = payload
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return payload, False
    return node, True


def _shape(tool: CustomApiTool, payload: Any) -> tuple[Any, str]:
    """Cap and injection-scan a response. Returns (payload, note)."""
    extracted, found = _extract_path(payload, tool.response_json_path)
    note = (
        ""
        if found
        else f" (response_json_path '{tool.response_json_path}' did not match)"
    )
    if isinstance(extracted, list):
        items = extracted[:CUSTOM_API_MAX_ITEMS]
        # Per-item, not whole-block: one hostile row must not blank out the
        # legitimate ones (the connected-tool convention).
        kept = connected_common.drop_suspicious(
            items, lambda item: json.dumps(item, ensure_ascii=False, default=str)
        )
        dropped = len(items) - len(kept)
        if dropped:
            note += f" ({dropped} item(s) withheld as suspicious)"
        shaped: Any = [
            connected_common.truncate(
                json.dumps(item, ensure_ascii=False, default=str),
                CUSTOM_API_ITEM_MAX_CHARS,
            )
            for item in kept
        ]
    else:
        serialized = json.dumps(extracted, ensure_ascii=False, default=str)
        if prompt_guard.is_suspicious(serialized):
            return (
                "[withheld: the response looked like a prompt-injection payload]",
                note,
            )
        shaped = connected_common.truncate(serialized, tool.response_max_chars)
    return shaped, note


async def call(tool: CustomApiTool, args: dict[str, str]) -> str:
    """Execute one call and render it as an untrusted-data block.

    Never raises. Every failure path returns a sentence the subagent can act on,
    because ``subagent._execute`` has no ``try/except`` and an escaping exception
    would fail the entire subtask.
    """
    try:
        return await _call(tool, args)
    except Exception:  # noqa: BLE001 - last resort; this path runs user templates
        # Slug only: a traceback here could carry a substituted URL.
        logger.warning("Custom API tool %s failed unexpectedly", tool.slug)
        return connected_common.failure(tool.name, "the call could not be completed")


async def _call(tool: CustomApiTool, args: dict[str, str]) -> str:
    if not settings.custom_api_tools_enabled:
        # Second lock: resolve_enabled_tools already drops these actions when the
        # switch is off, so reaching here means something bypassed that gate.
        return connected_common.failure(
            tool.name, "custom API tools are disabled on this deployment"
        )

    try:
        values = _validate_args(tool, args)
    except CustomApiValidationError as exc:
        return connected_common.failure(tool.name, str(exc))

    url, query, headers, body = _build_request(tool, values)

    if settings.llm_ssrf_guard_enabled:
        # Re-checked here and not only at registration: the record outlives its
        # validation, and the hostname's DNS is the user's to change. Gated on
        # the same switch the route uses — that setting means "this deployment
        # may reach private hosts", and honouring it in one place but not the
        # other would make a tool registrable and then silently unusable.
        reason = await check_public_url(url)
        if reason:
            logger.warning(
                "Custom API tool %s refused by url_guard: %s", tool.slug, reason
            )
            return connected_common.failure(
                tool.name, f"the endpoint is not reachable ({reason})"
            )

    result = await connected_common.request_api(
        url,
        method=tool.method,
        headers=headers or None,
        params=query or None,
        json_body=body,
        timeout=min(tool.timeout_seconds, settings.custom_api_timeout_seconds),
        # Built from the template, not the substituted URL, so a secret a user
        # mistakenly pasted into path_template still cannot reach a log.
        log_target=f"{tool.slug}{tool.path_template}",
        # Deliberately no follow_redirect_host: the shared client does not follow
        # redirects, and that is what keeps an Authorization header from reaching
        # another origin (CLAUDE.md §8).
        max_bytes=CUSTOM_API_MAX_BYTES,
    )

    if result.oversized:
        return connected_common.failure(tool.name, "the response was too large to read")
    if 300 <= result.status < 400:
        return connected_common.failure(
            tool.name, "the endpoint redirected, and redirects are not followed"
        )
    if result.rate_limited:
        return connected_common.failure(tool.name, "the endpoint is rate limiting us")
    if result.data is None:
        detail = (
            f"it answered {result.status}"
            if result.status
            else "it could not be reached"
        )
        return connected_common.failure(tool.name, detail)

    shaped, note = _shape(tool, result.data)
    return connected_common.render_block(
        open_tag=CUSTOM_API_RESULT_OPEN,
        close_tag=CUSTOM_API_RESULT_CLOSE,
        header=f'Result of "{tool.name}"{note}',
        payload=shaped,
    )


def _build_request(
    tool: CustomApiTool, values: dict[str, Any]
) -> tuple[str, dict[str, Any], dict[str, str], Any]:
    """Assemble the URL, query, headers and body. The secret is applied here only."""
    path = _fill(tool.path_template, values, encode=True)
    url = f"{tool.base_url.rstrip('/')}{path}"
    # Values go through httpx's params=, never string concatenation, so encoding
    # is the library's job rather than ours.
    query = {k: _fill(v, values, encode=False) for k, v in tool.query_template.items()}
    headers = dict(tool.headers)
    body = _fill_body(tool.body_template, values) if tool.body_template else None

    if tool.secret:
        if tool.auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {tool.secret}"
        elif tool.auth_mode == "header" and tool.auth_name:
            headers[tool.auth_name] = tool.secret
        elif tool.auth_mode == "query" and tool.auth_name:
            query[tool.auth_name] = tool.secret
    return url, query, headers, body


async def dry_run(tool: CustomApiTool, args: dict[str, str]) -> CustomApiToolTestResult:
    """Run the real :func:`call` path and report a short, scanned preview.

    Deliberately not a shortcut: a check that takes a different path can pass
    while the real call fails, which makes it worse than no check at all.

    What comes back is kept small on purpose — this endpoint is an
    authenticated outbound-request oracle. The preview is the *rendered block*,
    so it has already been truncated and injection-scanned by :func:`_shape`;
    request headers are never echoed.
    """
    started = time.monotonic()
    block = await call(tool, args)
    duration_ms = int((time.monotonic() - started) * 1000)
    ok = block.startswith(CUSTOM_API_RESULT_OPEN)
    summary = connected_common.truncate(block, CUSTOM_API_PREVIEW_MAX_CHARS)
    return CustomApiToolTestResult(
        ok=ok,
        status=200 if ok else 0,
        duration_ms=duration_ms,
        preview=summary if ok else "",
        error=None if ok else summary,
    )
