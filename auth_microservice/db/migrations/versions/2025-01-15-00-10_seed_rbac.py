"""Seed initial organization, roles, and permissions for RBAC.

Revision ID: b4c0d8d95a7f
Revises: a1f3bc0c3e4b
Create Date: 2025-01-15 00:10:00

"""

from __future__ import annotations

import datetime
import enum

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "b4c0d8d95a7f"
down_revision = "a1f3bc0c3e4b"
branch_labels = None
depends_on = None


class LicenseStatusEnum(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"


def upgrade() -> None:
    now = datetime.datetime.utcnow()

    organization_table = sa.table(
        "organization",
        sa.column("organization_id", sa.Integer),
        sa.column("organization_name", sa.String),
        sa.column("license_status", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    permission_table = sa.table(
        "uuh_permission",
        sa.column("permission_id", sa.Integer),
        sa.column("permission_name", sa.String),
        sa.column("permission_description", sa.Text),
        sa.column("created_at", sa.DateTime),
    )

    roles_table = sa.table(
        "uuh_roles",
        sa.column("role_id", sa.Integer),
        sa.column("organization_id", sa.Integer),
        sa.column("role_name", sa.String),
        sa.column("role_description", sa.Text),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer),
        sa.column("permission_id", sa.Integer),
        sa.column("organization_id", sa.Integer),
        sa.column("created_at", sa.DateTime),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO organization (organization_id, organization_name, license_status, created_at, updated_at)
            VALUES (:organization_id, :organization_name, CAST(:license_status AS license_status), :created_at, :updated_at)
            """
        ).bindparams(
            organization_id=1,
            organization_name='Default Organization',
            license_status='active',
            created_at=now,
            updated_at=now,
        )
    )

    permissions = [
        (1, "user:read", "Read user profiles"),
        (2, "user:write", "Create or update users"),
        (3, "role:assign", "Assign roles to users"),
        (4, "settings:read", "Read organization settings"),
    ]

    op.bulk_insert(
        permission_table,
        [
            {
                "permission_id": pid,
                "permission_name": name,
                "permission_description": description,
                "created_at": now,
            }
            for pid, name, description in permissions
        ],
    )

    op.bulk_insert(
        roles_table,
        [
            {
                "role_id": 1,
                "organization_id": 1,
                "role_name": "super_admin",
                "role_description": "Full access to organization resources",
                "created_at": now,
                "updated_at": now,
            },
            {
                "role_id": 2,
                "organization_id": 1,
                "role_name": "staff",
                "role_description": "Basic staff role with limited permissions",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )

    op.bulk_insert(
        role_permissions_table,
        [
            {"role_id": 1, "permission_id": pid, "organization_id": 1, "created_at": now}
            for pid in [1, 2, 3, 4]
        ]
        + [
            {"role_id": 2, "permission_id": pid, "organization_id": 1, "created_at": now}
            for pid in [1, 4]
        ]
    )

    # Align PostgreSQL sequences with seeded identifiers.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "SELECT setval('organization_organization_id_seq', (SELECT MAX(organization_id) FROM organization))"
            )
        )
        op.execute(
            sa.text(
                "SELECT setval('uuh_permission_permission_id_seq', (SELECT MAX(permission_id) FROM uuh_permission))"
            )
        )
        op.execute(
            sa.text(
                "SELECT setval('uuh_roles_role_id_seq', (SELECT MAX(role_id) FROM uuh_roles))"
            )
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM role_permissions WHERE organization_id = 1"))
    op.execute(sa.text("DELETE FROM uuh_roles WHERE organization_id = 1"))
    op.execute(sa.text("DELETE FROM uuh_permission WHERE permission_id IN (1, 2, 3, 4)"))
    op.execute(sa.text("DELETE FROM organization WHERE organization_id = 1"))
