"""Domain groups: the invariants the two-stage router and the catalog rest on.

A group is not a label. Stage-one routing narrows to one of these and stage two
only ever sees that group's members, so a domain in the wrong group — or in no
group — is unreachable from automatic routing however good its ``routing_hint``
is. The catalog tabs and the colour palette key off the same ids.
"""

from __future__ import annotations

from app.agents.registry import (
    DEFAULT_DOMAIN,
    DEFAULT_GROUP,
    DOMAIN_CATALOG,
    DOMAIN_GROUP_CATALOG,
    DOMAINS,
    domains_in_group,
    get_domain_info,
    get_group_info,
)


def test_group_definitions_are_complete() -> None:
    for group in DOMAIN_GROUP_CATALOG:
        assert group.id, "group with no id"
        assert group.name, f"{group.id}: empty name"
        assert group.description, f"{group.id}: empty description"
        assert group.routing_hint, f"{group.id}: empty routing_hint"
        assert group.default_domain, f"{group.id}: empty default_domain"


def test_group_ids_are_unique() -> None:
    ids = [group.id for group in DOMAIN_GROUP_CATALOG]
    assert len(ids) == len(set(ids)), f"duplicate group ids: {ids}"


def test_every_domain_belongs_to_a_known_group() -> None:
    known = {group.id for group in DOMAIN_GROUP_CATALOG}
    for entry in DOMAIN_CATALOG:
        assert entry.group, f"{entry.id}: no group"
        assert entry.group in known, f"{entry.id}: unknown group {entry.group!r}"


def test_every_group_holds_at_least_one_domain() -> None:
    """An empty group is a routing dead end.

    Stage one can still choose it, and stage two then has nothing to offer, so
    every prompt landing there falls through to the group's default.
    """
    for group in DOMAIN_GROUP_CATALOG:
        assert domains_in_group(group.id), f"{group.id}: no domains"


def test_group_default_domain_belongs_to_that_group() -> None:
    """Stage two falls back here, so it must be a member.

    A default pointing outside its group would silently undo the group the
    first stage just chose.
    """
    for group in DOMAIN_GROUP_CATALOG:
        assert group.default_domain in DOMAINS, (
            f"{group.id}: default_domain {group.default_domain!r} is not a domain"
        )
        assert get_domain_info(group.default_domain).group == group.id, (
            f"{group.id}: default_domain {group.default_domain!r} is in another group"
        )


def test_catalog_is_ordered_by_group_in_contiguous_blocks() -> None:
    """Catalog order is the frontend's order and the catalog tabs' order.

    Interleaving two groups would put a squad under a tab in a position no
    reader expects, and ``AGENT_DOMAINS`` mirrors the same order index for
    index.
    """
    seen: list[str] = []
    for entry in DOMAIN_CATALOG:
        if not seen or seen[-1] != entry.group:
            assert entry.group not in seen, (
                f"group {entry.group!r} appears in two separate blocks"
            )
            seen.append(entry.group)
    expected = [group.id for group in DOMAIN_GROUP_CATALOG]
    assert seen == expected, f"catalog group order {seen} != catalog {expected}"


def test_general_is_last_and_lives_in_the_default_group() -> None:
    """``general`` is the routing fallback for both stages.

    Stage one falls back to ``DEFAULT_GROUP`` and stage two to that group's
    default, so the two paths only agree while ``general`` is that default.
    """
    assert DOMAIN_CATALOG[-1].id == DEFAULT_DOMAIN, "general must stay last"
    assert get_domain_info(DEFAULT_DOMAIN).group == DEFAULT_GROUP
    assert get_group_info(DEFAULT_GROUP).default_domain == DEFAULT_DOMAIN


def test_unknown_group_resolves_to_the_default() -> None:
    assert get_group_info("nope").id == DEFAULT_GROUP
    assert get_group_info("").id == DEFAULT_GROUP
    assert domains_in_group("nope") == ()
