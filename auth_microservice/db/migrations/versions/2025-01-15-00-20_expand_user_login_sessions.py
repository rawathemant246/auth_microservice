"""Expand user login table to store session metadata.

Revision ID: c7f3b8246470
Revises: b4c0d8d95a7f
Create Date: 2025-01-15 00:20:00

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "c7f3b8246470"
down_revision = "b4c0d8d95a7f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE uuh_user_login RESTART IDENTITY CASCADE")

    op.add_column(
        "uuh_user_login",
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "uuh_user_login",
        sa.Column("refresh_token_hash", sa.String(length=255), nullable=False),
    )
    op.add_column(
        "uuh_user_login",
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "uuh_user_login",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "uuh_user_login",
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "uuh_user_login",
        sa.Column("ip_address", sa.String(length=45), nullable=True),
    )
    op.add_column(
        "uuh_user_login",
        sa.Column("user_agent", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("uuh_user_login", "user_agent")
    op.drop_column("uuh_user_login", "ip_address")
    op.drop_column("uuh_user_login", "last_refreshed_at")
    op.drop_column("uuh_user_login", "revoked_at")
    op.drop_column("uuh_user_login", "refresh_token_expires_at")
    op.drop_column("uuh_user_login", "refresh_token_hash")
    op.drop_column("uuh_user_login", "issued_at")
