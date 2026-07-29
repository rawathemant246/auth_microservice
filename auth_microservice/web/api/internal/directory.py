"""Internal endpoint exposing display names to lms-backend.

lms-backend stores no names. `student_profiles` carries an `auth_user_id` and no
`first_name`; `school_profiles` carries a board and an address and no school name.
So every document it renders for a human — report cards today, class lists and
transfer certificates later — has to resolve names here.

Read-only and bulk by design. A report card run for a 3000-student school would be
3000 round trips one at a time; this lets the caller resolve a whole section in one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import Organization, User
from auth_microservice.web.api.internal.permissions import require_internal_secret
from auth_microservice.web.api.internal.schemas import DirectoryResponse, DirectoryUser

router = APIRouter(prefix="/internal/v1", tags=["internal"])

#: Matches the bulk-create ceiling, and the LMS's own per-import row limit. A
#: caller with more users than this is rendering a whole school and should page.
MAX_DIRECTORY_USERS = 500


@router.get(
    "/orgs/{organization_id}/directory",
    response_model=DirectoryResponse,
    dependencies=[Depends(require_internal_secret)],
)
async def get_directory(
    organization_id: int,
    user_ids: list[int] = Query(default=[]),
    session: AsyncSession = Depends(get_db_session),
) -> DirectoryResponse:
    """Return the organization's name, and the named users that belong to it.

    Users are filtered by `organization_id` as well as by id, so a caller cannot
    read a name out of another school by guessing a user id. Ids that do not exist,
    or belong elsewhere, are simply absent from the response rather than raising:
    a report card run should not fail wholesale because one student's account was
    removed, and the caller can see which ids came back.
    """
    if len(user_ids) > MAX_DIRECTORY_USERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"at most {MAX_DIRECTORY_USERS} user_ids per request",
        )

    org = await session.scalar(
        select(Organization).where(Organization.organization_id == organization_id),
    )
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="organization_not_found",
        )

    users: list[DirectoryUser] = []
    if user_ids:
        rows = await session.scalars(
            select(User).where(
                User.organization_id == organization_id,
                User.user_id.in_(user_ids),
            ),
        )
        users = [
            DirectoryUser(
                user_id=u.user_id,
                first_name=u.first_name,
                last_name=u.last_name,
                username=u.username,
            )
            for u in rows
        ]

    return DirectoryResponse(
        organization_id=org.organization_id,
        organization_name=org.organization_name,
        users=users,
    )
