"""The canonical form that decides two addresses are one mailbox."""

from __future__ import annotations

import uuid

import pytest

from app.utils.email_identity import canonicalize, domain_of, unique_canonicals


@pytest.mark.parametrize(
    ("submitted", "expected"),
    [
        # Gmail ignores dots and everything from '+' onward.
        ("you+maestro@gmail.com", "you@gmail.com"),
        ("y.o.u@gmail.com", "you@gmail.com"),
        ("Y.O.U+tag@GMAIL.COM", "you@gmail.com"),
        # googlemail.com is the same mailbox as gmail.com.
        ("you@googlemail.com", "you@gmail.com"),
        ("y.o.u+tag@googlemail.com", "you@gmail.com"),
        # Microsoft honours dots but not sub-addressing.
        ("y.o.u+tag@outlook.com", "y.o.u@outlook.com"),
        ("you+tag@hotmail.com", "you@hotmail.com"),
        ("you+tag@live.com", "you@live.com"),
        # hotmail and outlook are distinct mailboxes, never merged.
        ("you@hotmail.com", "you@hotmail.com"),
    ],
)
def test_known_providers_are_canonicalised(submitted: str, expected: str) -> None:
    assert canonicalize(submitted) == expected


@pytest.mark.parametrize(
    "submitted",
    [
        # '+' is a legal local-part character and its meaning is provider
        # specific. A self-hosted server may treat this as a distinct mailbox,
        # so stripping it here would merge two unrelated accounts.
        "you+tag@example.com",
        "y.o.u@example.com",
        # Privacy relays are permanent addresses, not sub-addresses.
        "abc123@privaterelay.appleid.com",
        "someone@duck.com",
    ],
)
def test_unknown_domains_are_only_lowercased(submitted: str) -> None:
    assert canonicalize(submitted) == submitted.lower()


def test_a_degenerate_local_part_is_left_alone() -> None:
    """'+tag@gmail.com' canonicalises to an empty local part, which is not an
    address. Returning it would merge every such submission into one value."""
    assert canonicalize("+tag@gmail.com") == "+tag@gmail.com"


def test_surrounding_whitespace_is_stripped() -> None:
    assert canonicalize("  You+X@Gmail.com  ") == "you@gmail.com"


def test_a_string_without_an_at_sign_is_returned_lowercased() -> None:
    """EmailStr rejects these upstream; this only has to not raise."""
    assert canonicalize("NotAnAddress") == "notanaddress"


def test_domain_of_returns_the_lowercased_domain() -> None:
    assert domain_of("You@Example.COM") == "example.com"
    assert domain_of("no-at-sign") == ""


def test_unique_canonicals_drops_every_colliding_group() -> None:
    """The migration backfill rule: a group that would violate the unique
    index is left out entirely, so those rows keep NULL and are grandfathered."""
    alice, bob, carol = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    result = unique_canonicals(
        [
            (alice, "you@gmail.com"),
            (bob, "y.o.u+tag@gmail.com"),
            (carol, "solo@example.com"),
        ]
    )

    assert result == {carol: "solo@example.com"}


def test_unique_canonicals_keeps_every_distinct_row() -> None:
    alice, bob = uuid.uuid4(), uuid.uuid4()

    result = unique_canonicals([(alice, "a@gmail.com"), (bob, "b@gmail.com")])

    assert result == {alice: "a@gmail.com", bob: "b@gmail.com"}
