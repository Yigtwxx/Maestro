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

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.constants import EMAIL_RELAY_DOMAINS
from app.core.metrics import metrics
from app.utils import mx_check
from app.utils.disposable_domains import DISPOSABLE_EMAIL_DOMAINS
from app.utils.email_identity import canonicalize, domain_of

_DISPOSABLE_REASON = "disposable_domain"
_NO_MX_REASON = "no_mx"

# Shared instances, matching `auth._INVALID_MFA`. Neither message names the
# submitted address: these responses are read by whoever typed it, but they also
# land in logs and support tickets.
_DISPOSABLE_DOMAIN = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="That email provider isn't supported. Please use a permanent address.",
)
_UNREACHABLE_DOMAIN = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="That email domain can't receive mail. Please check the address.",
)


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


async def enforce(email: str) -> None:
    """Admit ``email`` or raise 400, skipping everything for an admin address.

    Raises rather than returning a bool, following
    `utils.login_throttle.password.enforce`. `mail_budget.allow` returns instead
    because its caller must answer with a *normal* body; here a visible refusal
    is correct -- both rejections read only the domain, so neither can be turned
    into an account-existence oracle.
    """
    if is_exempt(email):
        return
    if is_disposable(email):
        metrics.record_abuse_rejection(_DISPOSABLE_REASON)
        raise _DISPOSABLE_DOMAIN
    if not await mx_check.has_mx(email):
        metrics.record_abuse_rejection(_NO_MX_REASON)
        raise _UNREACHABLE_DOMAIN


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
