"""Admin privileges: unmetered quota, email-gate bypass, and suspension lockout.

These cover the authorization side effects of the ``admin`` role and the new
``suspended_at`` lockout, without needing MongoDB.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core import deps
from app.core.constants import UserRole
from app.core.security import hash_password
from app.models.user import User
from app.services import quota_service

_PASSWORD = "supersecret"


async def _make_user(
    db,  # noqa: ANN001 - AsyncSession
    *,
    email: str,
    role: str = UserRole.USER.value,
    verified: bool = True,
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(_PASSWORD),
        role=role,
        email_verified=verified,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def test_admin_bypasses_quota_without_a_subscription(db_session) -> None:
    admin = await _make_user(
        db_session, email="admin@test.com", role=UserRole.ADMIN.value
    )
    # No subscription at all, yet enforcement must not raise for an admin.
    await quota_service.enforce_can_start_task(db_session, admin)


async def test_non_admin_without_subscription_is_blocked(db_session) -> None:
    user = await _make_user(db_session, email="user@test.com")
    with pytest.raises(HTTPException) as exc:
        await quota_service.enforce_can_start_task(db_session, user)
    assert exc.value.status_code == 402, "No subscription must yield HTTP 402"


async def test_admin_task_budget_is_the_default(db_session) -> None:
    admin = await _make_user(
        db_session, email="admin2@test.com", role=UserRole.ADMIN.value
    )
    budget = await quota_service.resolve_task_token_budget(admin.id)
    from app.core.constants import TASK_TOKEN_BUDGET_DEFAULT

    assert budget == TASK_TOKEN_BUDGET_DEFAULT, "Admins are never quota-throttled"


async def test_admin_bypasses_email_verification_gate(db_session, email_gate) -> None:
    admin = await _make_user(
        db_session,
        email="admin3@test.com",
        role=UserRole.ADMIN.value,
        verified=False,
    )
    assert await deps.get_verified_user(admin) is admin


async def test_unverified_non_admin_is_gated(db_session, email_gate) -> None:
    user = await _make_user(db_session, email="user2@test.com", verified=False)
    with pytest.raises(HTTPException) as exc:
        await deps.get_verified_user(user)
    assert exc.value.status_code == 403, "Unverified non-admins are gated"


async def test_suspended_user_is_locked_out_of_product(client, db_session) -> None:
    email = "victim@test.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "V"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    user = await db_session.scalar(select(User).where(User.email == email))
    user.suspended_at = datetime.now(UTC)
    await db_session.commit()

    # The ActiveUser dependency raises before the handler runs, so this 403 does
    # not depend on the endpoint's own backing services.
    blocked = await client.get("/api/v1/agents", headers=headers)
    assert blocked.status_code == 403, "A suspended account must be locked out"
    # Login still works (so the user can see the suspension), the surface does not.
    relog = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert relog.status_code == 200, "Suspended users keep working credentials"
