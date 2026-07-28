"""Schemas for user-registered HTTP endpoints exposed to agents as tools.

This is the only place in the product where a *user* supplies the hostname an
outbound request goes to, so validation here is a security boundary rather than
input hygiene. Three things are enforced before a record can exist:

* the base URL passes ``url_guard.validate_url_shape`` — the same check
  ``schemas/api_key`` already applies to a custom LLM endpoint (CLAUDE.md §8);
* the path template cannot escape the base or smuggle a query/fragment, and
  every ``{placeholder}`` in it is a parameter the model is actually allowed to
  fill;
* static headers cannot carry a second credential or rebind ``Host``.

DNS resolution is deliberately *not* done here. ``validate_url_shape`` is sync
and DNS-free by design; the resolving check runs in the route and again at call
time, because a record outlives its validation.
"""

from __future__ import annotations

import string
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import (
    CUSTOM_API_ARG_MAX_CHARS,
    CUSTOM_API_FORBIDDEN_HEADERS,
    CUSTOM_API_MAX_ENUM_VALUES,
    CUSTOM_API_MAX_HEADERS,
    CUSTOM_API_MAX_PARAMETERS,
    CUSTOM_API_MAX_QUERY_PARAMS,
    CUSTOM_API_PARAM_PATTERN,
    CUSTOM_API_RESULT_MAX_CHARS,
    CUSTOM_API_SLUG_PATTERN,
)
from app.utils.url_guard import validate_url_shape

AuthMode = Literal["none", "bearer", "header", "query"]
HttpMethod = Literal["GET", "POST"]
ParameterType = Literal["string", "integer", "number", "boolean"]

# Anything that could take the request off the base path or start a new URL
# component. Checked as substrings because a template is not a parsed URL.
_FORBIDDEN_IN_PATH = ("..", "//", "?", "#", "\\", "://")


class CustomApiParameter(BaseModel):
    """One argument the model may fill when calling this endpoint."""

    name: str = Field(pattern=CUSTOM_API_PARAM_PATTERN)
    type: ParameterType = "string"
    description: str = Field(default="", max_length=200)
    required: bool = False
    enum: list[str] | None = Field(default=None, max_length=CUSTOM_API_MAX_ENUM_VALUES)


def _placeholders(template: str) -> set[str]:
    """Field names in a ``{brace}`` template, ignoring literal text."""
    return {
        name for _, name, _, _ in string.Formatter().parse(template) if name is not None
    }


def _collect_placeholders(
    path_template: str,
    query_template: dict[str, str],
    body_template: dict[str, Any] | None,
) -> set[str]:
    found = _placeholders(path_template)
    for value in query_template.values():
        found |= _placeholders(str(value))
    if body_template:
        # Only string leaves can carry a placeholder; a nested structure is
        # walked so a template two levels down is still validated.
        stack: list[Any] = [body_template]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, str):
                found |= _placeholders(node)
    return found


