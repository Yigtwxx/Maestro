"""The admin guard: non-admins are refused, admins pass.

Uses the PG-only ``GET /admin/users`` endpoint so the guard is exercised without
needing MongoDB.
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.constants import UserRole
from app.models.user import User

_PASSWORD = "supersecret"


async def _register_and_login(client, email: str) -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "T"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _promote(db, email: str) -> None:  # noqa: ANN001 - AsyncSession
    user = await db.scalar(select(User).where(User.email == email))
    user.role = UserRole.ADMIN.value
    await db.commit()


async def test_admin_routes_require_authentication(client) -> None:
    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code in (401, 403), resp.text


async def test_non_admin_is_forbidden(client) -> None:
    headers = await _register_and_login(client, "plain@test.com")
    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 403, "A non-admin must be refused the admin surface"


async def test_admin_is_allowed(client, db_session) -> None:
    email = "boss@test.com"
    headers = await _register_and_login(client, email)
    await _promote(db_session, email)

    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 200, resp.text
    emails = [row["email"] for row in resp.json()]
    assert email in emails, "The admin listing should include the promoted account"


async def test_promotion_takes_effect_on_the_next_request(client, db_session) -> None:
    """Role is read fresh per request, not from the (still-valid) access token."""
    email = "fresh@test.com"
    headers = await _register_and_login(client, email)

    before = await client.get("/api/v1/admin/users", headers=headers)
    assert before.status_code == 403, "Not an admin yet"

    await _promote(db_session, email)

    after = await client.get("/api/v1/admin/users", headers=headers)
    assert after.status_code == 200, "Same token, now admin — no re-login needed"
