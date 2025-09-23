"""pycasbin integration for RBAC policy enforcement."""

from __future__ import annotations

import asyncio
from pathlib import Path

import casbin
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from auth_microservice.db.models.oltp import Permission, Role, RolePermission, User


class RbacService:
    """Thin wrapper around casbin enforcer loading policies from Postgres."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        model_path: str | Path,
    ) -> None:
        self._session_factory = session_factory
        self._model_path = str(model_path)
        self._enforcer = casbin.Enforcer(self._model_path, enable_log=False)
        self._lock = asyncio.Lock()
        self._policies_loaded = False

    async def ensure_policies_loaded(self) -> None:
        """Eagerly load policies if they have not been loaded yet."""

        if self._policies_loaded:
            return
        await self.reload_policies()

    async def reload_policies(self) -> None:
        """Reload policies from the relational database."""

        async with self._lock:
            logger.debug("Reloading RBAC policies from OLTP store")
            self._enforcer.clear_policy()
            async with self._session_factory() as session:
                await self._load_role_permissions(session)
                await self._load_user_roles(session)
            self._policies_loaded = True

    async def _load_role_permissions(self, session: AsyncSession) -> None:
        stmt = (
            select(RolePermission, Role.role_id, Permission.permission_name)
            .join(Role, Role.role_id == RolePermission.role_id)
            .join(Permission, Permission.permission_id == RolePermission.permission_id)
        )
        result = await session.execute(stmt)
        for role_permission, role_id, permission_name in result.all():
            policy = (
                str(role_id),
                permission_name,
                str(role_permission.organization_id),
                "access",
            )
            self._enforcer.add_policy(*policy)
            logger.debug("Loaded policy %s", policy)

    async def _load_user_roles(self, session: AsyncSession) -> None:
        stmt = select(User.user_id, User.role_id, User.organization_id).where(User.role_id.isnot(None))
        result = await session.execute(stmt)
        for user_id, role_id, organization_id in result.all():
            if role_id is None:
                continue
            grouping = (str(user_id), str(role_id), str(organization_id))
            self._enforcer.add_grouping_policy(*grouping)
            logger.debug("Loaded grouping policy %s", grouping)

    async def enforce(
        self,
        user_id: int,
        permission_name: str,
        organization_id: int,
        action: str = "access",
    ) -> bool:
        """Check if user has permission within a given organization."""

        await self.ensure_policies_loaded()
        decision = await asyncio.to_thread(
            self._enforcer.enforce,
            str(user_id),
            permission_name,
            str(organization_id),
            action,
        )
        logger.debug(
            "RBAC enforce user=%s perm=%s org=%s -> %s",
            user_id,
            permission_name,
            organization_id,
            decision,
        )
        return bool(decision)

    async def get_user_permissions(self, user_id: int, organization_id: int) -> list[str]:
        """Fetch all permissions available to a user in an organization."""

        await self.ensure_policies_loaded()
        roles = await asyncio.to_thread(
            self._enforcer.get_roles_for_user_in_domain,
            str(user_id),
            str(organization_id),
        )
        permissions: set[str] = set()
        for role in roles:
            policies = await asyncio.to_thread(
                self._enforcer.get_permissions_for_user_in_domain,
                role,
                str(organization_id),
            )
            for _, permission_name, _, _ in policies:
                permissions.add(permission_name)
        return sorted(permissions)

    async def invalidate_cache(self) -> None:
        """Force subsequent calls to reload policies."""

        self._policies_loaded = False

    @property
    def enforcer(self) -> casbin.Enforcer:
        """Return underlying casbin enforcer (read-only usage)."""

        return self._enforcer
