"""Disposable providers, privacy relays and the admin exemption."""

from __future__ import annotations

from app.core.config import settings
from app.core.constants import EMAIL_CANONICAL_PROVIDERS, EMAIL_RELAY_DOMAINS
from app.utils.disposable_domains import DISPOSABLE_EMAIL_DOMAINS
from app.utils.email_hygiene import canonical_for_storage, is_disposable, is_exempt


def test_a_listed_provider_is_disposable() -> None:
    assert is_disposable("throwaway@mailinator.com") is True


def test_an_ordinary_provider_is_not_disposable() -> None:
    assert is_disposable("someone@gmail.com") is False


def test_the_check_is_case_insensitive() -> None:
    assert is_disposable("Throwaway@MAILINATOR.com") is True


def test_privacy_relays_are_never_disposable() -> None:
    """These are permanent addresses belonging to privacy-conscious users.
    Blocking them would harm exactly the people who care most."""
    assert is_disposable("abc123@privaterelay.appleid.com") is False
    assert is_disposable("someone@duck.com") is False
    assert is_disposable("someone@simplelogin.com") is False
    assert is_disposable("someone@mozmail.com") is False


def test_the_operator_can_extend_the_list(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "disposable_domains_extra", "burner.test, x.test")

    assert is_disposable("a@burner.test") is True
    assert is_disposable("a@x.test") is True


def test_the_switch_disables_the_whole_check(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "disposable_email_block_enabled", False)

    assert is_disposable("throwaway@mailinator.com") is False


def test_an_admin_address_is_exempt(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "grant_admin_emails", "owner@gmail.com")

    assert is_exempt("owner@gmail.com") is True


def test_an_admin_sub_address_is_exempt_too(monkeypatch) -> None:  # noqa: ANN001
    """Both sides are compared canonically, which is what lets the operator
    open unlimited `+loadtest` accounts from one listed address."""
    monkeypatch.setattr(settings, "grant_admin_emails", "owner@gmail.com")

    assert is_exempt("owner+loadtest@gmail.com") is True
    assert is_exempt("o.w.n.e.r@gmail.com") is True


def test_a_non_admin_address_is_not_exempt(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "grant_admin_emails", "owner@gmail.com")

    assert is_exempt("someone@gmail.com") is False


def test_no_configured_admins_means_nobody_is_exempt(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "grant_admin_emails", "")

    assert is_exempt("owner@gmail.com") is False


def test_an_exempt_address_stores_no_canonical(monkeypatch) -> None:  # noqa: ANN001
    """NULL is how the exemption reaches the unique index: Postgres does not
    conflict on NULL, so the operator can hold many accounts on one mailbox."""
    monkeypatch.setattr(settings, "grant_admin_emails", "owner@gmail.com")

    assert canonical_for_storage("owner+one@gmail.com") is None


def test_an_ordinary_address_stores_its_canonical(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "grant_admin_emails", "")

    assert canonical_for_storage("You+tag@Gmail.com") == "you@gmail.com"


def test_relays_and_the_disposable_blocklist_never_overlap() -> None:
    """If this ever fails, a domain both allowlisted as a privacy relay and
    blocklisted as disposable would be blocked -- `is_disposable` checks the
    relay set first, but only a passing test keeps a future edit to either set
    from creating a domain that is both."""
    assert DISPOSABLE_EMAIL_DOMAINS.isdisjoint(EMAIL_RELAY_DOMAINS)


def test_relays_and_canonical_providers_never_overlap() -> None:
    """`canonicalize` reads only `EMAIL_CANONICAL_PROVIDERS` and never
    consults `EMAIL_RELAY_DOMAINS`. If a domain were ever added to both sets,
    its sub-addresses would silently start being merged into one account,
    collapsing distinct privacy-relay mailboxes into a single canonical form
    with no warning. This test is the only enforcement of the disjointness
    that prevents that silent failure."""
    assert EMAIL_RELAY_DOMAINS.isdisjoint(EMAIL_CANONICAL_PROVIDERS)
