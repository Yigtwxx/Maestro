"""Per-recipient outbound mail budget: the axis no per-caller limit covers.

`rate_limit` keys by caller. Every endpoint exercised here lets the caller
choose the *recipient*, so the caller's bucket says nothing about how much mail
one inbox is receiving -- which is the quantity a bombing run maximises.
"""

from __future__ import annotations

from app.core.constants import MAIL_SEND_BUDGET

_PASSWORD = "supersecret"
_VICTIM = "victim@user.com"
_ATTACKER = "attacker@user.com"
_BUDGET = MAIL_SEND_BUDGET.max_requests


async def _register(client, email: str, password: str = _PASSWORD):  # noqa: ANN001, ANN201
    return await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "V"},
    )


async def _login(client, email: str, password: str = _PASSWORD):  # noqa: ANN001, ANN201
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


async def _forgot(client, email: str):  # noqa: ANN001, ANN201
    return await client.post("/api/v1/auth/forgot-password", json={"email": email})


async def _request_email_change(client, headers: dict, target: str):  # noqa: ANN001, ANN201
    return await client.post(
        "/api/v1/users/me/email",
        json={"new_email": target, "current_password": _PASSWORD},
        headers=headers,
    )


def _to(messages: list, address: str) -> int:
    """How many captured messages were addressed to `address`."""
    return sum(1 for message in messages if message.to == address)


async def test_repeated_registration_stops_mailing_the_victim(
    client,  # noqa: ANN001
    rate_limited,  # noqa: ANN001
    sent_emails,  # noqa: ANN001
) -> None:
    """The flood stops; the response never changes.

    The first attempt creates the account and mails a verification link; every
    later one finds the address taken and mails the real owner a
    "someone tried to register your address" notice. Both spend the budget,
    because both land in the same inbox.
    """
    for attempt in range(_BUDGET):
        resp = await _register(client, _VICTIM)
        assert resp.status_code == 202, f"attempt {attempt}: {resp.text}"
    assert _to(sent_emails, _VICTIM) == _BUDGET

    resp = await _register(client, _VICTIM)

    assert resp.status_code == 202, "the body must not reveal the suppression"
    assert _to(sent_emails, _VICTIM) == _BUDGET, "no further mail reaches the victim"


async def test_register_and_forgot_password_share_one_bucket(
    client,  # noqa: ANN001
    rate_limited,  # noqa: ANN001
    sent_emails,  # noqa: ANN001
) -> None:
    """Per-endpoint buckets would multiply the budget by the endpoint count."""
    for _ in range(_BUDGET):
        assert (await _register(client, _VICTIM)).status_code == 202
    baseline = _to(sent_emails, _VICTIM)

    resp = await _forgot(client, _VICTIM)

    assert resp.status_code == 202
    assert _to(sent_emails, _VICTIM) == baseline


async def test_email_change_charges_the_target_not_the_caller(
    client,  # noqa: ANN001
    rate_limited,  # noqa: ANN001
    sent_emails,  # noqa: ANN001
) -> None:
    """One account must not be a mail cannon aimed at any address.

    This endpoint takes an *arbitrary* `new_email` behind a session, so a
    caller-keyed limit measures the wrong thing entirely: the attacker's own
    bucket is irrelevant to how much mail the victim is taking.
    """
    await _register(client, _ATTACKER)
    token = (await _login(client, _ATTACKER)).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    for attempt in range(_BUDGET):
        resp = await _request_email_change(client, headers, _VICTIM)
        assert resp.status_code == 202, f"attempt {attempt}: {resp.text}"
    assert _to(sent_emails, _VICTIM) == _BUDGET

    resp = await _request_email_change(client, headers, _VICTIM)

    assert resp.status_code == 202
    assert _to(sent_emails, _VICTIM) == _BUDGET, (
        "the victim's inbox is the budgeted one"
    )


async def test_sub_addresses_share_one_mail_budget(
    client,  # noqa: ANN001
    rate_limited,  # noqa: ANN001
    sent_emails,  # noqa: ANN001
) -> None:
    """The budget keys on the mailbox, not the typed string.

    `victim@gmail.com` and `victim+other@gmail.com` are one inbox; keying on
    the raw recipient would let each variant open its own bucket while every
    message still landed in the same place, multiplying the budget by however
    many variants the caller bothers to type.
    """
    await _register(client, _ATTACKER)
    token = (await _login(client, _ATTACKER)).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    variants = ["victim@gmail.com", "victim+other@gmail.com"]

    for attempt in range(_BUDGET):
        target = variants[attempt % 2]
        resp = await _request_email_change(client, headers, target)
        assert resp.status_code == 202, f"attempt {attempt}: {resp.text}"
    total = _to(sent_emails, variants[0]) + _to(sent_emails, variants[1])
    assert total == _BUDGET

    resp = await _request_email_change(client, headers, variants[0])

    assert resp.status_code == 202
    total_after = _to(sent_emails, variants[0]) + _to(sent_emails, variants[1])
    assert total_after == _BUDGET, "no further mail reaches either variant"


async def test_distinct_mailboxes_get_separate_budgets(
    client,  # noqa: ANN001
    rate_limited,  # noqa: ANN001
    sent_emails,  # noqa: ANN001
) -> None:
    """Two addresses that are not the same mailbox must not share a bucket."""
    await _register(client, _ATTACKER)
    token = (await _login(client, _ATTACKER)).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(_BUDGET):
        resp = await _request_email_change(client, headers, "one@gmail.com")
        assert resp.status_code == 202
    assert _to(sent_emails, "one@gmail.com") == _BUDGET

    resp = await _request_email_change(client, headers, "two@gmail.com")

    assert resp.status_code == 202
    assert _to(sent_emails, "two@gmail.com") == 1, (
        "a different mailbox has its own budget"
    )


async def test_budget_exhaustion_still_creates_the_account(
    client,  # noqa: ANN001
    rate_limited,  # noqa: ANN001
    sent_emails,  # noqa: ANN001
) -> None:
    """Refusing the whole request would be a better weapon than the one removed.

    An attacker keeping one address's bucket full could otherwise deny that
    address registration indefinitely. Only the mail is suppressed; the account
    exists, and `resend-verification` is the way back once the window clears.

    Reaching this state needs an endpoint that mails an address holding no
    account -- which is exactly what POST /users/me/email is, and why it is the
    sharpest of the four.
    """
    await _register(client, _ATTACKER)
    token = (await _login(client, _ATTACKER)).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(_BUDGET):
        await _request_email_change(client, headers, _VICTIM)
    baseline = _to(sent_emails, _VICTIM)

    assert (await _register(client, _VICTIM)).status_code == 202

    assert _to(sent_emails, _VICTIM) == baseline, "the verification mail is suppressed"
    login = await _login(client, _VICTIM)
    assert login.status_code == 200, "the account was created despite the block"


async def test_disabled_rate_limiting_disables_the_budget(
    client,  # noqa: ANN001
    sent_emails,  # noqa: ANN001
) -> None:
    """No `rate_limited` fixture, so RATE_LIMIT_ENABLED is false.

    Every throttle here obeys that switch, or the suite's own repeated
    registrations would start failing for reasons no test asked about.
    """
    sends = _BUDGET + 2
    for _ in range(sends):
        assert (await _register(client, _VICTIM)).status_code == 202

    assert _to(sent_emails, _VICTIM) == sends
