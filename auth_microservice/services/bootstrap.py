"""Bootstrap helpers for platform-level superuser provisioning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import (
    LicenseStatusEnum,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
)
from auth_microservice.services.auth.service import AuthService
from auth_microservice.services.organizations import (
    ADMIN_PERMISSION_NAMES,
    PERMISSION_DESCRIPTIONS,
)


@dataclass(slots=True)
class SuperuserBootstrapResult:
    """Outcome of a bootstrap attempt."""

    organization: Organization
    role: Role
    user: User
    created: bool


SUPER_ADMIN_ROLE_NAME = "super_admin"
ROOT_ORGANIZATION_NAME = "RootOrg"
SUPER_ADMIN_PERMISSION_NAMES: tuple[str, ...] = tuple(
    sorted(
        {
            *ADMIN_PERMISSION_NAMES,
            "platform.bootstrap",
            "platform.metrics.read",
            "platform.organizations.manage",
            "platform.users.manage",
            "platform.rbac.manage",
            "platform.audit.view",
        },
    ),
)


class PlatformBootstrapService:
    """Coordinate creation of the platform root organization and superuser."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def organizations_exist(self) -> bool:
        """Return True when at least one organization is present."""

        count = await self._session.scalar(
            select(func.count()).select_from(Organization),
        )
        return bool(count)

    async def ensure_root_organization(self) -> Organization:
        """Fetch or create the global root organization."""

        organization = await self._session.scalar(
            select(Organization).where(Organization.organization_name == ROOT_ORGANIZATION_NAME),
        )
        if organization is not None:
            return organization

        organization = Organization(
            organization_name=ROOT_ORGANIZATION_NAME,
            license_status=LicenseStatusEnum.ACTIVE,
        )
        self._session.add(organization)
        await self._session.flush()
        await self._session.refresh(organization)
        return organization

    async def ensure_super_admin_role(self, organization: Organization) -> Role:
        """Fetch or create the super admin role bound to the root organization."""

        role = await self._session.scalar(
            select(Role).where(Role.role_name == SUPER_ADMIN_ROLE_NAME),
        )
        if role is None:
            role = Role(
                organization_id=organization.organization_id,
                role_name=SUPER_ADMIN_ROLE_NAME,
                role_description="Platform super administrator",
            )
            self._session.add(role)
            await self._session.flush()
            await self._session.refresh(role)

        permissions = await self._ensure_permissions(SUPER_ADMIN_PERMISSION_NAMES)
        existing_assignments = await self._session.scalars(
            select(RolePermission.permission_id).where(
                RolePermission.role_id == role.role_id,
                RolePermission.organization_id == organization.organization_id,
            ),
        )
        assigned = set(existing_assignments.all())

        for permission in permissions.values():
            if permission.permission_id in assigned:
                continue
            self._session.add(
                RolePermission(
                    role_id=role.role_id,
                    permission_id=permission.permission_id,
                    organization_id=organization.organization_id,
                ),
            )
        await self._session.flush()
        return role

    async def bootstrap_superuser(
        self,
        admin_payload: Mapping[str, Any],
    ) -> SuperuserBootstrapResult:
        """Ensure a superuser exists using the provided admin payload."""

        organization = await self.ensure_root_organization()
        role = await self.ensure_super_admin_role(organization)

        existing_super_user = await self._session.scalar(
            select(User).where(User.role_id == role.role_id),
        )
        if existing_super_user is not None:
            return SuperuserBootstrapResult(
                organization=organization,
                role=role,
                user=existing_super_user,
                created=False,
            )

        auth_service = AuthService(self._session)
        payload = dict(admin_payload)
        contact_info = payload.pop("contact_information", {})

        register_payload: dict[str, Any] = {
            **payload,
            "organization_id": organization.organization_id,
            "role_id": role.role_id,
            "contact_information": dict(contact_info),
        }
        user = await auth_service.register_user(register_payload)
        await self._session.refresh(user)
        return SuperuserBootstrapResult(
            organization=organization,
            role=role,
            user=user,
            created=True,
        )

    async def _ensure_permissions(
        self,
        permission_names: Iterable[str],
    ) -> dict[str, Permission]:
        names = list(permission_names)
        if not names:
            return {}

        result = await self._session.execute(
            select(Permission).where(Permission.permission_name.in_(names)),
        )
        found = {permission.permission_name: permission for permission in result.scalars()}

        missing = [name for name in names if name not in found]
        for name in missing:
            permission = Permission(
                permission_name=name,
                permission_description=PERMISSION_DESCRIPTIONS.get(
                    name,
                    f"Permission for {name}",
                ),
            )
            self._session.add(permission)
            found[name] = permission

        if missing:
            await self._session.flush()

        return found
