"""Default role templates for school organizations.

Every school gets this same set of roles, one row per role per organization, so
that ``teacher`` in school 12 is a distinct grantable role from ``teacher`` in
school 13. Schools may add their own roles or re-grant these through the RBAC
admin API; this module only defines what a school starts with.

IMPORTANT: a permission grants a *capability*, never a row scope. ``student.read``
lets a teacher or parent read student records; restricting a teacher to their own
sections and a parent to their own children is the query layer's job in
lms-backend (org_id plus relationship scoping). Do not read this matrix as a
statement about which rows a role can see.
"""

from __future__ import annotations

SCHOOL_ADMIN = "school_admin"
PRINCIPAL = "principal"
TEACHER = "teacher"
STUDENT = "student"
PARENT = "parent"
ACCOUNTANT = "accountant"
LIBRARIAN = "librarian"
TRANSPORT_MANAGER = "transport_manager"

ROLE_DESCRIPTIONS: dict[str, str] = {
    SCHOOL_ADMIN: "Full administrative access to this school",
    PRINCIPAL: "School head; full academic and staff oversight",
    TEACHER: "Teaching staff; classes, content, assessment, grading",
    STUDENT: "Enrolled student",
    PARENT: "Parent or guardian of an enrolled student",
    ACCOUNTANT: "Fee collection and financial reporting",
    LIBRARIAN: "Library catalogue and circulation",
    TRANSPORT_MANAGER: "Routes, vehicles, and student transport mapping",
}

# The 45 LMS permissions seeded by migration d8e4f92a7b30.
_ALL_LMS_PERMISSIONS: tuple[str, ...] = (
    "school.setup",
    "school.read",
    "school.update",
    "academic.manage",
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
    "attendance.mark",
    "attendance.read",
    "attendance.report",
    "fee.structure.manage",
    "fee.collect",
    "fee.read",
    "fee.report",
    "fee.concession.manage",
    "content.create",
    "content.read",
    "content.update",
    "content.delete",
    "assignment.create",
    "assignment.read",
    "assignment.grade",
    "exam.create",
    "exam.read",
    "exam.grade",
    "gradebook.read",
    "gradebook.write",
    "report_card.generate",
    "report_card.read",
    "announcement.create",
    "announcement.read",
    "message.send",
    "message.read",
    "tutor.use",
    "tutor.history.read",
    "analytics.read",
)

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    SCHOOL_ADMIN: _ALL_LMS_PERMISSIONS,
    # Everything the school admin has except one-time profile bootstrapping.
    PRINCIPAL: tuple(p for p in _ALL_LMS_PERMISSIONS if p != "school.setup"),
    TEACHER: (
        "school.read",
        "student.read",
        "teacher.read",
        "parent.read",
        "attendance.mark",
        "attendance.read",
        "attendance.report",
        "content.create",
        "content.read",
        "content.update",
        "content.delete",
        "assignment.create",
        "assignment.read",
        "assignment.grade",
        "exam.create",
        "exam.read",
        "exam.grade",
        "gradebook.read",
        "gradebook.write",
        "report_card.generate",
        "report_card.read",
        "announcement.create",
        "announcement.read",
        "message.send",
        "message.read",
        "tutor.history.read",
        "analytics.read",
    ),
    STUDENT: (
        "school.read",
        "attendance.read",
        "content.read",
        "assignment.read",
        "exam.read",
        "gradebook.read",
        "report_card.read",
        "announcement.read",
        "message.send",
        "message.read",
        "tutor.use",
    ),
    PARENT: (
        "school.read",
        "student.read",
        "attendance.read",
        "fee.read",
        "gradebook.read",
        "report_card.read",
        "announcement.read",
        "message.send",
        "message.read",
        "tutor.history.read",
    ),
    ACCOUNTANT: (
        "school.read",
        "student.read",
        "fee.structure.manage",
        "fee.collect",
        "fee.read",
        "fee.report",
        "fee.concession.manage",
        "announcement.read",
    ),
    # Library and transport modules are not built in lms-backend yet, so these
    # start with read-only school context and gain module permissions when the
    # corresponding endpoints land.
    LIBRARIAN: (
        "school.read",
        "student.read",
        "announcement.read",
    ),
    TRANSPORT_MANAGER: (
        "school.read",
        "student.read",
        "announcement.read",
    ),
}

DEFAULT_SCHOOL_ROLES: tuple[str, ...] = tuple(ROLE_PERMISSIONS)
