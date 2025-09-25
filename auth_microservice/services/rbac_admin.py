"""Administrative helpers for managing RBAC entities."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import (
    Permission,
    Role,
    RolePermission,
    User,
)


class RbacAdminService:
    """Encapsulates CRUD operations for roles, permissions, and assignments."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_roles(self, organization_id: int) -> list[tuple[Role, list[int]]]:
        roles_result = await self._session.execute(
            select(Role).where(Role.organization_id == organization_id).order_by(Role.role_id)
        )
        roles = list(roles_result.scalars())
        if not roles:
            return []

        role_ids = [role.role_id for role in roles]
        rp_result = await self._session.execute(
            select(RolePermission.role_id, RolePermission.permission_id)
            .where(RolePermission.role_id.in_(role_ids))
            .order_by(RolePermission.permission_id)
        )
        permissions_map: dict[int, list[int]] = defaultdict(list)
        for role_id, permission_id in rp_result:
            permissions_map[role_id].append(permission_id)

        return [(role, permissions_map.get(role.role_id, [])) for role in roles]

    async def create_role(
        self,
        organization_id: int,
        *,
        role_name: str,
        role_description: str | None = None,
    ) -> Role:
        existing = await self._session.scalar(select(Role).where(Role.role_name == role_name))
        if existing is not None:
            raise ValueError("role_name_exists")

        role = Role(
            organization_id=organization_id,
            role_name=role_name,
            role_description=role_description,
        )
        self._session.add(role)
        await self._session.flush()
        await self._session.refresh(role)
        return role

    async def update_role(
        self,
        role: Role,
        *,
        role_name: str | None = None,
        role_description: str | None = None,
    ) -> Role:
        if role_name and role_name != role.role_name:
            conflict = await self._session.scalar(select(Role).where(Role.role_name == role_name))
            if conflict is not None:
                raise ValueError("role_name_exists")
            role.role_name = role_name
        if role_description is not None:
            role.role_description = role_description
        await self._session.flush()
        await self._session.refresh(role)
        return role

    async def delete_role(self, role: Role) -> None:
        await self._session.execute(
            update(User).where(User.role_id == role.role_id).values(role_id=None)
        )
        await self._session.execute(
            delete(RolePermission).where(RolePermission.role_id == role.role_id)
        )
        await self._session.delete(role)
        await self._session.flush()

    async def list_permissions(self) -> list[Permission]:
        result = await self._session.execute(select(Permission).order_by(Permission.permission_id))
        return list(result.scalars())

    async def get_effective_permissions(self, user_id: int, organization_id: int) -> list[str]:
        stmt = (
            select(Permission.permission_name)
            .join(RolePermission, Permission.permission_id == RolePermission.permission_id)
            .join(Role, Role.role_id == RolePermission.role_id)
            .join(User, User.role_id == Role.role_id)
            .where(User.user_id == user_id)
            .where(Role.organization_id == organization_id)
            .where(RolePermission.organization_id == organization_id)
        )
        result = await self._session.execute(stmt)
        permissions = {row[0] for row in result.all()}
        return sorted(permissions)

    async def create_permission(
        self,
        *,
        permission_name: str,
        permission_description: str | None = None,
    ) -> Permission:
        existing = await self._session.scalar(
            select(Permission).where(Permission.permission_name == permission_name)
        )
        if existing is not None:
            raise ValueError("permission_name_exists")

        permission = Permission(
            permission_name=permission_name,
            permission_description=permission_description,
        )
        self._session.add(permission)
        await self._session.flush()
        await self._session.refresh(permission)
        return permission

    async def assign_permission_to_role(
        self,
        *,
        role: Role,
        permission: Permission,
    ) -> None:
        exists = await self._session.scalar(
            select(func.count())
            .select_from(RolePermission)
            .where(
                RolePermission.role_id == role.role_id,
                RolePermission.permission_id == permission.permission_id,
                RolePermission.organization_id == role.organization_id,
            )
        )
        if exists:
            raise ValueError("role_permission_exists")

        self._session.add(
            RolePermission(
                role_id=role.role_id,
                permission_id=permission.permission_id,
                organization_id=role.organization_id,
            )
        )
        await self._session.flush()

    async def revoke_permission_from_role(
        self,
        *,
        role: Role,
        permission_id: int,
    ) -> None:
        result = await self._session.execute(
            delete(RolePermission)
            .where(
                RolePermission.role_id == role.role_id,
                RolePermission.permission_id == permission_id,
                RolePermission.organization_id == role.organization_id,
            )
            .returning(RolePermission.permission_id)
        )
        if result.first() is None:
            raise ValueError("role_permission_not_found")
        await self._session.flush()

    async def assign_role_to_user(
        self,
        *,
        user: User,
        role: Role,
    ) -> User:
        if user.organization_id != role.organization_id:
            raise ValueError("role_not_in_organization")
        user.role_id = role.role_id
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def revoke_role_from_user(
        self,
        *,
        user: User,
        role_id: int,
    ) -> User:
        if user.role_id != role_id:
            raise ValueError("role_not_assigned")
        user.role_id = None
        await self._session.flush()
        await self._session.refresh(user)
        return user
