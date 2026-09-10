"""The plugin manifest, and the payloads around installing one.

A plugin bundles skills, MCP server *definitions* and agents so a whole way of
working installs in one action. Three rules are baked into the shape of this
file rather than left to the service, because a schema refuses with a field name
and a service refuses with prose.

**No credential, anywhere, ever.** There is no ``secret`` field on any member of
a manifest, so ``extra="forbid"`` makes one a 422 rather than a silent drop. A
plugin declares *where* a server is and *how* it authenticates, never *with
what*; the installed record lands with no secret and — when the server needs one
— disabled, and the installer supplies their own. This is the plugin-era
restatement of ``marketplace_service.install`` passing a literal
``mcp_server_ids=[]``, and it is the most important rule here.

**No tool schemas.** A manifest cannot ship an MCP server's tool descriptions.
Those are prompt text written by a third party, and the only place they may
enter is discovery, which scans and rebuilds them. A manifest that could carry
them would carry prompt text with no scan behind it.

**No executable member.** No code, no hooks, no commands. This is a bundle of
declarations. Adding an executable member is not a feature increment; it is a
different security review.

Every member is re-validated through the *real* create schema at install time
(``SkillCreate``, ``McpServerCreate``, ``AgentConfigCreate``), so there is
exactly one authority per record type and this file only has to describe the
bundle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import (
    MCP_SERVER_SLUG_PATTERN,
    PLUGIN_DESCRIPTION_MAX_CHARS,
    PLUGIN_ID_PATTERN,
    PLUGIN_MANIFEST_VERSION,
    PLUGIN_MAX_AGENTS,
    PLUGIN_MAX_MCP_SERVERS,
    PLUGIN_MAX_SKILLS,
    PLUGIN_NAME_MAX_CHARS,
    PLUGIN_VERSION_PATTERN,
    SKILL_INSTRUCTIONS_MAX_CHARS,
    SKILL_SLUG_PATTERN,
)
from app.schemas.mcp_server import McpAuthMode, McpTransport
from app.utils.url_guard import validate_url_shape


class PluginSkill(BaseModel):
    """A skill a plugin creates in the installer's account."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=SKILL_SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=280)
    instructions: str = Field(min_length=1, max_length=SKILL_INSTRUCTIONS_MAX_CHARS)
    output_format: str = Field(default="", max_length=2000)
    required_tools: list[str] = Field(default_factory=list, max_length=20)


class PluginMcpServer(BaseModel):
    """An MCP server *definition*. Note what is absent: any credential.

    ``tools`` is absent too, and deliberately: a catalog is discovered, scanned
    and rebuilt, never shipped.
    """

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=MCP_SERVER_SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=280)
    url: str = Field(min_length=1, max_length=500)
    transport: McpTransport = "streamable_http"
    auth_mode: McpAuthMode = "none"
    auth_name: str = Field(default="", max_length=80)
    timeout_seconds: int = Field(default=30, ge=1, le=120)

    @model_validator(mode="after")
    def _validate(self) -> PluginMcpServer:
        reason = validate_url_shape(self.url)
        if reason is not None:
            raise ValueError(f"url rejected: {reason}.")
        if self.auth_mode == "header" and not self.auth_name.strip():
            raise ValueError("auth_name is required for auth_mode 'header'.")
        return self


