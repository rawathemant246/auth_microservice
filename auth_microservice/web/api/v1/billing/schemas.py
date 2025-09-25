"""Schemas for billing APIs."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from auth_microservice.db.models.oltp import (
    BillingCycleEnum,
    InvoiceStatusEnum,
    PaymentMethodEnum,
    PaymentStatusEnum,
    PlanTypeEnum,
    SubscriptionHistoryStatusEnum,
    SupportLevelEnum,
)


class BillingPlanCreateRequest(BaseModel):
    plan_name: str = Field(..., min_length=1, max_length=100)
    plan_description: Optional[str] = None
    price: Decimal
    billing_cycle: BillingCycleEnum
    max_users: Optional[int] = None
    max_storage: Optional[int] = None
    support_level: Optional[SupportLevelEnum] = None


class BillingPlanUpdateRequest(BaseModel):
    plan_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    plan_description: Optional[str] = None
    price: Optional[Decimal] = None
    billing_cycle: Optional[BillingCycleEnum] = None
    max_users: Optional[int] = None
    max_storage: Optional[int] = None
    support_level: Optional[SupportLevelEnum] = None


class BillingPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: int
    plan_name: str
    plan_description: Optional[str]
    price: Decimal
    billing_cycle: BillingCycleEnum
    max_users: Optional[int]
    max_storage: Optional[int]
    support_level: Optional[SupportLevelEnum]
    created_at: datetime
    updated_at: datetime


class BillingPlansListResponse(BaseModel):
    items: list[BillingPlanResponse]


class SubscriptionCreateRequest(BaseModel):
    plan_id: int
    plan_type: PlanTypeEnum
    payment_status: PaymentStatusEnum
    subscription_start: Optional[date] = None
    subscription_end: Optional[date] = None
    history_status: SubscriptionHistoryStatusEnum = SubscriptionHistoryStatusEnum.ACTIVE


class SubscriptionUpdateRequest(BaseModel):
    plan_id: Optional[int] = None
    plan_type: Optional[PlanTypeEnum] = None
    payment_status: Optional[PaymentStatusEnum] = None
    subscription_start: Optional[date] = None
    subscription_end: Optional[date] = None
    history_status: Optional[SubscriptionHistoryStatusEnum] = None


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subscription_id: int
    organization_id: int
    subscription_start: Optional[date]
    subscription_end: Optional[date]
    plan_type: PlanTypeEnum
    payment_status: PaymentStatusEnum


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: int
    school_id: int
    plan_id: int
    amount: Decimal
    billing_cycle: BillingCycleEnum
    invoice_date: Optional[datetime]
    due_date: Optional[datetime]
    status: InvoiceStatusEnum
    payment_method: Optional[PaymentMethodEnum]
    payment_date: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class InvoicesListResponse(BaseModel):
    items: list[InvoiceResponse]


class InvoiceUpdateRequest(BaseModel):
    amount: Optional[Decimal] = None
    billing_cycle: Optional[BillingCycleEnum] = None
    due_date: Optional[datetime] = None
    status: Optional[InvoiceStatusEnum] = None
    payment_method: Optional[PaymentMethodEnum] = None
    payment_date: Optional[datetime] = None

