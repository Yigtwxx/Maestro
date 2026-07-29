"""Billing endpoints: plans, subscription, subscribe, cancel, payment method.

The card number reaches ``billing_service.subscribe`` and stops there. It is
never persisted, never logged, and never appears in a response.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.constants import (
    BILLING_CURRENCY,
    PLAN_MONTHLY_TOKEN_QUOTA,
    PLAN_PRICE_USD_CENTS,
    RATE_LIMIT_PAYMENT,
    RATE_LIMIT_PUBLIC,
    RATE_LIMIT_READ,
    SubscriptionPlan,
    UserRole,
)
from app.core.deps import ActiveUser, DbSession
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.billing import (
    PaymentMethodPublic,
    PlanPublic,
    PlanPublicListing,
    SubscribeRequest,
    SubscriptionPublic,
)
from app.services import billing_service, quota_service
from app.services.payment import CardDetails, PaymentError
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/billing", tags=["billing"])

_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="billing")
# Payment mutations are throttled harder than reads.
_payment_rate_limit = rate_limit(RATE_LIMIT_PAYMENT, scope="billing")
# The public pricing page is unauthenticated, so it is throttled harder still.
_public_rate_limit = rate_limit(RATE_LIMIT_PUBLIC, scope="billing")

NO_SUBSCRIPTION_DETAIL = "You do not have a subscription yet."
BILLING_DISABLED_DETAIL = (
    "Paid plans are coming soon. Every account currently runs on the free plan."
)
FREE_PLAN_NOT_CANCELABLE_DETAIL = (
    "The free plan cannot be cancelled — it is what every account runs on."
)


def _require_billing_reachable(user: User) -> None:
    """Refuse a paid-plan mutation unless billing is live or the caller is admin.

    The UI cannot be the only guard: this endpoint is directly callable with a
    bearer token and reaches the payment provider. The admin exemption is what
    lets the operator exercise the real flow before it opens to everyone.

    403, not 402 (which means "pay us" -- the opposite of what is happening) and
    not 5xx (which would page ops for a deliberate product state).
    """
    if settings.billing_enabled or user.role == UserRole.ADMIN.value:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail=BILLING_DISABLED_DETAIL
    )


async def _to_public(
    db: DbSession, user: ActiveUser, subscription: Subscription
) -> SubscriptionPublic:
    """Assemble the subscription view, including live quota consumption."""
    snapshot = await quota_service.get_quota_snapshot(db, user)
    payment_method = await billing_service.get_payment_method(db, user.id)
    return SubscriptionPublic(
        plan=SubscriptionPlan(subscription.plan),
        status=billing_service.resolve_effective_status(subscription),
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        used_tokens=snapshot.used_tokens,
        quota_tokens=snapshot.quota_tokens,
        payment_method=(
            PaymentMethodPublic.model_validate(payment_method)
            if payment_method is not None
            else None
        ),
    )


@router.get("/plans", response_model=list[PlanPublic], dependencies=[_read_rate_limit])
async def list_plans(user: ActiveUser) -> list[PlanPublic]:
    """The free plan plus the three paid plans, at list price."""
    return [
        PlanPublic(
            plan=plan,
            price_cents=PLAN_PRICE_USD_CENTS[plan.value],
            quota_tokens=PLAN_MONTHLY_TOKEN_QUOTA[plan.value],
            currency=BILLING_CURRENCY,
        )
        for plan in SubscriptionPlan
    ]


@router.get(
    "/plans/public",
    response_model=list[PlanPublicListing],
    dependencies=[_public_rate_limit],
)
async def list_plans_public() -> list[PlanPublicListing]:
    """The free plan plus the three paid plans, for anonymous visitors."""
    return [
        PlanPublicListing(
            plan=plan,
            price_cents=PLAN_PRICE_USD_CENTS[plan.value],
            quota_tokens=PLAN_MONTHLY_TOKEN_QUOTA[plan.value],
            currency=BILLING_CURRENCY,
        )
        for plan in SubscriptionPlan
    ]


@router.get(
    "/subscription", response_model=SubscriptionPublic, dependencies=[_read_rate_limit]
)
async def get_subscription(user: ActiveUser, db: DbSession) -> SubscriptionPublic:
    """The current subscription and quota usage."""
    subscription = await billing_service.get_subscription(db, user.id)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NO_SUBSCRIPTION_DETAIL
        )
    # Roll the window forward if the period has elapsed, so the displayed period
    # and quota reflect the current billing cycle rather than a stale one.
    subscription = await billing_service.sync_billing_period(db, subscription)
    return await _to_public(db, user, subscription)


@router.get(
    "/payment-method",
    response_model=PaymentMethodPublic | None,
    dependencies=[_read_rate_limit],
)
async def get_payment_method(
    user: ActiveUser, db: DbSession
) -> PaymentMethodPublic | None:
    """The stored card's brand, last four digits and expiry — nothing more."""
    payment_method = await billing_service.get_payment_method(db, user.id)
    if payment_method is None:
        return None
    return PaymentMethodPublic.model_validate(payment_method)


@router.post(
    "/subscribe", response_model=SubscriptionPublic, dependencies=[_payment_rate_limit]
)
async def subscribe(
    payload: SubscribeRequest, user: ActiveUser, db: DbSession
) -> SubscriptionPublic:
    """Charge the first period and activate the plan."""
    # Before CardDetails is built, so no PAN is handled for a refused call.
    _require_billing_reachable(user)
    card = CardDetails(
        number=payload.card.number,
        exp_month=payload.card.exp_month,
        exp_year=payload.card.exp_year,
        cvc=payload.card.cvc,
        holder=payload.card.holder,
    )
    try:
        subscription = await billing_service.subscribe(
            db, user, plan=payload.plan, card=card
        )
    except PaymentError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)
        ) from exc
    return await _to_public(db, user, subscription)


@router.post(
    "/cancel", response_model=SubscriptionPublic, dependencies=[_payment_rate_limit]
)
async def cancel(user: ActiveUser, db: DbSession) -> SubscriptionPublic:
    """Stop renewal; the plan stays usable until the period ends."""
    _require_billing_reachable(user)
    # Unconditional, and deliberately not tied to the flag: cancelling sets
    # status=canceled, which fails is_active, which makes enforce_can_start_task
    # raise 402. A user could permanently lock themselves out of the product
    # with a button that looks harmless, with no way back short of a DB edit.
    existing = await billing_service.get_subscription(db, user.id)
    if existing is not None and existing.plan == SubscriptionPlan.FREE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=FREE_PLAN_NOT_CANCELABLE_DETAIL,
        )
    subscription = await billing_service.cancel(db, user)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NO_SUBSCRIPTION_DETAIL
        )
    return await _to_public(db, user, subscription)
