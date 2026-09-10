"""What a manifest may and may not declare.

Three of these are the rules the whole feature rests on: no credential, no tool
schemas, no executable member. Each is enforced by *omission* — the field does
not exist, and ``extra="forbid"`` turns naming it into a 422 with a field path
rather than a silent drop that a publisher would never learn about.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.constants import PLUGIN_MAX_AGENTS, PLUGIN_MAX_SKILLS
from app.schemas.plugin import PluginManifest

_BASE = {"id": "acme.research", "name": "Research Kit", "version": "1.0.0"}


def _manifest(**overrides) -> dict:
    return {
        **_BASE,
        "skills": [{"slug": "teardown", "name": "T", "instructions": "do it"}],
        **overrides,
    }


def test_a_minimal_manifest_is_accepted():
    assert PluginManifest(**_manifest()).id == "acme.research"


# --- the three rules --------------------------------------------------------


@pytest.mark.parametrize(
    "member,field",
    [
        ("mcp_servers", "secret"),
        ("mcp_servers", "encrypted_secret"),
        ("mcp_servers", "secret_hint"),
    ],
)
def test_no_credential_field_exists_anywhere(member, field):
    """The most important rule here.

    A plugin declares *where* a server is and *how* it authenticates, never
    *with what*. The installed record lands with no secret, disabled, for the
    installer to fill in — the plugin-era restatement of ``install`` passing a
    literal ``mcp_server_ids=[]``.
    """
    with pytest.raises(ValidationError, match=field):
        PluginManifest(
            **_manifest(
                **{
                    member: [
                        {
                            "slug": "acme",
                            "name": "A",
                            "url": "https://mcp.example.com/mcp",
                            field: "sk-live-1",
                        }
                    ]
                }
            )
        )


def test_a_manifest_cannot_ship_tool_schemas():
    """Prompt text with no discovery-time scan behind it."""
    with pytest.raises(ValidationError, match="tools"):
        PluginManifest(
            **_manifest(
                mcp_servers=[
                    {
                        "slug": "acme",
                        "name": "A",
                        "url": "https://mcp.example.com/mcp",
                        "tools": [{"name": "search", "description": "…"}],
                    }
                ]
            )
        )


@pytest.mark.parametrize("field", ["hooks", "commands", "scripts", "code"])
def test_a_manifest_cannot_carry_an_executable_member(field):
    """This is a bundle of declarations.

    Adding an executable member is not a feature increment; it is a different
    security review.
    """
    with pytest.raises(ValidationError, match=field):
        PluginManifest(**_manifest(**{field: ["anything"]}))


# --- structure --------------------------------------------------------------


def test_an_empty_bundle_is_refused():
    with pytest.raises(ValidationError, match="at least one member"):
        PluginManifest(**_BASE)


def test_a_dangling_reference_is_refused():
    """Resolved at install, so an unresolvable slug has to fail here — otherwise
    it becomes a half-installed agent missing what it was published to use."""
    with pytest.raises(ValidationError, match="unknown skills"):
        PluginManifest(
            **_manifest(
                agents=[
                    {
                        "slug": "ag",
                        "name": "A",
                        "domain": "general",
                        "system_prompt": "p",
                        "skill_slugs": ["not-declared"],
                    }
                ]
            )
        )


def test_a_duplicate_slug_within_one_group_is_refused():
    with pytest.raises(ValidationError, match="duplicate skill slug"):
        PluginManifest(
            **_manifest(
                skills=[
                    {"slug": "teardown", "name": "A", "instructions": "x"},
                    {"slug": "teardown", "name": "B", "instructions": "y"},
                ]
            )
        )


@pytest.mark.parametrize(
    "group,cap",
    [("skills", PLUGIN_MAX_SKILLS), ("agents", PLUGIN_MAX_AGENTS)],
)
def test_the_structural_caps_are_a_422_naming_the_field(group, cap):
    """A cap in the schema fails with a field name; a cap in the service fails
    halfway through writing records."""
    member = (
        {"slug": "s", "name": "N", "instructions": "x"}
        if group == "skills"
        else {"slug": "s", "name": "N", "domain": "general", "system_prompt": "p"}
    )
    members = [{**member, "slug": f"member-{i}"} for i in range(cap + 1)]
    with pytest.raises(ValidationError, match=group):
        PluginManifest(**_manifest(**{group: members}))


@pytest.mark.parametrize("version", ["1", "1.0", "v1.0.0", "1.0.0-beta", ""])
def test_a_malformed_version_is_refused(version):
    with pytest.raises(ValidationError, match="version"):
        PluginManifest(**_manifest(version=version))


@pytest.mark.parametrize("plugin_id", ["Acme.Kit", "ab", "acme kit", "acme/kit"])
def test_a_malformed_plugin_id_is_refused(plugin_id):
    with pytest.raises(ValidationError, match="id"):
        PluginManifest(**_manifest(id=plugin_id))


def test_an_unknown_manifest_version_is_refused():
    with pytest.raises(ValidationError, match="manifest_version"):
        PluginManifest(**_manifest(manifest_version=2))


def test_a_credentialed_url_is_refused():
    with pytest.raises(ValidationError, match="url"):
        PluginManifest(
            **_manifest(
                mcp_servers=[
                    {
                        "slug": "acme",
                        "name": "A",
                        "url": "http://user:pw@mcp.example.com/mcp",
                    }
                ]
            )
        )


def test_a_stdio_transport_is_refused():
    """Typed, so it is a 422 with a field name rather than a runtime branch."""
    with pytest.raises(ValidationError, match="transport"):
        PluginManifest(
            **_manifest(
                mcp_servers=[
                    {
                        "slug": "acme",
                        "name": "A",
                        "url": "https://mcp.example.com/mcp",
                        "transport": "stdio",
                    }
                ]
            )
        )


# --- the digest -------------------------------------------------------------


def test_the_digest_ignores_formatting_but_not_content():
    from app.services.plugin_service import manifest_digest

    one = PluginManifest(**_manifest())
    two = PluginManifest(**_manifest())
    assert manifest_digest(one) == manifest_digest(two)

    changed = PluginManifest(
        **_manifest(
            skills=[{"slug": "teardown", "name": "T", "instructions": "do it twice"}]
        )
    )
    assert manifest_digest(changed) != manifest_digest(one)
