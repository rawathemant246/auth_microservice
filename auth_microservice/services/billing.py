"""Billing domain services for plans, subscriptions, and invoices."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import (
    BillingCycleEnum,
    BillingPlan,
    Invoice,
    PaymentStatusEnum,
    PlanTypeEnum,
    Subscription,
    SubscriptionHistory,
    SubscriptionHistoryStatusEnum,
    SupportLevelEnum,
)


class BillingService:
    """Encapsulates billing plan, subscription, and invoice operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # Billing plans -----------------------------------------------------------------

    async def list_plans(self) -> list[BillingPlan]:
        stmt = select(BillingPlan).order_by(BillingPlan.plan_id)
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def get_plan(self, plan_id: int) -> BillingPlan | None:
        return await self._session.get(BillingPlan, plan_id)

    async def create_plan(
        self,
        *,
        plan_name: str,
        plan_description: str | None,
        price: Decimal,
        billing_cycle: BillingCycleEnum,
        max_users: int | None,
        max_storage: int | None,
        support_level: SupportLevelEnum | None,
    ) -> BillingPlan:
        existing = await self._session.scalar(
            select(BillingPlan).where(BillingPlan.plan_name == plan_name),
        )
        if existing is not None:
            raise ValueError("plan_name_exists")

        plan = BillingPlan(
            plan_name=plan_name,
            plan_description=plan_description,
            price=price,
            billing_cycle=billing_cycle,
            max_users=max_users,
            max_storage=max_storage,
            support_level=support_level,
        )
        self._session.add(plan)
        await self._session.flush()
        await self._session.refresh(plan)
        return plan

    async def update_plan(
        self,
        plan: BillingPlan,
        updates: dict[str, Any],
    ) -> BillingPlan:
        if "plan_name" in updates and updates["plan_name"] and updates["plan_name"] != plan.plan_name:
            conflict = await self._session.scalar(
                select(BillingPlan).where(BillingPlan.plan_name == updates["plan_name"]),
            )
            if conflict is not None:
                raise ValueError("plan_name_exists")
            plan.plan_name = updates["plan_name"]

        if "plan_description" in updates:
            plan.plan_description = updates["plan_description"]
        if "price" in updates and updates["price"] is not None:
            plan.price = updates["price"]
        if "billing_cycle" in updates and updates["billing_cycle"] is not None:
            plan.billing_cycle = updates["billing_cycle"]
        if "max_users" in updates:
            plan.max_users = updates["max_users"]
        if "max_storage" in updates:
            plan.max_storage = updates["max_storage"]
        if "support_level" in updates:
            plan.support_level = updates["support_level"]

        await self._session.flush()
        await self._session.refresh(plan)
        return plan

    # Subscriptions -----------------------------------------------------------------

    async def get_subscription(self, organization_id: int) -> Subscription | None:
        stmt: Select[Subscription] = select(Subscription).where(
            Subscription.organization_id == organization_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_subscription(
        self,
        *,
        organization_id: int,
        subscription_start: date | None,
        subscription_end: date | None,
        plan_type: PlanTypeEnum,
        payment_status: PaymentStatusEnum,
        plan_id: int,
        history_status: SubscriptionHistoryStatusEnum,
    ) -> Subscription:
        existing = await self.get_subscription(organization_id)
        if existing is not None:
            raise ValueError("subscription_exists")

        subscription = Subscription(
            organization_id=organization_id,
            subscription_start=subscription_start,
            subscription_end=subscription_end,
            plan_type=plan_type,
            payment_status=payment_status,
        )
        self._session.add(subscription)
        await self._session.flush()

        await self._record_subscription_history(
            organization_id=organization_id,
            plan_id=plan_id,
            start_date=subscription_start,
            end_date=subscription_end,
            status=history_status,
        )
        await self._session.refresh(subscription)
        return subscription

    async def update_subscription(
        self,
        subscription: Subscription,
        updates: dict[str, Any],
    ) -> Subscription:
        if "subscription_start" in updates:
            subscription.subscription_start = updates["subscription_start"]
        if "subscription_end" in updates:
            subscription.subscription_end = updates["subscription_end"]
        if "plan_type" in updates and updates["plan_type"] is not None:
            subscription.plan_type = updates["plan_type"]
        if "payment_status" in updates and updates["payment_status"] is not None:
            subscription.payment_status = updates["payment_status"]

        await self._session.flush()

        if "history" in updates:
            history_data = updates["history"]
            await self._record_subscription_history(
                organization_id=subscription.organization_id,
                plan_id=history_data["plan_id"],
                start_date=history_data.get("start_date", subscription.subscription_start),
                end_date=history_data.get("end_date", subscription.subscription_end),
                status=history_data["status"],
            )

        await self._session.refresh(subscription)
        return subscription

    async def _record_subscription_history(
        self,
        *,
        organization_id: int,
        plan_id: int,
        start_date: date | None,
        end_date: date | None,
        status: SubscriptionHistoryStatusEnum,
    ) -> None:
        start_dt: datetime | None = None
        end_dt: datetime | None = None
        if start_date is not None:
            if isinstance(start_date, datetime):
                start_dt = start_date
            else:
                start_dt = datetime.combine(start_date, time.min)
        if end_date is not None:
            if isinstance(end_date, datetime):
                end_dt = end_date
            else:
                end_dt = datetime.combine(end_date, time.min)

        history = SubscriptionHistory(
            school_id=organization_id,
            plan_id=plan_id,
            start_date=start_dt,
            end_date=end_dt,
            status=status,
        )
        self._session.add(history)
        await self._session.flush()

    # Invoices -----------------------------------------------------------------------

    async def list_invoices(self, organization_id: int) -> list[Invoice]:
        stmt = (
            select(Invoice)
            .where(Invoice.school_id == organization_id)
            .order_by(Invoice.invoice_date.desc().nullslast(), Invoice.invoice_id.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def get_invoice(self, invoice_id: int) -> Invoice | None:
        return await self._session.get(Invoice, invoice_id)

    async def update_invoice(
        self,
        invoice: Invoice,
        updates: dict[str, Any],
    ) -> Invoice:
        if "amount" in updates and updates["amount"] is not None:
            invoice.amount = updates["amount"]
        if "status" in updates and updates["status"] is not None:
            invoice.status = updates["status"]
        if "payment_method" in updates and updates["payment_method"] is not None:
            invoice.payment_method = updates["payment_method"]
        if "payment_date" in updates:
            invoice.payment_date = updates["payment_date"]
        if "due_date" in updates:
            invoice.due_date = updates["due_date"]
        if "billing_cycle" in updates and updates["billing_cycle"] is not None:
            invoice.billing_cycle = updates["billing_cycle"]

        await self._session.flush()
        await self._session.refresh(invoice)
        return invoice
