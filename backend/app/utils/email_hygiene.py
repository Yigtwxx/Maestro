"""Domain-level admission checks for an address entering the system.

Two rejections live here, and both depend **only on the submitted domain** --
never on whether an account exists. That is what makes them safe to answer
visibly with a 400 while `/register` keeps the byte-identical response CLAUDE.md
§8 requires for the account-existence question. The one check that *does* depend
on existing accounts -- canonical uniqueness -- is deliberately not here: it is
enforced by the `users.canonical_email` unique index, so it surfaces as an
IntegrityError instead of a read-then-write with a timing oracle in front of it.

Admin addresses skip everything, the same way `quota_service`, the concurrency
cap and the storage caps run unmetered for admins so the operator can still
load-test. The list is the existing `GRANT_ADMIN_EMAILS`; both sides of the
comparison are canonicalised, which is what lets an operator listed once open
unlimited `+loadtest` accounts.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.constants import EMAIL_RELAY_DOMAINS
from app.utils.disposable_domains import DISPOSABLE_EMAIL_DOMAINS
from app.utils.email_identity import canonicalize, domain_of


def is_disposable(email: str) -> bool:
    """Report whether ``email`` belongs to a known throwaway provider."""
    if not settings.disposable_email_block_enabled:
        return False
    domain = domain_of(email)
    if domain in EMAIL_RELAY_DOMAINS:
        return False
    return domain in DISPOSABLE_EMAIL_DOMAINS or domain in _extra_domains()


def is_exempt(email: str) -> bool:
    """Report whether ``email`` is one of the operator's admin addresses."""
    configured = settings.grant_admin_emails
    if not configured:
        return False
    target = canonicalize(email)
    return any(
        canonicalize(entry) == target
        for entry in configured.split(",")
        if entry.strip()
    )


def canonical_for_storage(email: str) -> str | None:
    """The value for ``users.canonical_email``.

    ``None`` for an exempt address: NULL is how the exemption reaches the unique
    index, since Postgres does not conflict on NULL. It is the same mechanism
    that grandfathers pre-existing colliding rows in migration 0019.
    """
    if is_exempt(email):
        return None
    return canonicalize(email)


def _extra_domains() -> frozenset[str]:
    """Parse the operator's additions.

    Parsed per call rather than cached at import: the value is a short string,
    and a cache would go stale whenever a test or a reload changes the setting.
    """
    return frozenset(
        entry.strip().lower()
        for entry in settings.disposable_domains_extra.split(",")
        if entry.strip()
    )
