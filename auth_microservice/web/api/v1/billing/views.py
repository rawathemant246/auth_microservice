"""Billing endpoints for plans, subscriptions, and invoices."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import Invoice, Subscription
from auth_microservice.services.billing import BillingService
from auth_microservice.web.api.dependencies import (
    AuthenticatedPrincipal,
    require_permission,
)
from auth_microservice.web.api.v1.billing.schemas import (
    BillingPlanCreateRequest,
    BillingPlanResponse,
    BillingPlansListResponse,
    BillingPlanUpdateRequest,
    InvoiceResponse,
    InvoicesListResponse,
    InvoiceUpdateRequest,
    SubscriptionCreateRequest,
    SubscriptionResponse,
    SubscriptionUpdateRequest,
)

plans_router = APIRouter(prefix="/v1/billing", tags=["billing"])
org_router = APIRouter(prefix="/v1", tags=["billing"])


@plans_router.get("/plans", response_model=BillingPlansListResponse)
async def list_billing_plans(
    _: AuthenticatedPrincipal = Depends(require_permission("billing.plan.read")),
    session: AsyncSession = Depends(get_db_session),
) -> BillingPlansListResponse:
    service = BillingService(session)
    plans = await service.list_plans()
    return BillingPlansListResponse(items=[BillingPlanResponse.model_validate(plan) for plan in plans])


@plans_router.post("/plans", response_model=BillingPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_billing_plan(
    payload: BillingPlanCreateRequest,
    _: AuthenticatedPrincipal = Depends(require_permission("billing.plan.write")),
    session: AsyncSession = Depends(get_db_session),
) -> BillingPlanResponse:
    service = BillingService(session)
    try:
        plan = await service.create_plan(
            plan_name=payload.plan_name,
            plan_description=payload.plan_description,
            price=payload.price,
            billing_cycle=payload.billing_cycle,
            max_users=payload.max_users,
            max_storage=payload.max_storage,
            support_level=payload.support_level,
        )
    except ValueError as exc:
        if str(exc) == "plan_name_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="plan_name_exists") from exc
        raise
    return BillingPlanResponse.model_validate(plan)


@plans_router.patch("/plans/{plan_id}", response_model=BillingPlanResponse)
async def update_billing_plan(
    plan_id: int,
    payload: BillingPlanUpdateRequest,
    _: AuthenticatedPrincipal = Depends(require_permission("billing.plan.write")),
    session: AsyncSession = Depends(get_db_session),
) -> BillingPlanResponse:
    service = BillingService(session)
    plan = await service.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan_not_found")

    updates = payload.model_dump(exclude_unset=True)
    try:
        plan = await service.update_plan(plan, updates)
    except ValueError as exc:
        if str(exc) == "plan_name_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="plan_name_exists") from exc
        raise

    return BillingPlanResponse.model_validate(plan)


def _ensure_same_org(principal: AuthenticatedPrincipal, organization_id: int) -> None:
    if principal.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _serialize_subscription(subscription: Subscription) -> SubscriptionResponse:
    return SubscriptionResponse.model_validate(subscription)


@org_router.get("/orgs/{organization_id}/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    organization_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission("billing.subscription.read")),
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionResponse:
    _ensure_same_org(principal, organization_id)
    service = BillingService(session)
    subscription = await service.get_subscription(organization_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subscription_not_found")
    return _serialize_subscription(subscription)


@org_router.post(
    "/orgs/{organization_id}/subscription",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    organization_id: int,
    payload: SubscriptionCreateRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission("billing.subscription.write")),
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionResponse:
    _ensure_same_org(principal, organization_id)
    service = BillingService(session)

    plan = await service.get_plan(payload.plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan_not_found")

    try:
        subscription = await service.create_subscription(
            organization_id=organization_id,
            subscription_start=payload.subscription_start,
            subscription_end=payload.subscription_end,
            plan_type=payload.plan_type,
            payment_status=payload.payment_status,
            plan_id=payload.plan_id,
            history_status=payload.history_status,
        )
    except ValueError as exc:
        if str(exc) == "subscription_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="subscription_exists") from exc
        raise

    return _serialize_subscription(subscription)


@org_router.patch("/orgs/{organization_id}/subscription", response_model=SubscriptionResponse)
async def update_subscription(
    organization_id: int,
    payload: SubscriptionUpdateRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission("billing.subscription.write")),
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionResponse:
    _ensure_same_org(principal, organization_id)
    service = BillingService(session)

    subscription = await service.get_subscription(organization_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subscription_not_found")

    updates = payload.model_dump(exclude_unset=True)
    history_payload: dict[str, Any] | None = None

    plan_id = updates.pop("plan_id", None)
    if plan_id is not None:
        plan = await service.get_plan(plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan_not_found")

    if "history_status" in updates:
        history_status = updates.pop("history_status")
        if history_status is not None:
            if plan_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="plan_id_required_for_history",
                )
            history_payload = {
                "plan_id": plan_id,
                "status": history_status,
                "start_date": updates.get("subscription_start", subscription.subscription_start),
                "end_date": updates.get("subscription_end", subscription.subscription_end),
            }

    if plan_id is not None and "plan_type" not in updates:
        updates["plan_type"] = subscription.plan_type

    if history_payload is not None:
        updates["history"] = history_payload

    subscription = await service.update_subscription(subscription, updates)
    return _serialize_subscription(subscription)


def _serialize_invoice(invoice: Invoice) -> InvoiceResponse:
    return InvoiceResponse.model_validate(invoice)


@org_router.get("/orgs/{organization_id}/invoices", response_model=InvoicesListResponse)
async def list_invoices(
    organization_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission("billing.invoice.read")),
    session: AsyncSession = Depends(get_db_session),
) -> InvoicesListResponse:
    _ensure_same_org(principal, organization_id)
    service = BillingService(session)
    invoices = await service.list_invoices(organization_id)
    return InvoicesListResponse(items=[_serialize_invoice(invoice) for invoice in invoices])


@org_router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission("billing.invoice.read")),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceResponse:
    invoice = await BillingService(session).get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invoice_not_found")
    if principal.organization_id != invoice.school_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return _serialize_invoice(invoice)


@org_router.patch("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: int,
    payload: InvoiceUpdateRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission("billing.invoice.write")),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceResponse:
    service = BillingService(session)
    invoice = await service.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invoice_not_found")
    if invoice.school_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    updates = payload.model_dump(exclude_unset=True)
    invoice = await service.update_invoice(invoice, updates)
    return _serialize_invoice(invoice)


__all__ = ["plans_router", "org_router"]
