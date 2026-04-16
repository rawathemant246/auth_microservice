"""Platform admin stats endpoints (overview, revenue, growth)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import Organization, User, UserLoginActivity
from auth_microservice.settings import settings

router = APIRouter(tags=["admin-stats"])


def _verify_secret(request: Request) -> None:
    secret = request.headers.get("X-Internal-Secret")
    expected = settings.internal_api_secret
    if not expected or not secret or not secrets.compare_digest(secret, expected):
        raise HTTPException(status_code=403, detail="invalid_internal_secret")


@router.get("/admin/stats/overview")
async def platform_overview(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _verify_secret(request)

    total_orgs = await session.scalar(select(func.count()).select_from(Organization))
    total_users = await session.scalar(select(func.count()).select_from(User))

    yesterday = datetime.now(timezone.utc) - timedelta(hours=24)
    active_today = await session.scalar(
        select(func.count(func.distinct(UserLoginActivity.user_id)))
        .where(UserLoginActivity.login_timestamp > yesterday)
        .where(UserLoginActivity.login_success == True)  # noqa: E712
    )

    return {
        "total_organizations": total_orgs or 0,
        "total_users": total_users or 0,
        "active_users_today": active_today or 0,
    }


@router.get("/admin/stats/revenue")
async def revenue_stats(
    request: Request,
    months: int = Query(default=12),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _verify_secret(request)

    from_date = datetime.now(timezone.utc) - timedelta(days=months * 30)

    result = await session.execute(
        text("""
            SELECT
                date_trunc('month', payment_date) as month,
                COALESCE(SUM(amount), 0) as revenue
            FROM invoices
            WHERE payment_date > :from_date AND status = 'paid'
            GROUP BY month
            ORDER BY month
        """),
        {"from_date": from_date},
    )

    monthly = [{"month": str(row.month), "revenue": float(row.revenue)} for row in result]

    mrr = monthly[-1]["revenue"] if monthly else 0

    return {
        "mrr": mrr,
        "arr": mrr * 12,
        "monthly": monthly,
    }


@router.get("/admin/stats/growth")
async def growth_stats(
    request: Request,
    months: int = Query(default=12),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _verify_secret(request)

    from_date = datetime.now(timezone.utc) - timedelta(days=months * 30)

    result = await session.execute(
        text("""
            SELECT
                date_trunc('month', created_at) as month,
                COUNT(*) as new_schools
            FROM organization
            WHERE created_at > :from_date
            GROUP BY month
            ORDER BY month
        """),
        {"from_date": from_date},
    )

    monthly = [{"month": str(row.month), "new_schools": row.new_schools} for row in result]

    return {"monthly": monthly}
