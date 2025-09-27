"""SQLAlchemy models for the OLTP relational schema."""

from __future__ import annotations

import enum
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth_microservice.db.base import Base

# region: Enumerations ------------------------------------------------------------------


class GenderEnum(str, enum.Enum):
    """Gender options for a user."""

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class UserStatusEnum(str, enum.Enum):
    """Status of a user account."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class LicenseStatusEnum(str, enum.Enum):
    """Organization license status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"


class PlanTypeEnum(str, enum.Enum):
    """Subscription plan types."""

    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"


class PaymentStatusEnum(str, enum.Enum):
    """Payment states for subscriptions."""

    PAID = "paid"
    UNPAID = "unpaid"
    OVERDUE = "overdue"


class BillingCycleEnum(str, enum.Enum):
    """Billing cycles supported by invoices and plans."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class SupportLevelEnum(str, enum.Enum):
    """Support level attached to a billing plan."""

    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class PriorityEnum(str, enum.Enum):
    """Priority of a support ticket."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatusEnum(str, enum.Enum):
    """Lifecycle status of a support ticket."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class FeedbackTypeEnum(str, enum.Enum):
    """Feedback categories."""

    SUGGESTION = "suggestion"
    BUG = "bug"
    FEATURE_REQUEST = "feature_request"
    OTHER = "other"


class FeedbackStatusEnum(str, enum.Enum):
    """Feedback processing states."""

    NEW = "new"
    IN_REVIEW = "in_review"
    IMPLEMENTED = "implemented"
    CLOSED = "closed"


class AlertStatusEnum(str, enum.Enum):
    """Security alert status."""

    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class LoginMethodEnum(str, enum.Enum):
    """Authentication method used during login."""

    STANDARD = "standard"
    OAUTH = "oauth"
    SSO = "sso"
    MULTI_FACTOR = "multi_factor"


class SupportStatusEnum(str, enum.Enum):
    """Legacy alias for support ticket status (kept for clarity)."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class InvoiceStatusEnum(str, enum.Enum):
    """Invoice status."""

    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"


class PaymentMethodEnum(str, enum.Enum):
    """Accepted payment methods."""

    CREDIT_CARD = "credit_card"
    BANK_TRANSFER = "bank_transfer"
    PAYPAL = "paypal"
    OTHER = "other"


class SubscriptionHistoryStatusEnum(str, enum.Enum):
    """Subscription history states."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    CANCELLED = "cancelled"


class SupportPriorityEnum(str, enum.Enum):
    """Alias to avoid confusion with other enums."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class SsoProviderName(str, enum.Enum):
    """Supported SSO providers."""

    GOOGLE = "google"


# endregion ---------------------------------------------------------------------------


# region: Core entities ----------------------------------------------------------------


class Organization(Base):
    """Represents a tenant/organization (e.g., school)."""

    __tablename__ = "organization"

    organization_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    license_status: Mapped[LicenseStatusEnum] = mapped_column(
        Enum(LicenseStatusEnum, name="license_status"),
        default=LicenseStatusEnum.ACTIVE,
        nullable=False,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
    )

    users: Mapped[list["User"]] = relationship("User", back_populates="organization", foreign_keys="User.organization_id", primaryjoin="Organization.organization_id == User.organization_id")
    roles: Mapped[list["Role"]] = relationship("Role", back_populates="organization")
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="organization",
    )
    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="organization")
    usage_metrics: Mapped[list["UsageMetric"]] = relationship(
        "UsageMetric", back_populates="organization",
    )
    system_health_logs: Mapped[list["SystemHealthLog"]] = relationship(
        "SystemHealthLog", back_populates="organization",
    )
    system_alerts: Mapped[list["SystemAlert"]] = relationship(
        "SystemAlert", back_populates="organization",
    )


class Role(Base):
    """Role entity scoped to an organization."""

    __tablename__ = "uuh_roles"

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organization.organization_id"), nullable=False,
    )
    role_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    role_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
    )

    organization: Mapped[Organization] = relationship("Organization", back_populates="roles")
    users: Mapped[list["User"]] = relationship("User", back_populates="role")
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan",
    )


class Permission(Base):
    """Permission entity."""

    __tablename__ = "uuh_permission"

    permission_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permission_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    permission_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan",
    )


