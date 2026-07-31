"""The canonical form of an email address.

Two addresses share a canonical form when they reach one mailbox. This is what
lets `users.canonical_email` carry a unique index that bounds an account per
inbox rather than per typed string: `you+1@gmail.com`, `you+2@gmail.com` and
`y.o.u@gmail.com` are one mailbox and must be one account.

The rule is applied only to `EMAIL_CANONICAL_PROVIDERS`. Sub-addressing is not
a standard -- `+` is an ordinary local-part character and the receiving server
decides what it means -- so an unknown domain is lowercased and otherwise left
exactly as typed.

Pure by design: no settings, no I/O, no database. The switchable and networked
parts of email hygiene live in `email_hygiene` and `mx_check`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.core.constants import EMAIL_CANONICAL_PROVIDERS, EMAIL_SUBADDRESS_SEPARATOR


def canonicalize(email: str) -> str:
    """Return the canonical form of ``email``.

    Always safe to call: a value that is not an address is lowercased and
    returned, because `EmailStr` has already rejected those upstream and this
    function must not raise on data already in the database.
    """
    normalised = email.strip().lower()
    local, separator, domain = normalised.rpartition("@")
    if not separator:
        return normalised
    rules = EMAIL_CANONICAL_PROVIDERS.get(domain)
    if rules is None:
        return normalised
    strip_dots, canonical_domain = rules
    local = local.split(EMAIL_SUBADDRESS_SEPARATOR, 1)[0]
    if strip_dots:
        local = local.replace(".", "")
    if not local:
        # `+tag@gmail.com` has nothing left. Collapsing every such submission
        # to one empty-local value would merge unrelated accounts, so leave it.
        return normalised
    return f"{local}@{canonical_domain}"


def domain_of(email: str) -> str:
    """Return the lowercased domain, or an empty string if there is no ``@``."""
    normalised = email.strip().lower()
    local, separator, domain = normalised.rpartition("@")
    return domain if separator else ""


def unique_canonicals(rows: Sequence[tuple[Any, str]]) -> dict[Any, str]:
    """Map each row id to its canonical address, dropping colliding groups.

    The backfill rule for migration 0019. Rows already in the database may
    collide under the new rule (accounts that were one mailbox all along);
    creating the unique index over them would fail. Every member of a colliding
    group is omitted here so its column stays NULL -- Postgres unique indexes do
    not conflict on NULL, which grandfathers those accounts while every new
    registration still writes a value.

    Lives here rather than inside the migration so it is importable and
    therefore testable: `alembic/versions` module names begin with a digit.
    """
    canonical_by_id = {row_id: canonicalize(email) for row_id, email in rows}
    counts: dict[str, int] = {}
    for canonical in canonical_by_id.values():
        counts[canonical] = counts.get(canonical, 0) + 1
    return {
        row_id: canonical
        for row_id, canonical in canonical_by_id.items()
        if counts[canonical] == 1
    }
