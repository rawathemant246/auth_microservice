"""Administrative services aggregating organization data."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import (
    Invoice,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserLoginActivity,
    UserStatusEnum,
)
from auth_microservice.services.organizations import OrganizationService


class AdminService:
    """High-level helpers for admin panel functionality."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_organization(self, organization_id: int) -> Organization:
        organization = await self._session.get(Organization, organization_id)
        if organization is None:
            raise ValueError("organization_not_found")
        return organization

    async def get_org_overview(self, organization_id: int) -> dict[str, Any]:
        await self.ensure_organization(organization_id)

        counts = await self._collect_counts(organization_id)
        invoices = await self._collect_latest_invoices(organization_id)
        activity = await self._collect_active_user_activity(organization_id)

        return {
            "organization_id": organization_id,
            "counts": counts,
            "latest_invoices": invoices,
            "active_user_activity": activity,
        }

    async def _collect_counts(self, organization_id: int) -> dict[str, int]:
        total_users_stmt = select(func.count()).select_from(User).where(User.organization_id == organization_id)
        active_users_stmt = (
            select(func.count())
            .select_from(User)
            .where(User.organization_id == organization_id, User.status == UserStatusEnum.ACTIVE)
        )
        total_roles_stmt = select(func.count()).select_from(Role).where(Role.organization_id == organization_id)
        total_permissions_stmt = (
            select(func.count(func.distinct(RolePermission.permission_id)))
            .where(RolePermission.organization_id == organization_id)
        )

        total_users = await self._session.scalar(total_users_stmt) or 0
        active_users = await self._session.scalar(active_users_stmt) or 0
        total_roles = await self._session.scalar(total_roles_stmt) or 0
        total_permissions = await self._session.scalar(total_permissions_stmt) or 0

        return {
            "users_total": total_users,
            "users_active": active_users,
            "roles_total": total_roles,
            "permissions_total": total_permissions,
        }

    async def _collect_latest_invoices(self, organization_id: int) -> list[dict[str, Any]]:
        stmt: Select[Invoice] = (
            select(Invoice)
            .where(Invoice.school_id == organization_id)
            .order_by(Invoice.invoice_date.desc().nullslast(), Invoice.invoice_id.desc())
            .limit(5)
        )
        result = await self._session.execute(stmt)
        invoices = []
        for invoice in result.scalars():
            amount = float(invoice.amount) if isinstance(invoice.amount, Decimal) else invoice.amount
            invoices.append(
                {
                    "invoice_id": invoice.invoice_id,
                    "amount": amount,
                    "status": invoice.status,
                    "invoice_date": invoice.invoice_date,
                    "due_date": invoice.due_date,
                },
            )
        return invoices

    async def _collect_active_user_activity(self, organization_id: int) -> list[dict[str, Any]]:
        bucket = func.date(UserLoginActivity.login_timestamp)
        stmt = (
            select(bucket.label("bucket"), func.count())
            .join(User, UserLoginActivity.user_id == User.user_id)
            .where(User.organization_id == organization_id)
            .group_by(bucket)
            .order_by(bucket.desc())
            .limit(30)
        )
        result = await self._session.execute(stmt)
        activity: list[dict[str, Any]] = []
        for bucket_date, count in result.all():
            cast_date: date | None = bucket_date
            activity.append(
                {
                    "date": cast_date.isoformat() if isinstance(cast_date, date) else str(cast_date),
                    "logins": count,
                },
            )
        activity.reverse()
        return activity

    async def get_rbac_snapshot(self, organization_id: int) -> dict[str, Any]:
        await self.ensure_organization(organization_id)

        roles_result = await self._session.execute(
            select(Role).where(Role.organization_id == organization_id).order_by(Role.role_name),
        )
        roles = roles_result.scalars().all()

        perm_rows = await self._session.execute(
            select(RolePermission.role_id, Permission)
            .join(Permission, Permission.permission_id == RolePermission.permission_id)
            .where(RolePermission.organization_id == organization_id),
        )
        permissions_map: dict[int, list[Permission]] = defaultdict(list)
        for role_id, permission in perm_rows.all():
            permissions_map[role_id].append(permission)

        user_rows = await self._session.execute(
            select(User).where(User.organization_id == organization_id),
        )
        users_by_role: dict[int | None, list[User]] = defaultdict(list)
        for user in user_rows.scalars():
            users_by_role[user.role_id].append(user)

        snapshot_roles: list[dict[str, Any]] = []
        for role in roles:
            role_permissions = permissions_map.get(role.role_id, [])
            role_users = users_by_role.get(role.role_id, [])
            snapshot_roles.append(
                {
                    "role_id": role.role_id,
                    "role_name": role.role_name,
                    "role_description": role.role_description,
                    "permissions": [
                        {
                            "permission_id": permission.permission_id,
                            "permission_name": permission.permission_name,
                            "permission_description": permission.permission_description,
                        }
                        for permission in sorted(role_permissions, key=lambda p: p.permission_name)
                    ],
                    "users": [
                        {
                            "user_id": user.user_id,
                            "username": user.username,
                            "first_name": user.first_name,
                            "last_name": user.last_name,
                            "status": user.status,
                        }
                        for user in sorted(role_users, key=lambda u: u.username)
                    ],
                },
            )

        return {
            "organization_id": organization_id,
            "roles": snapshot_roles,
        }

    async def reseed_defaults(self) -> int:
        stmt = select(Organization)
        result = await self._session.execute(stmt)
        organizations = result.scalars().all()
        org_service = OrganizationService(self._session)
        processed = 0
        for organization in organizations:
            await org_service.ensure_admin_role(organization)
            processed += 1
        return processed
