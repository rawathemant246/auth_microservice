"""Seed default school role templates and grant them the LMS permissions.

Migration d8e4f92a7b30 created 45 LMS permission rows but never granted them to
any role, and no role existed for teacher, student, or parent at all. That left
lms-backend with nothing to authorize against: bulk-imported users were created
with role_id = NULL and every role-guarded endpoint refused them.

This migration also widens the role_name uniqueness constraint. It was globally
UNIQUE, which in a multi-tenant deployment means the name "teacher" could exist
in exactly one school for the lifetime of the database. Roles are per-organization
rows, so uniqueness belongs on (organization_id, role_name).

Revision ID: f1a7c3d21e08
Revises: d8e4f92a7b30
Create Date: 2026-07-25 00:10:00

"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from alembic import op

from auth_microservice.rbac.role_templates import (
    ROLE_DESCRIPTIONS,
    ROLE_PERMISSIONS,
)

# revision identifiers, used by Alembic.
revision = "f1a7c3d21e08"
down_revision = "d8e4f92a7b30"
branch_labels = None
depends_on = None

# Roles belonging to the platform rather than to a school. These are left alone.
_PLATFORM_ROLE_NAMES = ("super_admin",)


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.datetime.now(datetime.timezone.utc)

    # ---- 1. Uniqueness moves from role_name to (organization_id, role_name) ----
    # The original constraint was created implicitly via unique=True, so Postgres
    # named it uuh_roles_role_name_key. Drop by name if present, then add the
    # composite. Guarded so re-running against a partially migrated database is safe.
    if conn.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "ALTER TABLE uuh_roles DROP CONSTRAINT IF EXISTS uuh_roles_role_name_key"
            )
        )
        existing = conn.execute(
            sa.text(
                "SELECT 1 FROM pg_constraint WHERE conname = 'uq_roles_org_role_name'"
            )
        ).scalar()
        if not existing:
            op.create_unique_constraint(
                "uq_roles_org_role_name",
                "uuh_roles",
                ["organization_id", "role_name"],
            )

    # ---- 2. Resolve permission names to ids ----
    wanted: set[str] = set()
    for names in ROLE_PERMISSIONS.values():
        wanted.update(names)

    permission_ids: dict[str, int] = {
        name: pid
        for name, pid in conn.execute(
            sa.text(
                "SELECT permission_name, permission_id FROM uuh_permission "
                "WHERE permission_name = ANY(:names)"
            ).bindparams(sa.bindparam("names", value=sorted(wanted))),
        ).all()
    }

    missing = sorted(wanted - set(permission_ids))
    if missing:
        raise RuntimeError(
            "cannot seed role templates, permissions absent from uuh_permission: "
            + ", ".join(missing)
        )

    # ---- 3. One role row per template per organization, plus grants ----
    org_ids = [
        row[0]
        for row in conn.execute(
            sa.text("SELECT organization_id FROM organization ORDER BY organization_id"),
        ).all()
    ]

    for org_id in org_ids:
        for role_name, permission_names in ROLE_PERMISSIONS.items():
            if role_name in _PLATFORM_ROLE_NAMES:
                continue

            role_id = conn.execute(
                sa.text(
                    "SELECT role_id FROM uuh_roles "
                    "WHERE organization_id = :org AND role_name = :name"
                ).bindparams(org=org_id, name=role_name),
            ).scalar()

            if role_id is None:
                role_id = conn.execute(
                    sa.text(
                        "INSERT INTO uuh_roles "
                        "(organization_id, role_name, role_description, created_at, updated_at) "
                        "VALUES (:org, :name, :descr, :now, :now) "
                        "RETURNING role_id"
                    ).bindparams(
                        org=org_id,
                        name=role_name,
                        descr=ROLE_DESCRIPTIONS.get(role_name),
                        now=now,
                    ),
                ).scalar()

            for permission_name in permission_names:
                conn.execute(
                    sa.text(
                        "INSERT INTO role_permissions "
                        "(role_id, permission_id, organization_id, created_at) "
                        "VALUES (:role_id, :perm_id, :org, :now) "
                        "ON CONFLICT DO NOTHING"
                    ).bindparams(
                        role_id=role_id,
                        perm_id=permission_ids[permission_name],
                        org=org_id,
                        now=now,
                    ),
                )

    if conn.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "SELECT setval('uuh_roles_role_id_seq', "
                "(SELECT MAX(role_id) FROM uuh_roles))"
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    template_names = [
        name for name in ROLE_PERMISSIONS if name not in _PLATFORM_ROLE_NAMES
    ]

    # Detach users before removing the roles they point at, so the FK holds.
    conn.execute(
        sa.text(
            "UPDATE uuh_users SET role_id = NULL WHERE role_id IN "
            "(SELECT role_id FROM uuh_roles WHERE role_name = ANY(:names))"
        ).bindparams(sa.bindparam("names", value=template_names)),
    )
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE role_id IN "
            "(SELECT role_id FROM uuh_roles WHERE role_name = ANY(:names))"
        ).bindparams(sa.bindparam("names", value=template_names)),
    )
    conn.execute(
        sa.text(
            "DELETE FROM uuh_roles WHERE role_name = ANY(:names)"
        ).bindparams(sa.bindparam("names", value=template_names)),
    )

    if conn.dialect.name == "postgresql":
        op.drop_constraint("uq_roles_org_role_name", "uuh_roles", type_="unique")
        op.create_unique_constraint(
            "uuh_roles_role_name_key", "uuh_roles", ["role_name"]
        )
