"""Add LMS education permissions to RBAC.

Revision ID: d8e4f92a7b30
Revises: c7f3b8246470
Create Date: 2025-01-15 00:30:00

"""
from __future__ import annotations

import datetime

import sqlalchemy as sa
from alembic import op

revision = "d8e4f92a7b30"
down_revision = "c7f3b8246470"
branch_labels = None
depends_on = None

LMS_PERMISSIONS = [
    ("school.setup", "Initial school profile configuration"),
    ("school.read", "Read school profile and academic structure"),
    ("school.update", "Update school profile details"),
    ("academic.manage", "Manage academic years, classes, sections, subjects, timetable"),
    ("student.create", "Create individual student profiles"),
    ("student.read", "Read student profiles and data"),
    ("student.update", "Update student profiles"),
    ("student.delete", "Deactivate students"),
    ("student.bulk_import", "Import students via CSV bulk upload"),
    ("teacher.create", "Create teacher profiles"),
    ("teacher.read", "Read teacher profiles"),
    ("teacher.update", "Update teacher profiles"),
    ("teacher.delete", "Deactivate teachers"),
    ("parent.create", "Create parent profiles"),
    ("parent.read", "Read parent profiles"),
    ("parent.update", "Update parent profiles"),
    ("attendance.mark", "Mark daily and period-wise attendance"),
    ("attendance.read", "View attendance records"),
    ("attendance.report", "Generate attendance reports"),
    ("fee.structure.manage", "Create and manage fee structures"),
    ("fee.collect", "Collect fees and record payments"),
    ("fee.read", "View fee records and invoices"),
    ("fee.report", "Generate fee collection reports"),
    ("fee.concession.manage", "Create and manage fee concessions"),
    ("content.create", "Create learning content and materials"),
    ("content.read", "Access learning content"),
    ("content.update", "Update learning content"),
    ("content.delete", "Remove learning content"),
    ("assignment.create", "Create assignments"),
    ("assignment.read", "View assignments"),
    ("assignment.grade", "Grade student submissions"),
    ("exam.create", "Create exams and manage question bank"),
    ("exam.read", "View exams and results"),
    ("exam.grade", "Grade exam answers"),
    ("gradebook.read", "View gradebook entries"),
    ("gradebook.write", "Enter marks and grades"),
    ("report_card.generate", "Generate report cards"),
    ("report_card.read", "View report cards"),
    ("announcement.create", "Create announcements and circulars"),
    ("announcement.read", "View announcements"),
    ("message.send", "Send messages to teachers or parents"),
    ("message.read", "Read messages"),
    ("tutor.use", "Use the AI tutor for doubt-solving"),
    ("tutor.history.read", "View AI tutor conversation history"),
    ("analytics.read", "View analytics dashboards"),
]


def upgrade() -> None:
    now = datetime.datetime.utcnow()

    conn = op.get_bind()
    for name, description in LMS_PERMISSIONS:
        exists = conn.execute(
            sa.text("SELECT 1 FROM uuh_permission WHERE permission_name = :name"),
            {"name": name},
        ).fetchone()
        if not exists:
            conn.execute(
                sa.text(
                    "INSERT INTO uuh_permission (permission_name, permission_description, created_at) "
                    "VALUES (:name, :desc, :now)"
                ),
                {"name": name, "desc": description, "now": now},
            )

    if conn.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "SELECT setval('uuh_permission_permission_id_seq', "
                "(SELECT MAX(permission_id) FROM uuh_permission))"
            )
        )


def downgrade() -> None:
    perm_names = [name for name, _ in LMS_PERMISSIONS]
    placeholders = ", ".join(f"'{n}'" for n in perm_names)

    op.execute(
        sa.text(
            f"DELETE FROM role_permissions WHERE permission_id IN "
            f"(SELECT permission_id FROM uuh_permission WHERE permission_name IN ({placeholders}))"
        )
    )
    op.execute(
        sa.text(
            f"DELETE FROM uuh_permission WHERE permission_name IN ({placeholders})"
        )
    )
