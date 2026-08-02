"""Add staff.attendance.mark and staff.attendance.read.

Staff attendance (LMS-backend#58) needs its own permissions rather than reusing
`attendance.mark` and `attendance.read`.

Those two are held by every teacher, because marking and reading *student* attendance
is a teacher's daily job. Reusing them for staff attendance would let any teacher
record their own arrival time, their colleagues' absences, and read the whole staff
room's leave history -- on data the issue states will eventually feed payroll. The
name collision is a coincidence of the word "attendance"; the authority is not the
same authority.

Granted to school_admin and principal, via _ALL_LMS_PERMISSIONS. Deliberately not
teacher.

A teacher reading *their own* staff attendance is legitimate and is not covered here:
that is row scope, not capability, and the same distinction LMS-backend#68 drew for
students applies. It needs a scope resolver for teachers, which does not exist yet.
Until then a teacher cannot read staff attendance at all, which errs towards refusing
rather than towards exposing the staff room.

Accountant is also excluded for now. Payroll is explicitly out of scope for #58, and
granting an accountant read access to leave records before anything consumes them
would be guessing at a workflow nobody has designed.

Revision ID: d9c1a5e37f24
Revises: b4e9d13c6a52
Create Date: 2026-08-02 01:20:00

"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d9c1a5e37f24"
down_revision = "b4e9d13c6a52"
branch_labels = None
depends_on = None

PERMISSIONS = (
    (
        "staff.attendance.mark",
        "Record staff attendance, check-in and check-out, and leave",
    ),
    (
        "staff.attendance.read",
        "Read staff attendance records and per-teacher monthly summaries",
    ),
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

    role_rows = conn.execute(
        sa.text(
            "SELECT role_id, organization_id FROM uuh_roles "
            "WHERE role_name = ANY(:names)"
        ).bindparams(sa.bindparam("names", value=list(ROLES_GRANTED))),
    ).all()

    for name, description in PERMISSIONS:
        permission_id = conn.execute(
            sa.text(
                "SELECT permission_id FROM uuh_permission WHERE permission_name = :name"
            ).bindparams(name=name),
        ).scalar()

        if permission_id is None:
            permission_id = conn.execute(
                sa.text(
                    "INSERT INTO uuh_permission "
                    "(permission_name, permission_description, created_at) "
                    "VALUES (:name, :descr, :now) RETURNING permission_id"
                ).bindparams(name=name, descr=description, now=now),
            ).scalar()

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

    if conn.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "SELECT setval('uuh_permission_permission_id_seq', "
                "(SELECT MAX(permission_id) FROM uuh_permission))"
            )
        )


def downgrade() -> None:
    conn = op.get_bind()

    for name, _ in PERMISSIONS:
        permission_id = conn.execute(
            sa.text(
                "SELECT permission_id FROM uuh_permission WHERE permission_name = :name"
            ).bindparams(name=name),
        ).scalar()

        if permission_id is None:
            continue

        # Grants first: role_permissions references the permission.
        #
        # Downgrading leaves lms-backend asking for permissions nobody holds, so staff
        # attendance answers 403 rather than becoming readable by everyone. That is the
        # safe direction for a rollback to fail in.
        conn.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE permission_id = :pid"
            ).bindparams(pid=permission_id),
        )
        conn.execute(
            sa.text("DELETE FROM uuh_permission WHERE permission_id = :pid").bindparams(
                pid=permission_id
            ),
        )
