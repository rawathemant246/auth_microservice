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

# Every LMS permission. 45 were seeded by migration d8e4f92a7b30; `student.read.all`
# (c7b2e5f14a93) and `timetable.manage` (b4e9d13c6a52) came later, each with its own
# migration, because changing this tuple alone does not reach a school that already
# exists -- the templates are only read when an organization's roles are created.
_ALL_LMS_PERMISSIONS: tuple[str, ...] = (
    "school.setup",
    "school.read",
    "school.update",
    "academic.manage",
    # Writes only: creating period definitions and timetable slots. Reading a
    # timetable is deliberately not a permission -- a teacher, a student and a parent
    # all need to see it, so a read permission would have to be granted to everyone
    # and would therefore say nothing. See LMS-backend#59.
    "timetable.manage",
    "student.create",
    "student.read",
    # Capability's one concession to scope, and the reason it exists is written up in
    # LMS-backend#68. `student.read` cannot express scope: a parent and an accountant
    # both hold it, and they must not see the same students. lms-backend derives scope
    # from relationships -- a parent's own children, a teacher's own sections -- and
    # this is how a caller says "every student in this school" instead.
    #
    # It has to be an explicit grant rather than an inference. The tempting shortcut is
    # "a caller with no student, parent or teacher profile must be office staff, so
    # give them everything", and that fails open: one broken profile insert and a
    # student sees the whole school. Absence of a relationship now means absence of
    # access.
    #
    # Governs everything that resolves to a student, not only student profiles --
    # report cards, invoices, receipts, attendance, tutor sessions.
    "student.read.all",
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
    # ---- who legitimately sees the whole school ----
    #
    # school_admin and principal get `student.read.all` through _ALL_LMS_PERMISSIONS.
    # The three below are school-wide operational roles: an accountant bills every
    # family, a librarian issues a book to any student, a transport manager assigns any
    # student to a route. Teacher, parent and student are deliberately absent -- their
    # scope comes from a relationship, and lms-backend refuses what the relationship
    # does not cover.
    ACCOUNTANT: (
        "school.read",
        "student.read",
        "student.read.all",
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
        "student.read.all",
        "announcement.read",
    ),
    TRANSPORT_MANAGER: (
        "school.read",
        "student.read",
        "student.read.all",
        "announcement.read",
    ),
}

DEFAULT_SCHOOL_ROLES: tuple[str, ...] = tuple(ROLE_PERMISSIONS)
