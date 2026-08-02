"""Add homework.write and grant it to teaching and office roles.

The homework diary (LMS-backend#60) needs its own permission rather than reusing
`assignment.create`.

That issue's whole framing is that a diary entry is *not* an assignment: an assignment
has a due date, submissions, a rubric and grading, and a diary entry is "read pages
40-45, bring the geometry box tomorrow". Reusing `assignment.create` would mean the
permission no longer says what it does, and LMS-backend#76 was an audit of exactly
that kind of drift -- a permission applied to something adjacent, then to something
adjacent to that.

Reading is deliberately not a permission. A student sees their own diary and a parent
sees their children's, which is row scope rather than capability -- lms-backend
resolves it through `Scoped<Student>`, the seam #68 built. A read permission would
have to be granted to students and parents alike and would say nothing.

Roles that get it: teacher, because writing the diary is the daily job it exists for;
school_admin and principal via _ALL_LMS_PERMISSIONS.

Idempotent, and grants only to roles that already exist -- an organization created
later gets it from the role templates.

Revision ID: e2f4b8a6c910
Revises: d9c1a5e37f24
Create Date: 2026-08-03 00:10:00

"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e2f4b8a6c910"
down_revision = "d9c1a5e37f24"
branch_labels = None
depends_on = None

PERMISSION_NAME = "homework.write"
PERMISSION_DESCRIPTION = (
    "Write and edit homework diary entries for a section and subject"
)

# Kept in step with ROLE_PERMISSIONS in auth_microservice/rbac/role_templates.py.
# Written out here rather than imported, because a migration has to keep describing
# what it did even after the templates move on.
ROLES_GRANTED = (
    "school_admin",
    "principal",
    "teacher",
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
    # Downgrading leaves lms-backend asking for a permission nobody holds, so writing
    # a diary entry answers 403 rather than becoming open to everyone. Reading is
    # unaffected, being row-scoped. That is the safe direction for a rollback to fail
    # in.
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