class PluginAgent(BaseModel):
    """An agent a plugin creates, referring to its siblings by manifest slug."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=SKILL_SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    domain: str = Field(min_length=1, max_length=40)
    system_prompt: str = Field(min_length=1, max_length=8000)
    tools: list[str] = Field(default_factory=list, max_length=30)
    description: str = Field(default="", max_length=280)
    routing_hint: str = Field(default="", max_length=280)
    output_format: str = Field(default="", max_length=2000)
    routable: bool = False
    # Resolved to freshly created ids at install. Slugs within *this* manifest
    # only — there is deliberately no way to reference another plugin's records.
    skill_slugs: list[str] = Field(default_factory=list, max_length=PLUGIN_MAX_SKILLS)
    mcp_server_slugs: list[str] = Field(
        default_factory=list, max_length=PLUGIN_MAX_MCP_SERVERS
    )


class PluginManifest(BaseModel):
    """One bundle, as published or imported."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal[PLUGIN_MANIFEST_VERSION] = PLUGIN_MANIFEST_VERSION
    id: str = Field(pattern=PLUGIN_ID_PATTERN)
    name: str = Field(min_length=1, max_length=PLUGIN_NAME_MAX_CHARS)
    version: str = Field(pattern=PLUGIN_VERSION_PATTERN)
    description: str = Field(default="", max_length=PLUGIN_DESCRIPTION_MAX_CHARS)
    homepage: str = Field(default="", max_length=500)
    # A display label only. Never trusted for anything — a manifest cannot
    # assert who wrote it.
    author: str = Field(default="", max_length=80)

    skills: list[PluginSkill] = Field(
        default_factory=list, max_length=PLUGIN_MAX_SKILLS
    )
    mcp_servers: list[PluginMcpServer] = Field(
        default_factory=list, max_length=PLUGIN_MAX_MCP_SERVERS
    )
    agents: list[PluginAgent] = Field(
        default_factory=list, max_length=PLUGIN_MAX_AGENTS
    )

    @model_validator(mode="after")
    def _validate(self) -> PluginManifest:
        if self.homepage:
            reason = validate_url_shape(self.homepage)
            if reason is not None:
                raise ValueError(f"homepage rejected: {reason}.")
        if not (self.skills or self.mcp_servers or self.agents):
            raise ValueError("a plugin must declare at least one member.")

        for group, label in (
            (self.skills, "skill"),
            (self.mcp_servers, "mcp_server"),
            (self.agents, "agent"),
        ):
            slugs = [member.slug for member in group]
            if len(set(slugs)) != len(slugs):
                raise ValueError(f"duplicate {label} slug in the manifest.")

        skill_slugs = {member.slug for member in self.skills}
        server_slugs = {member.slug for member in self.mcp_servers}
        for agent in self.agents:
            # Resolved at install, so an unresolvable reference has to fail
            # here — otherwise it becomes a half-installed agent missing the
            # thing it was published to use.
            unknown = set(agent.skill_slugs) - skill_slugs
            if unknown:
                raise ValueError(
                    f"agent '{agent.slug}' references unknown skills: "
                    f"{', '.join(sorted(unknown))}."
                )
            unknown = set(agent.mcp_server_slugs) - server_slugs
            if unknown:
                raise ValueError(
                    f"agent '{agent.slug}' references unknown MCP servers: "
                    f"{', '.join(sorted(unknown))}."
                )
        return self


class PluginPublish(BaseModel):
    """Payload to publish a bundle to the catalog."""

    model_config = ConfigDict(extra="forbid")

    manifest: PluginManifest


class PluginImport(BaseModel):
    """Payload to import a manifest from a URL the user supplies."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _validate(self) -> PluginImport:
        reason = validate_url_shape(self.url)
        if reason is not None:
            raise ValueError(f"url rejected: {reason}.")
        return self


class PluginPublic(BaseModel):
    """A catalog entry, as browsed. Never carries the author's identity."""

    id: str
    plugin_id: str
    name: str
    description: str
    version: str
    author_label: str
    installs: int
    featured: bool = False
    created_at: datetime


class PluginDetail(PluginPublic):
    """A catalog entry with the manifest, for the install confirmation."""

    manifest: PluginManifest


class PluginInstallMember(BaseModel):
    """One record an install created, or an uninstall would delete."""

    kind: Literal["skill", "mcp_server", "agent"]
    id: str
    name: str
    # True when the user changed it after installing. Surfaced so an uninstall
    # can say what it is about to throw away.
    edited: bool = False


class PluginInstallPublic(BaseModel):
    """An installed plugin, as shown to its owner."""

    id: str
    plugin_id: str
    name: str
    version: str
    source: Literal["catalog", "url"]
    origin_url: str | None = None
    created_skill_ids: list[str] = Field(default_factory=list)
    created_mcp_server_ids: list[str] = Field(default_factory=list)
    created_agent_ids: list[str] = Field(default_factory=list)
    # Servers that landed disabled because they need a credential the manifest
    # could not carry. The one thing a user must do after installing.
    needs_credentials: list[str] = Field(default_factory=list)
    installed_at: datetime
    updated_at: datetime


class PluginUninstallPreview(BaseModel):
    """What a delete would remove, so the confirmation can list it."""

    plugin_id: str
    name: str
    members: list[PluginInstallMember] = Field(default_factory=list)


class PluginUpgradeChange(BaseModel):
    """One member's fate in an upgrade, and why."""

    kind: Literal["skill", "mcp_server", "agent"]
    slug: str
    name: str = ""
    action: Literal["created", "updated", "unchanged", "removed", "conflict"]
    # Fields the new version changed and this upgrade applied.
    applied: list[str] = Field(default_factory=list)
    # Fields the new version changed that the *user* had also changed, so they
    # were left alone. This is the whole reason the upgrade is a three-way merge
    # rather than an overwrite.
    conflicted: list[str] = Field(default_factory=list)
    note: str = ""


class PluginUpgradeResult(BaseModel):
    """What an upgrade did, or would do when ``dry_run`` was set.

    One shape for both, so the preview a user approves is produced by the same
    code that applies it — a separate preview path is a preview that can drift
    from what happens.
    """

    dry_run: bool
    from_version: str
    to_version: str
    changed: bool
    changes: list[PluginUpgradeChange] = Field(default_factory=list)
