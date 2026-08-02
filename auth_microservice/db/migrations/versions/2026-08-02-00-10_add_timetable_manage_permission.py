"""Add timetable.manage and grant it to the roles that build a timetable.

The four timetable routes in lms-backend were mounted without a permission guard,
unlike every route around them, so any authenticated member of a school could create
period definitions and timetable slots -- including the students and parents in it.
Found while adding conflict detection in LMS-backend#59: it makes little sense to
refuse a slot that double-books a teacher while not checking who is asking.

Only writes are guarded. Reading a timetable stays open to the school, because a
teacher, a student and a parent all legitimately need to see it, and a read
permission would have to be granted to everyone to say nothing.

Roles that get it: school_admin and principal, via _ALL_LMS_PERMISSIONS. Teacher is
deliberately excluded -- reading the timetable is not rewriting it, and a teacher who
could edit slots could quietly move their own periods.

Idempotent, and grants only to roles that already exist -- an organization created
later gets it from the role templates.

Revision ID: b4e9d13c6a52
Revises: c7b2e5f14a93
Create Date: 2026-08-02 00:10:00

"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b4e9d13c6a52"
down_revision = "c7b2e5f14a93"
branch_labels = None
depends_on = None

PERMISSION_NAME = "timetable.manage"
PERMISSION_DESCRIPTION = (
    "Create and change period definitions and timetable slots for the school"
)

# Kept in step with ROLE_PERMISSIONS in auth_microservice/rbac/role_templates.py.
# Written out here rather than imported, because a migration has to keep describing
# what it did even after the templates move on.
ROLES_GRANTED = (
    "school_admin",
    "principal",
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

    # Driven off uuh_roles rather than off the organization list, so a school that
    # renamed or removed a default role is left as its administrator left it.
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
    # Downgrading leaves lms-backend asking for a permission nobody holds, so timetable
    # writes start answering 403 rather than reverting to being open to everyone. That
    # is the safe direction for a rollback to fail in.
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
