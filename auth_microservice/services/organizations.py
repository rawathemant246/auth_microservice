"""Organization provisioning and administration helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import (
    LicenseStatusEnum,
    Organization,
    Permission,
    Role,
    RolePermission,
)

ADMIN_PERMISSION_NAMES: list[str] = [
    "org.create",
    "org.read",
    "org.update",
    "org.delete",
    "user.invite",
    "user.read",
    "user.update",
    "user.delete",
    "role.assign",
    "role.revoke",
    "role.read",
    "role.create",
    "role.update",
    "role.delete",
    "role.perm.assign",
    "role.perm.revoke",
    "perm.read",
    "perm.create",
    "settings.read",
    "settings.update",
    "privacy.read",
    "privacy.update",
    "billing.plan.read",
    "billing.plan.write",
    "billing.subscription.read",
    "billing.subscription.write",
    "billing.invoice.read",
    "billing.invoice.write",
    "support.ticket.create",
    "support.ticket.read",
    "support.ticket.update",
    "support.comment",
    "feedback.create",
    "feedback.read",
    "feedback.update",
    "search.read",
    "security.alert.read",
    "security.alert.update",
    "audit.log.read",
    "activity.login.read",
    "activity.user.read",
    # LMS: School
    "school.setup",
    "school.read",
    "school.update",
    "academic.manage",
    # LMS: People
    "student.create",
    "student.read",
    "student.update",
    "student.delete",
    "student.bulk_import",
    "teacher.create",
    "teacher.read",
    "teacher.update",
    "teacher.delete",
    "parent.create",
    "parent.read",
    "parent.update",
    # LMS: Attendance
    "attendance.mark",
    "attendance.read",
    "attendance.report",
    # LMS: Fees
    "fee.structure.manage",
    "fee.collect",
    "fee.read",
    "fee.report",
    "fee.concession.manage",
    # LMS: Content
    "content.create",
    "content.read",
    "content.update",
    "content.delete",
    "assignment.create",
    "assignment.read",
    "assignment.grade",
    # LMS: Assessment
    "exam.create",
    "exam.read",
    "exam.grade",
    "gradebook.read",
    "gradebook.write",
    "report_card.generate",
    "report_card.read",
    # LMS: Communication
    "announcement.create",
    "announcement.read",
    "message.send",
    "message.read",
    # LMS: AI
    "tutor.use",
    "tutor.history.read",
    # LMS: Analytics
    "analytics.read",
]

PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "org.create": "Create new organizations",
    "org.read": "Read organization details",
    "org.update": "Update organization details",
    "org.delete": "Deactivate organizations",
    "user.invite": "Invite or create organization users",
    "user.read": "Read user profiles",
    "user.update": "Update user profiles",
    "user.delete": "Deactivate users",
    "role.assign": "Assign roles to users",
    "role.revoke": "Revoke roles from users",
    "role.read": "List roles",
    "role.create": "Create roles",
    "role.update": "Update roles",
    "role.delete": "Delete roles",
    "role.perm.assign": "Assign permissions to roles",
    "role.perm.revoke": "Revoke permissions from roles",
    "perm.read": "List permissions",
    "perm.create": "Create permissions",
    "settings.read": "Read organization settings",
    "settings.update": "Update organization settings",
    "privacy.read": "Read privacy settings",
    "privacy.update": "Update privacy settings",
    "billing.plan.read": "View billing plans",
    "billing.plan.write": "Create or update billing plans",
    "billing.subscription.read": "View organization subscription",
    "billing.subscription.write": "Create or update organization subscription",
    "billing.invoice.read": "View invoices",
    "billing.invoice.write": "Update invoices",
    "support.ticket.create": "Create support tickets",
    "support.ticket.read": "View support tickets",
    "support.ticket.update": "Update support tickets",
    "support.comment": "Comment on support tickets",
    "feedback.create": "Submit feedback entries",
    "feedback.read": "Read feedback entries",
    "feedback.update": "Update feedback entries",
    "search.read": "Perform cross-resource search",
    "security.alert.read": "View security alerts",
    "security.alert.update": "Update security alert status",
    "audit.log.read": "View audit log entries",
    "activity.login.read": "Review login activity",
    "activity.user.read": "Review user activity",
    "platform.bootstrap": "Initialize platform bootstrap workflows",
    "platform.metrics.read": "Read platform metrics",
    "platform.organizations.manage": "Manage organizations across tenants",
    "platform.users.manage": "Manage users across organizations",
    "platform.rbac.manage": "Manage platform-wide RBAC configuration",
    "platform.audit.view": "View platform-level audit logs",
    # LMS permissions
    "school.setup": "Initial school profile configuration",
    "school.read": "Read school profile and academic structure",
    "school.update": "Update school profile details",
    "academic.manage": "Manage academic years, classes, sections, subjects, timetable",
    "student.create": "Create individual student profiles",
    "student.read": "Read student profiles and data",
    "student.update": "Update student profiles",
    "student.delete": "Deactivate students",
    "student.bulk_import": "Import students via CSV bulk upload",
    "teacher.create": "Create teacher profiles",
    "teacher.read": "Read teacher profiles",
    "teacher.update": "Update teacher profiles",
    "teacher.delete": "Deactivate teachers",
    "parent.create": "Create parent profiles",
    "parent.read": "Read parent profiles",
    "parent.update": "Update parent profiles",
    "attendance.mark": "Mark daily and period-wise attendance",
    "attendance.read": "View attendance records",
    "attendance.report": "Generate attendance reports",
    "fee.structure.manage": "Create and manage fee structures",
    "fee.collect": "Collect fees and record payments",
    "fee.read": "View fee records and invoices",
    "fee.report": "Generate fee collection reports",
    "fee.concession.manage": "Create and manage fee concessions",
    "content.create": "Create learning content and materials",
    "content.read": "Access learning content",
    "content.update": "Update learning content",
    "content.delete": "Remove learning content",
    "assignment.create": "Create assignments",
    "assignment.read": "View assignments",
    "assignment.grade": "Grade student submissions",
    "exam.create": "Create exams and manage question bank",
    "exam.read": "View exams and results",
    "exam.grade": "Grade exam answers",
    "gradebook.read": "View gradebook entries",
    "gradebook.write": "Enter marks and grades",
    "report_card.generate": "Generate report cards",
    "report_card.read": "View report cards",
    "announcement.create": "Create announcements and circulars",
    "announcement.read": "View announcements",
    "message.send": "Send messages to teachers or parents",
    "message.read": "Read messages",
    "tutor.use": "Use the AI tutor for doubt-solving",
    "tutor.history.read": "View AI tutor conversation history",
    "analytics.read": "View analytics dashboards",
}


class OrganizationService:
    """High-level orchestration around organizations and admin roles."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_organization(
        self,
        *,
        name: str,
        license_status: LicenseStatusEnum | None = None,
    ) -> tuple[Organization, Role]:
        """Create a new organization with a default administrator role."""

        existing = await self._session.scalar(
            select(Organization).where(Organization.organization_name == name),
        )
        if existing is not None:
            raise ValueError("organization_name_exists")

        organization = Organization(
            organization_name=name,
            license_status=license_status or LicenseStatusEnum.ACTIVE,
        )
        self._session.add(organization)
        await self._session.flush()

        admin_role = await self.ensure_admin_role(organization)
        await self._session.refresh(organization)
        return organization, admin_role

    async def ensure_admin_role(self, organization: Organization) -> Role:
        """Ensure the default administrator role exists for an organization."""

        role_name = self._build_admin_role_name(organization.organization_id)
        role = await self._session.scalar(
            select(Role)
            .where(Role.organization_id == organization.organization_id)
            .where(Role.role_name == role_name),
        )
        if role is None:
            role = Role(
                organization_id=organization.organization_id,
                role_name=role_name,
                role_description="Organization administrator",
            )
            self._session.add(role)
            await self._session.flush()
            await self._session.refresh(role)

        permissions = await self._ensure_permissions(ADMIN_PERMISSION_NAMES)

        existing_relations_result = await self._session.scalars(
            select(RolePermission.permission_id).where(
                RolePermission.role_id == role.role_id,
                RolePermission.organization_id == organization.organization_id,
            ),
        )
        existing_relations = set(existing_relations_result.all())

        for permission in permissions.values():
            if permission.permission_id in existing_relations:
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

    async def update_organization(
        self,
        organization: Organization,
        updates: dict[str, Any],
    ) -> Organization:
        """Apply updates to an organization enforcing name uniqueness."""

        if updates.get("organization_name"):
            new_name = updates["organization_name"]
            conflict = await self._session.scalar(
                select(Organization)
                .where(Organization.organization_name == new_name)
                .where(Organization.organization_id != organization.organization_id),
            )
            if conflict is not None:
                raise ValueError("organization_name_exists")
            organization.organization_name = new_name

        if updates.get("license_status"):
            organization.license_status = updates["license_status"]

        await self._session.flush()
        await self._session.refresh(organization)
        return organization

    async def deactivate_organization(self, organization: Organization) -> Organization:
        """Mark an organization as suspended."""

        organization.license_status = LicenseStatusEnum.SUSPENDED
        await self._session.flush()
        await self._session.refresh(organization)
        return organization

    async def list_organizations(self) -> list[Organization]:
        """Return all organizations ordered by identifier."""

        result = await self._session.execute(
            select(Organization).order_by(Organization.organization_id),
        )
        return list(result.scalars())

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

    @staticmethod
    def _build_admin_role_name(organization_id: int) -> str:
        return f"org_{organization_id}_admin"
