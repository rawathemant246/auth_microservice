"""Schemas for admin panel endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from auth_microservice.db.models.oltp import InvoiceStatusEnum, UserStatusEnum


class OrganizationCounts(BaseModel):
    users_total: int
    users_active: int
    roles_total: int
    permissions_total: int


class InvoiceSummary(BaseModel):
    invoice_id: int
    amount: float
    status: InvoiceStatusEnum
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None


class ActiveUserBucket(BaseModel):
    date: str
    logins: int


class OrganizationOverviewResponse(BaseModel):
    organization_id: int
    counts: OrganizationCounts
    latest_invoices: List[InvoiceSummary]
    active_user_activity: List[ActiveUserBucket]


class PermissionSnapshot(BaseModel):
    permission_id: int
    permission_name: str
    permission_description: Optional[str] = None


class RoleUserSnapshot(BaseModel):
    user_id: int
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    status: UserStatusEnum


class RoleSnapshot(BaseModel):
    role_id: int
    role_name: str
    role_description: Optional[str] = None
    permissions: List[PermissionSnapshot]
    users: List[RoleUserSnapshot]


class RbacSnapshotResponse(BaseModel):
    organization_id: int
    roles: List[RoleSnapshot]


class BootstrapSeedResponse(BaseModel):
    organizations_seeded: int

    model_config = ConfigDict(from_attributes=True)
