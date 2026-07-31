"""Add student.read.all and grant it to the school-wide roles.

The permission that lets lms-backend enforce row scope without failing open. Full
reasoning is in LMS-backend#68; the short version:

`student.read` is held by school_admin, principal, teacher, parent, accountant,
librarian and transport_manager alike. It says "may read student records" and cannot
say *which* students, so a parent and an accountant are indistinguishable by
capability -- and they must not see the same rows.

lms-backend derives scope from relationships: a student is themselves, a parent has
their children via student_parent_map, a teacher has the students in sections they
are assigned to or class-teach. `student.read.all` is how a caller says "every
student in this school" instead.

The reason it is an explicit grant and not an inference: the tempting shortcut is
"a caller with no student, parent or teacher profile must be office staff, so give
them the school", and that fails open. One failed profile insert and a student sees
every child's report card. With this permission, absence of a relationship means
absence of access.

Roles that get it: school_admin and principal via _ALL_LMS_PERMISSIONS, plus
accountant, librarian and transport_manager, which are school-wide operational
roles. Teacher, parent and student are deliberately excluded.

Idempotent, and grants only to roles that already exist -- an organization created
later gets it from the role templates.

Revision ID: c7b2e5f14a93
Revises: f1a7c3d21e08
Create Date: 2026-07-31 00:10:00

"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c7b2e5f14a93"
down_revision = "f1a7c3d21e08"
branch_labels = None
depends_on = None

PERMISSION_NAME = "student.read.all"
PERMISSION_DESCRIPTION = (
    "Read records for every student in the school, not only related ones"
)

# Kept in step with ROLE_PERMISSIONS in auth_microservice/rbac/role_templates.py.
# Written out here rather than imported, because a migration has to keep describing
# what it did even after the templates move on.
ROLES_GRANTED = (
    "school_admin",
    "principal",
    "accountant",
    "librarian",
    "transport_manager",
)


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.datetime.now(datetime.timezone.utc)

    permission_id = conn.execute(
        sa.text(
            "SELECT permission_id FROM uuh_permission WHERE permission_name = :name"
        ).bindparams(name=PERMISSION_NAME),
    ).scalar()

    if permission_id is None:
        permission_id = conn.execute(
            sa.text(
                "INSERT INTO uuh_permission "
                "(permission_name, permission_description, created_at) "
                "VALUES (:name, :descr, :now) RETURNING permission_id"
            ).bindparams(name=PERMISSION_NAME, descr=PERMISSION_DESCRIPTION, now=now),
        ).scalar()

    if conn.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "SELECT setval('uuh_permission_permission_id_seq', "
                "(SELECT MAX(permission_id) FROM uuh_permission))"
            )
        )

    # Every existing (organization, role) pair whose role should hold it. Driven off
    # uuh_roles rather than off the organization list, so a school that renamed or
    # removed a default role is left as its administrator left it.
    role_rows = conn.execute(
        sa.text(
            "SELECT role_id, organization_id FROM uuh_roles "
            "WHERE role_name = ANY(:names)"
        ).bindparams(sa.bindparam("names", value=list(ROLES_GRANTED))),
    ).all()

    for role_id, organization_id in role_rows:
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions "
                "(role_id, permission_id, organization_id, created_at) "
                "VALUES (:role_id, :perm_id, :org, :now) "
                "ON CONFLICT DO NOTHING"
            ).bindparams(
                role_id=role_id, perm_id=permission_id, org=organization_id, now=now
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()

    permission_id = conn.execute(
        sa.text(
            "SELECT permission_id FROM uuh_permission WHERE permission_name = :name"
        ).bindparams(name=PERMISSION_NAME),
    ).scalar()

    if permission_id is None:
        return

    # Grants first: role_permissions references the permission.
    #
    # Downgrading removes the only way to say "the whole school", so every caller
    # falls back to relationship scope. That means office staff lose access rather
    # than gain it, which is the safe direction for a rollback to fail in.
    conn.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_id = :pid").bindparams(
            pid=permission_id
        ),
    )
    conn.execute(
        sa.text("DELETE FROM uuh_permission WHERE permission_id = :pid").bindparams(
            pid=permission_id
        ),
    )