class _CustomApiToolBase(BaseModel):
    """Shared validation for create and update."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate(self) -> _CustomApiToolBase:
        base_url = getattr(self, "base_url", None)
        if base_url is not None:
            reason = validate_url_shape(base_url)
            if reason:
                raise ValueError(f"base_url rejected: {reason}")
            # A query or fragment on the base would be silently dropped once
            # httpx builds params, so refuse it rather than ignore it.
            if "?" in base_url or "#" in base_url:
                raise ValueError("base_url must not carry a query string or fragment.")

        path_template = getattr(self, "path_template", None)
        if path_template is not None:
            if not path_template.startswith("/"):
                raise ValueError("path_template must start with '/'.")
            for token in _FORBIDDEN_IN_PATH:
                if token in path_template:
                    raise ValueError(f"path_template must not contain {token!r}.")

        headers = getattr(self, "headers", None)
        if headers is not None:
            for name in headers:
                if name.lower() in CUSTOM_API_FORBIDDEN_HEADERS:
                    raise ValueError(
                        f"header {name!r} is set by the platform and cannot be "
                        "overridden. Use auth_mode to attach a credential."
                    )
                if not name.isascii() or not name.strip() or "\n" in name:
                    raise ValueError(f"header name {name!r} is not a valid token.")

        # Every placeholder must be a declared parameter. Without this the model
        # could be handed a template it can never satisfy, and a stray
        # "{secret}" would be substituted from nothing at call time.
        parameters = getattr(self, "parameters", None)
        if parameters is not None and path_template is not None:
            declared = {p.name for p in parameters}
            used = _collect_placeholders(
                path_template,
                getattr(self, "query_template", None) or {},
                getattr(self, "body_template", None),
            )
            unknown = used - declared
            if unknown:
                raise ValueError(
                    "template references undeclared parameters: "
                    + ", ".join(sorted(unknown))
                )

        auth_mode = getattr(self, "auth_mode", None)
        if auth_mode is not None and auth_mode != "none":
            if not getattr(self, "auth_name", "") and auth_mode != "bearer":
                raise ValueError(f"auth_name is required for auth_mode {auth_mode!r}.")

        method = getattr(self, "method", None)
        if getattr(self, "body_template", None) and method == "GET":
            raise ValueError("body_template is only valid for POST.")
        return self


class CustomApiToolCreate(_CustomApiToolBase):
    """Payload to register an endpoint."""

    slug: str = Field(pattern=CUSTOM_API_SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=280)
    method: HttpMethod = "GET"
    base_url: str = Field(min_length=1, max_length=500)
    path_template: str = Field(default="/", max_length=300)
    query_template: dict[str, str] = Field(
        default_factory=dict, max_length=CUSTOM_API_MAX_QUERY_PARAMS
    )
    headers: dict[str, str] = Field(
        default_factory=dict, max_length=CUSTOM_API_MAX_HEADERS
    )
    auth_mode: AuthMode = "none"
    auth_name: str = Field(default="", max_length=80)
    # Write-only: echoed back as ``secret_hint`` and never in full.
    secret: str | None = Field(default=None, max_length=4000)
    parameters: list[CustomApiParameter] = Field(
        default_factory=list, max_length=CUSTOM_API_MAX_PARAMETERS
    )
    body_template: dict[str, Any] | None = None
    response_json_path: str = Field(default="", max_length=120)
    response_max_chars: int = Field(
        default=CUSTOM_API_RESULT_MAX_CHARS, ge=200, le=CUSTOM_API_RESULT_MAX_CHARS
    )
    timeout_seconds: int = Field(default=15, ge=1, le=60)
    enabled: bool = True

    @model_validator(mode="after")
    def _require_secret_for_auth(self) -> CustomApiToolCreate:
        if self.auth_mode != "none" and not self.secret:
            raise ValueError(f"secret is required for auth_mode {self.auth_mode!r}.")
        return self


class CustomApiToolUpdate(_CustomApiToolBase):
    """Partial update. Only the provided fields change.

    ``secret=None`` means *leave the stored credential alone*, never "clear it":
    a PATCH that only renames the tool must not silently break a working call.
    """

    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=280)
    method: HttpMethod | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    path_template: str | None = Field(default=None, max_length=300)
    query_template: dict[str, str] | None = Field(
        default=None, max_length=CUSTOM_API_MAX_QUERY_PARAMS
    )
    headers: dict[str, str] | None = Field(
        default=None, max_length=CUSTOM_API_MAX_HEADERS
    )
    auth_mode: AuthMode | None = None
    auth_name: str | None = Field(default=None, max_length=80)
    secret: str | None = Field(default=None, max_length=4000)
    parameters: list[CustomApiParameter] | None = Field(
        default=None, max_length=CUSTOM_API_MAX_PARAMETERS
    )
    body_template: dict[str, Any] | None = None
    response_json_path: str | None = Field(default=None, max_length=120)
    response_max_chars: int | None = Field(
        default=None, ge=200, le=CUSTOM_API_RESULT_MAX_CHARS
    )
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    enabled: bool | None = None


class CustomApiToolPublic(BaseModel):
    """An endpoint as returned to its owner.

    The field list is the secret boundary and is deliberately explicit: no
    ``encrypted_secret``, no ``user_id``. The service also projects both away at
    the query, so the ciphertext never leaves it even if this model gains a
    field by accident.
    """

    id: str
    slug: str
    name: str
    description: str
    method: HttpMethod
    base_url: str
    path_template: str
    query_template: dict[str, str]
    headers: dict[str, str]
    auth_mode: AuthMode
    auth_name: str
    secret_hint: str | None = None
    parameters: list[CustomApiParameter]
    body_template: dict[str, Any] | None = None
    response_json_path: str = ""
    response_max_chars: int
    timeout_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class CustomApiToolTestRequest(BaseModel):
    """Arguments for one dry run, shaped like a model-supplied directive."""

    model_config = ConfigDict(extra="forbid")

    args: dict[str, str] = Field(
        default_factory=dict, max_length=CUSTOM_API_MAX_PARAMETERS
    )

    @model_validator(mode="after")
    def _cap_values(self) -> CustomApiToolTestRequest:
        for key, value in self.args.items():
            if len(value) > CUSTOM_API_ARG_MAX_CHARS:
                raise ValueError(f"argument {key!r} is too long.")
        return self


class CustomApiToolTestResult(BaseModel):
    """What a dry run did. ``preview`` is capped and injection-scanned."""

    ok: bool
    status: int
    duration_ms: int
    preview: str = ""
    error: str | None = None
