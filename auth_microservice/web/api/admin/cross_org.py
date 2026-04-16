"""Platform admin cross-org listing endpoints (invoices, tickets, users, subscriptions, usage)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import User
from auth_microservice.settings import settings

router = APIRouter(tags=["admin-cross-org"])


def _verify_secret(request: Request) -> None:
    secret = request.headers.get("X-Internal-Secret")
    expected = settings.internal_api_secret
    if not expected or not secret or not secrets.compare_digest(secret, expected):
        raise HTTPException(status_code=403, detail="invalid_internal_secret")


@router.get("/admin/invoices")
async def list_invoices(
    request: Request,
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _verify_secret(request)

    offset = (page - 1) * per_page

    where_clause = "WHERE i.status = :status" if status else ""

    result = await session.execute(
        text(f"""
            SELECT i.*, o.organization_name
            FROM invoices i
            JOIN organization o ON o.organization_id = i.org_id
            {where_clause}
            ORDER BY i.created_at DESC
            LIMIT :per_page OFFSET :offset
        """),
        {"status": status, "per_page": per_page, "offset": offset},
    )

    count_result = await session.execute(
        text(f"""
            SELECT COUNT(*) FROM invoices i
            JOIN organization o ON o.organization_id = i.org_id
            {where_clause}
        """),
        {"status": status},
    )

    items = [dict(row._mapping) for row in result]
    total = count_result.scalar() or 0

    return {"items": items, "total": total, "page": page}


@router.get("/admin/support/tickets")
async def list_support_tickets(
    request: Request,
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _verify_secret(request)

    offset = (page - 1) * per_page

    conditions = []
    if status:
        conditions.append("st.status = :status")
    if priority:
        conditions.append("st.priority = :priority")
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    result = await session.execute(
        text(f"""
            SELECT st.*, u.first_name, u.last_name, o.organization_name
            FROM support_tickets st
            JOIN uuh_users u ON u.user_id = st.user_id
            JOIN organization o ON o.organization_id = u.organization_id
            {where_clause}
            ORDER BY st.created_at DESC
            LIMIT :per_page OFFSET :offset
        """),
        {"status": status, "priority": priority, "per_page": per_page, "offset": offset},
    )

    count_result = await session.execute(
        text(f"""
            SELECT COUNT(*)
            FROM support_tickets st
            JOIN uuh_users u ON u.user_id = st.user_id
            JOIN organization o ON o.organization_id = u.organization_id
            {where_clause}
        """),
        {"status": status, "priority": priority},
    )

    items = [dict(row._mapping) for row in result]
    total = count_result.scalar() or 0

    return {"items": items, "total": total, "page": page}


@router.get("/admin/users")
async def list_users(
    request: Request,
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    org_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _verify_secret(request)

    offset = (page - 1) * per_page

    conditions = []
    if search:
        conditions.append(
            "(u.first_name ILIKE '%' || :search || '%' OR u.last_name ILIKE '%' || :search || '%')"
        )
    if role:
        conditions.append("r.role_name = :role")
    if org_id is not None:
        conditions.append("u.organization_id = :org_id")
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    params: dict = {
        "search": search,
        "role": role,
        "org_id": org_id,
        "per_page": per_page,
        "offset": offset,
    }

    result = await session.execute(
        text(f"""
            SELECT u.user_id, u.username, u.first_name, u.last_name, u.organization_id,
                   u.role_id, u.status, u.last_login, u.created_at,
                   o.organization_name, r.role_name, ci.email_id
            FROM uuh_users u
            JOIN organization o ON o.organization_id = u.organization_id
            LEFT JOIN uuh_roles r ON r.role_id = u.role_id
            LEFT JOIN uuh_contact_information ci ON ci.user_id = u.user_id
            {where_clause}
            ORDER BY u.created_at DESC
            LIMIT :per_page OFFSET :offset
        """),
        params,
    )

    count_result = await session.execute(
        text(f"""
            SELECT COUNT(*)
            FROM uuh_users u
            JOIN organization o ON o.organization_id = u.organization_id
            LEFT JOIN uuh_roles r ON r.role_id = u.role_id
            LEFT JOIN uuh_contact_information ci ON ci.user_id = u.user_id
            {where_clause}
        """),
        params,
    )

    items = [dict(row._mapping) for row in result]
    total = count_result.scalar() or 0

    return {"items": items, "total": total, "page": page}


@router.get("/admin/subscriptions")
async def list_subscriptions(
    request: Request,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _verify_secret(request)

    offset = (page - 1) * per_page

    result = await session.execute(
        text("""
            SELECT s.*, o.organization_name
            FROM subscriptions s
            JOIN organization o ON o.organization_id = s.organization_id
            ORDER BY s.subscription_start DESC
            LIMIT :per_page OFFSET :offset
        """),
        {"per_page": per_page, "offset": offset},
    )

    count_result = await session.execute(
        text("""
            SELECT COUNT(*)
            FROM subscriptions s
            JOIN organization o ON o.organization_id = s.organization_id
        """),
    )

    items = [dict(row._mapping) for row in result]
    total = count_result.scalar() or 0

    return {"items": items, "total": total, "page": page}


@router.get("/admin/orgs/{org_id}/usage")
async def org_usage(
    org_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _verify_secret(request)

    total_users = await session.scalar(
        select(func.count()).select_from(User).where(User.organization_id == org_id)
    )

    return {
        "organization_id": org_id,
        "total_users": total_users or 0,
    }
