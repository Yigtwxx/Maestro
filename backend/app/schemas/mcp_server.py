"""Schemas for user-registered remote MCP servers.

The second place in the product where a *user* supplies the hostname an outbound
request goes to, so — like ``schemas/custom_api_tool`` — this is a security
boundary rather than input hygiene. It enforces the same three things, with two
deliberate divergences noted below:

* the URL passes ``url_guard.validate_url_shape`` (sync and DNS-free by design;
  the resolving check runs in the route and again on every POST, because a
  record outlives its validation);
* static headers cannot carry a second credential, rebind ``Host``, or override
  a header the protocol needs;
* ``transport`` is a ``Literal``, so "no local stdio" is a typed 422 with a field
  name on it rather than a runtime branch someone can add a case to.

**Divergence 1: a query string is allowed.** ``custom_api``'s ``base_url``
rejects one, because that record composes a URL from a template and a query
would collide with it. An MCP endpoint is used verbatim, and several hosted
gateways key a tenant off ``?token=…`` — refusing one would refuse those
servers outright. It is preserved as written and never merged with params.

**Divergence 2: the auth modes are narrower.** No ``query`` mode: an MCP
endpoint is called repeatedly with a session header, and a credential in the
URL would be re-sent on every hop and land in any intermediary's access log.
OAuth is not offered either — see ``docs`` and CLAUDE.md §8.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import (
    MCP_FORBIDDEN_HEADERS,
    MCP_SERVER_SLUG_PATTERN,
    MCP_TOOLS_PER_SERVER_MAX,
)
from app.utils.url_guard import validate_url_shape

McpAuthMode = Literal["none", "bearer", "header"]
McpTransport = Literal["streamable_http"]

_MAX_HEADERS = 10


def _validate_headers(headers: dict[str, str]) -> None:
    """Refuse a header that would smuggle a credential or break the protocol."""
    for name, value in headers.items():
        lowered = name.strip().lower()
        if lowered in MCP_FORBIDDEN_HEADERS:
            raise ValueError(f"header {name!r} is set by Maestro and cannot be given.")
        if not name.strip() or not name.isascii():
            raise ValueError(f"header name {name!r} must be non-empty ASCII.")
        # CRLF in either half is header injection; non-ASCII values are refused
        # for the same reason httpx would reject them, but with a clear message.
        if not value.isascii() or "\r" in value or "\n" in value:
            raise ValueError(f"header {name!r} has an invalid value.")


class _McpServerBase(BaseModel):
    """Shared validation for the create and update payloads."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate(self) -> _McpServerBase:
        url = getattr(self, "url", None)
        if url is not None:
            reason = validate_url_shape(url)
            if reason is not None:
                raise ValueError(f"url rejected: {reason}.")
            if "#" in url:
                raise ValueError("url must not carry a fragment.")

        headers = getattr(self, "headers", None)
        if headers:
            _validate_headers(headers)

        auth_mode = getattr(self, "auth_mode", None)
        auth_name = getattr(self, "auth_name", None)
        if auth_mode == "header" and not (auth_name or "").strip():
            raise ValueError("auth_name is required for auth_mode 'header'.")
        return self


class McpServerCreate(_McpServerBase):
    """Payload to register a remote MCP server."""

    slug: str = Field(pattern=MCP_SERVER_SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=280)
    url: str = Field(min_length=1, max_length=500)
    transport: McpTransport = "streamable_http"
    headers: dict[str, str] = Field(default_factory=dict, max_length=_MAX_HEADERS)
    auth_mode: McpAuthMode = "none"
    auth_name: str = Field(default="", max_length=80)
    # Write-only: echoed back as ``secret_hint`` and never in full.
    secret: str | None = Field(default=None, max_length=4000)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    enabled: bool = True

    @model_validator(mode="after")
    def _require_secret_for_auth(self) -> McpServerCreate:
        if self.auth_mode != "none" and not self.secret:
            raise ValueError(f"secret is required for auth_mode {self.auth_mode!r}.")
        return self


class McpServerUpdate(_McpServerBase):
    """Partial update. Only the provided fields change.

    ``secret=None`` means *leave the stored credential alone*, never "clear it":
    a PATCH that only renames the server must not silently break every call.
    """

    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=280)
    url: str | None = Field(default=None, min_length=1, max_length=500)
    headers: dict[str, str] | None = Field(default=None, max_length=_MAX_HEADERS)
    auth_mode: McpAuthMode | None = None
    auth_name: str | None = Field(default=None, max_length=80)
    secret: str | None = Field(default=None, max_length=4000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=120)
    enabled: bool | None = None
    # Which discovered tools this server may offer. ``None`` leaves the stored
    # selection alone; an explicit list replaces it. Not on ``Create``: nothing
    # is discovered yet at registration time.
    tool_allowlist: list[str] | None = Field(
        default=None, max_length=MCP_TOOLS_PER_SERVER_MAX
    )


class McpToolPublic(BaseModel):
    """One discovered tool, as cached after sanitization.

    ``remote_name`` is the server's own spelling and is what ``tools/call``
    sends; ``action`` is the sanitized id the model names. Both are shown,
    because a user debugging a server needs to see the name it advertised.
    """

    action: str
    remote_name: str
    display_name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    # Set when the tool was withheld: a failed injection scan, an unusable name,
    # or a schema that could not be rebuilt within the caps.
    blocked_reason: str | None = None


class McpServerPublic(BaseModel):
    """A server as returned to its owner.

    The field list is the secret boundary and is deliberately explicit: no
    ``encrypted_secret``, no ``user_id``. The service projects both away at the
    query too, so the ciphertext never leaves it even if this model gains a
    field by accident.
    """

    id: str
    slug: str
    name: str
    description: str
    url: str
    transport: McpTransport
    headers: dict[str, str]
    auth_mode: McpAuthMode
    auth_name: str
    secret_hint: str | None = None
    timeout_seconds: int
    enabled: bool
    tool_allowlist: list[str] = Field(default_factory=list)
    tools: list[McpToolPublic] = Field(default_factory=list)
    tools_fetched_at: datetime | None = None
    # True once the cache is older than its TTL, or once a call named a tool the
    # server no longer has. Drives the "rediscover" prompt in the UI.
    tools_stale: bool = False
    protocol_version: str = ""
    server_name: str = ""
    server_version: str = ""
    source: str = "custom"
    created_at: datetime
    updated_at: datetime


class McpDiscoverResult(BaseModel):
    """The outcome of one discovery run.

    A failure is reported here rather than raised as a 500: pointing at a server
    that is down, or that refuses the handshake, is an ordinary thing for a user
    to do and the message has to say which.
    """

    ok: bool
    server_name: str = ""
    server_version: str = ""
    protocol_version: str = ""
    tools: list[McpToolPublic] = Field(default_factory=list)
    # How many the server advertised but we refused to expose.
    withheld: int = 0
    duration_ms: int = 0
    error: str | None = None
