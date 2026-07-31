"""Email identity hygiene at the registration boundary."""

from __future__ import annotations

import dns.resolver
from sqlalchemy import func, select

from app.core.config import settings
from app.core.metrics import metrics
from app.models.user import User
from app.utils import mx_check

_REGISTER = "/api/v1/auth/register"
_PASSWORD = "supersecret"
_ACCEPTED = "Check your email — we've sent you the next step."


async def _register(client, email: str):  # noqa: ANN001, ANN202
    return await client.post(_REGISTER, json={"email": email, "password": _PASSWORD})


async def _user_count(db_session) -> int:  # noqa: ANN001
    return await db_session.scalar(select(func.count()).select_from(User))


async def test_a_disposable_domain_is_refused_visibly(client, db_session) -> None:  # noqa: ANN001
    """Safe to answer visibly: the decision reads only the submitted domain and
    says nothing about whether any account exists."""
    resp = await _register(client, "throwaway@mailinator.com")

    assert resp.status_code == 400, resp.text
    assert await _user_count(db_session) == 0


async def test_a_disposable_rejection_is_counted(client) -> None:  # noqa: ANN001
    before = metrics.snapshot_abuse_rejections().get("disposable_domain", 0)

    await _register(client, "throwaway@guerrillamail.com")

    after = metrics.snapshot_abuse_rejections().get("disposable_domain", 0)
    assert after == before + 1


async def test_an_undeliverable_domain_is_refused(  # noqa: ANN001
    client, db_session, mx_check_on, monkeypatch
) -> None:
    async def _no_records(domain: str, record_type: str, **kwargs: object):  # noqa: ANN202
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr(mx_check, "_resolve", _no_records)

    # Not `gmial.invalid`: the `.invalid` TLD is an RFC 2606 special-use name
    # that `email-validator` (2.3+) now rejects with a 422 at the Pydantic layer,
    # before the request ever reaches `enforce`. This domain is syntactically
    # ordinary and exercises the same NXDOMAIN path via the monkeypatched
    # `_resolve` above.
    resp = await _register(client, "someone@totally-fake-domain-xyz123.com")

    assert resp.status_code == 400, resp.text
    assert await _user_count(db_session) == 0


async def test_a_sub_address_of_an_existing_account_is_silently_refused(  # noqa: ANN001
    client, db_session, sent_emails
) -> None:
    """The canonical collision takes the path a duplicate address already
    takes: the same fixed body, no account, and a notice to the real owner."""
    assert (await _register(client, "you@gmail.com")).status_code == 202
    sent_emails.clear()

    resp = await _register(client, "y.o.u+maestro@gmail.com")

    assert resp.status_code == 202, resp.text
    assert resp.json()["detail"] == _ACCEPTED
    assert await _user_count(db_session) == 1
    assert [message.to for message in sent_emails] == ["you@gmail.com"]


async def test_a_canonical_collision_is_counted(client) -> None:  # noqa: ANN001
    await _register(client, "someone@gmail.com")
    before = metrics.snapshot_abuse_rejections().get("canonical_duplicate", 0)

    await _register(client, "some.one+x@gmail.com")

    after = metrics.snapshot_abuse_rejections().get("canonical_duplicate", 0)
    assert after == before + 1


async def test_distinct_mailboxes_still_register(client, db_session) -> None:  # noqa: ANN001
    assert (await _register(client, "alice@gmail.com")).status_code == 202
    assert (await _register(client, "bob@gmail.com")).status_code == 202

    assert await _user_count(db_session) == 2


async def test_a_sub_address_on_an_unknown_provider_is_a_distinct_account(  # noqa: ANN001
    client, db_session
) -> None:
    """'+' belongs to the receiving server on a domain we know nothing about."""
    assert (await _register(client, "you@example.com")).status_code == 202
    assert (await _register(client, "you+tag@example.com")).status_code == 202

    assert await _user_count(db_session) == 2


async def test_an_admin_address_skips_the_domain_checks(  # noqa: ANN001
    client, db_session, monkeypatch, mx_check_on
) -> None:
    """The operator keeps unrestricted signup, as they do for quota,
    concurrency and storage. `mailinator.com` is on the disposable list, and
    the resolver is rigged to fail the test if it is consulted at all."""
    monkeypatch.setattr(settings, "grant_admin_emails", "owner@mailinator.com")

    def _explode(*args: object, **kwargs: object):  # noqa: ANN202
        raise AssertionError("an exempt address must not be resolved")

    monkeypatch.setattr(mx_check, "_resolve", _explode)

    resp = await _register(client, "owner@mailinator.com")

    assert resp.status_code == 202, resp.text
    assert await _user_count(db_session) == 1


async def test_an_admin_sub_address_bypasses_canonical_uniqueness(  # noqa: ANN001
    client, db_session, monkeypatch
) -> None:
    """Two accounts on one mailbox, which is the point of the exemption: the
    NULL canonical does not conflict with itself. Uses a domain that really
    does sub-address, so plain `canonicalize` matches both against the
    configured admin entry."""
    monkeypatch.setattr(settings, "grant_admin_emails", "owner@gmail.com")

    first = await _register(client, "owner@gmail.com")
    second = await _register(client, "owner+loadtest@gmail.com")

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert await _user_count(db_session) == 2


async def test_an_exempt_account_stores_no_canonical(  # noqa: ANN001
    client, db_session, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "grant_admin_emails", "owner@gmail.com")

    await _register(client, "owner@gmail.com")

    stored = await db_session.scalar(
        select(User.canonical_email).where(User.email == "owner@gmail.com")
    )
    assert stored is None


async def test_an_ordinary_account_stores_its_canonical(client, db_session) -> None:  # noqa: ANN001
    await _register(client, "You+tag@Gmail.com")

    stored = await db_session.scalar(select(User.canonical_email))
    assert stored == "you@gmail.com"