class RolePermission(Base):
    """Association between roles and permissions within an organization."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        sa.PrimaryKeyConstraint("role_id", "permission_id", "organization_id"),
    )

    role_id: Mapped[int] = mapped_column(ForeignKey("uuh_roles.role_id"), nullable=False)
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("uuh_permission.permission_id"), nullable=False,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organization.organization_id"), nullable=False,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )

    role: Mapped[Role] = relationship("Role", back_populates="role_permissions")
    permission: Mapped[Permission] = relationship("Permission", back_populates="role_permissions")
    organization: Mapped[Organization] = relationship(
        "Organization",
        foreign_keys=[organization_id],
    )


class User(Base):
    """Core user entity."""

    __tablename__ = "uuh_users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gender: Mapped[GenderEnum | None] = mapped_column(
        Enum(GenderEnum, name="gender_enum"), nullable=True,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organization.organization_id"), nullable=False,
    )
    role_id: Mapped[int | None] = mapped_column(ForeignKey("uuh_roles.role_id"), nullable=True)
    profile_img_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
    )
    status: Mapped[UserStatusEnum] = mapped_column(
        Enum(UserStatusEnum, name="user_status_enum"),
        default=UserStatusEnum.ACTIVE,
        nullable=False,
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(
        "Organization",
        back_populates="users",
        foreign_keys=[organization_id],
        primaryjoin="User.organization_id == Organization.organization_id",
    )
    role: Mapped[Role | None] = relationship("Role", back_populates="users")
    contact_information: Mapped["ContactInformation | None"] = relationship(
        "ContactInformation", back_populates="user", uselist=False,
    )
    login_records: Mapped[list["UserLogin"]] = relationship(
        "UserLogin", back_populates="user", cascade="all, delete-orphan",
    )
    password_resets: Mapped[list["PasswordReset"]] = relationship(
        "PasswordReset", back_populates="user", cascade="all, delete-orphan",
    )
    archived_entries: Mapped[list["ArchivedUser"]] = relationship(
        "ArchivedUser", back_populates="user", cascade="all, delete-orphan",
    )
    sso_accounts: Mapped[list["SsoProvider"]] = relationship(
        "SsoProvider", back_populates="user", cascade="all, delete-orphan",
    )
    support_tickets: Mapped[list["SupportTicket"]] = relationship(
        "SupportTicket", back_populates="user",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user")
    login_activity: Mapped[list["UserLoginActivity"]] = relationship(
        "UserLoginActivity", back_populates="user",
    )
    activity_logs: Mapped[list["UserActivityLog"]] = relationship(
        "UserActivityLog", back_populates="user",
    )
    security_alerts: Mapped[list["SecurityAlert"]] = relationship(
        "SecurityAlert", back_populates="user",
    )


class ContactInformation(Base):
    """User contact details."""

    __tablename__ = "uuh_contact_information"

    address_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=False, unique=True)
    email_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verified_phone_number: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    emergency_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    street_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="contact_information")


class UserLogin(Base):
    """Maps users to login identifiers (e.g., username history)."""

    __tablename__ = "uuh_user_login"

    login_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    refresh_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="login_records")


class PasswordReset(Base):
    """Password reset tokens."""

    __tablename__ = "uuh_password_reset"

    reset_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=False)
    reset_token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_used: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="password_resets")


class ArchivedUser(Base):
    """Archive snapshot for users."""

    __tablename__ = "archived_uuh_users"

    archived_user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organization.organization_id"), nullable=False,
    )
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now())

    user: Mapped[User] = relationship("User", back_populates="archived_entries")
    organization: Mapped[Organization] = relationship("Organization")


class Subscription(Base):
    """Organization subscriptions."""

    __tablename__ = "subscriptions"

    subscription_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organization.organization_id"), nullable=False,
    )
    subscription_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    subscription_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    plan_type: Mapped[PlanTypeEnum] = mapped_column(
        Enum(PlanTypeEnum, name="plan_type_enum"), nullable=False,
    )
    payment_status: Mapped[PaymentStatusEnum] = mapped_column(
        Enum(PaymentStatusEnum, name="payment_status_enum"), nullable=False,
    )

    organization: Mapped[Organization] = relationship("Organization", back_populates="subscriptions")


class BillingPlan(Base):
    """Billing plan catalog."""

    __tablename__ = "billing_plans"

    plan_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    plan_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    billing_cycle: Mapped[BillingCycleEnum] = mapped_column(
        Enum(BillingCycleEnum, name="billing_cycle_enum"), nullable=False,
    )
    max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_storage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    support_level: Mapped[SupportLevelEnum | None] = mapped_column(
        Enum(SupportLevelEnum, name="support_level_enum"), nullable=True,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
    )

    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="plan")
    subscription_history: Mapped[list["SubscriptionHistory"]] = relationship(
        "SubscriptionHistory", back_populates="plan",
    )


class Invoice(Base):
    """Invoices generated for organizations."""

    __tablename__ = "invoices"

    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.organization_id"), nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("billing_plans.plan_id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    billing_cycle: Mapped[BillingCycleEnum] = mapped_column(
        Enum(BillingCycleEnum, name="invoice_billing_cycle_enum"), nullable=False,
    )
    invoice_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[InvoiceStatusEnum] = mapped_column(
        Enum(InvoiceStatusEnum, name="invoice_status_enum"), nullable=False,
    )
    payment_method: Mapped[PaymentMethodEnum | None] = mapped_column(
        Enum(PaymentMethodEnum, name="payment_method_enum"), nullable=True,
    )
    payment_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
    )

    organization: Mapped[Organization] = relationship("Organization", back_populates="invoices")
    plan: Mapped[BillingPlan] = relationship("BillingPlan", back_populates="invoices")


class UsageMetric(Base):
    """Tracks organization usage metrics."""

    __tablename__ = "usage_metrics"

    metric_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.organization_id"), nullable=False)
    metric_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )

    organization: Mapped[Organization] = relationship("Organization", back_populates="usage_metrics")


class SubscriptionHistory(Base):
    """Historical subscription records."""

    __tablename__ = "subscription_history"

    subscription_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.organization_id"), nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("billing_plans.plan_id"), nullable=False)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SubscriptionHistoryStatusEnum] = mapped_column(
        Enum(SubscriptionHistoryStatusEnum, name="subscription_history_status_enum"),
        nullable=False,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
    )

    organization: Mapped[Organization] = relationship("Organization")
    plan: Mapped[BillingPlan] = relationship("BillingPlan", back_populates="subscription_history")


# endregion ---------------------------------------------------------------------------


# region: Support and monitoring ------------------------------------------------------


class SupportTicket(Base):
    """Support ticket raised by a user."""

    __tablename__ = "support_tickets"

    ticket_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[SupportPriorityEnum] = mapped_column(
        Enum(SupportPriorityEnum, name="support_priority_enum"), nullable=False,
    )
    status: Mapped[TicketStatusEnum] = mapped_column(
        Enum(TicketStatusEnum, name="ticket_status_enum"), nullable=False,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="support_tickets")
    comments: Mapped[list["SupportTicketComment"]] = relationship(
        "SupportTicketComment",
        back_populates="ticket",
        cascade="all, delete-orphan",
    )


class SupportTicketComment(Base):
    """Comment on a support ticket."""

    __tablename__ = "support_ticket_comments"

    comment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.ticket_id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )

    ticket: Mapped[SupportTicket] = relationship("SupportTicket", back_populates="comments")
    user: Mapped[User] = relationship("User")


class SystemHealthLog(Base):
    """Operational metrics for an organization."""

    __tablename__ = "system_health_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organization.organization_id"), nullable=False,
    )
    server_uptime: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    active_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_usage: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    cpu_usage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    memory_usage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    log_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship("Organization", back_populates="system_health_logs")


class SystemAlert(Base):
    """System level alerts."""

    __tablename__ = "system_alerts"

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organization.organization_id"), nullable=False,
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    alert_message: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    alert_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship("Organization", back_populates="system_alerts")


class AuditLog(Base):
    """Audit trail for user actions."""

    __tablename__ = "audit_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_table: Mapped[str | None] = mapped_column(String(100), nullable=True)
    affected_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_data: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    new_data: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    action_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="audit_logs")


class UserLoginActivity(Base):
    """Detailed login activity for users."""

    __tablename__ = "user_login_activity"

    login_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=False)
    login_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    login_ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
    login_success: Mapped[bool] = mapped_column(sa.Boolean, default=True, nullable=False)
    failed_attempt_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    login_method: Mapped[LoginMethodEnum] = mapped_column(
        Enum(LoginMethodEnum, name="login_method_enum"), nullable=False,
    )
    login_location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="login_activity")


class UserActivityLog(Base):
    """Log of high-level user activity."""

    __tablename__ = "user_activity_logs"

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    activity_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    activity_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="activity_logs")


class SecurityAlert(Base):
    """Security alerts triggered for a user."""

    __tablename__ = "security_alerts"

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    alert_message: Mapped[str] = mapped_column(Text, nullable=False)
    alert_status: Mapped[AlertStatusEnum] = mapped_column(
        Enum(AlertStatusEnum, name="security_alert_status_enum"), nullable=False,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="security_alerts")


class SsoProvider(Base):
    """Stores SSO mappings for users."""

    __tablename__ = "sso_providers"

    provider_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("uuh_users.user_id"), nullable=False)
    provider_name: Mapped[SsoProviderName] = mapped_column(
        Enum(SsoProviderName, name="sso_provider_name_enum"), nullable=False,
    )
    provider_uid: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="sso_accounts")


# endregion ---------------------------------------------------------------------------
