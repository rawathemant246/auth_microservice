"""Internal endpoint for bulk user creation (called by LMS backend)."""

from __future__ import annotations

import hmac
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.core.security import hash_password
from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import (
    ContactInformation,
    Organization,
    Role,
    User,
)
from auth_microservice.settings import settings
from auth_microservice.web.api.internal.schemas import (
    BulkUserCreateRequest,
    BulkUserCreateResponse,
    BulkUserCreatedEntry,
    BulkUserErrorEntry,
)

router = APIRouter(prefix="/internal/v1", tags=["internal"])


def _verify_internal_secret(request: Request) -> None:
    secret = request.headers.get("X-Internal-Secret")
    expected = settings.internal_api_secret
    if not expected or not secret or not hmac.compare_digest(secret, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid_internal_secret",
        )


def _generate_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%"),
    ]
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


@router.post(
    "/orgs/{organization_id}/users/bulk",
    response_model=BulkUserCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_users(
    organization_id: int,
    payload: BulkUserCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> BulkUserCreateResponse:
    _verify_internal_secret(request)

    org = await session.get(Organization, organization_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="organization_not_found",
        )

    created_users: list[BulkUserCreatedEntry] = []
    errors: list[BulkUserErrorEntry] = []

    for idx, entry in enumerate(payload.users):
        try:
            existing = await session.execute(
                select(User).where(User.username == entry.username),
            )
            if existing.scalar_one_or_none() is not None:
                errors.append(
                    BulkUserErrorEntry(
                        index=idx,
                        username=entry.username,
                        error="username_already_exists",
                    )
                )
                continue

            if entry.email:
                existing_email = await session.execute(
                    select(ContactInformation).where(
                        ContactInformation.email_id == entry.email
                    ),
                )
                if existing_email.scalar_one_or_none() is not None:
                    errors.append(
                        BulkUserErrorEntry(
                            index=idx,
                            username=entry.username,
                            error="email_already_exists",
                        )
                    )
                    continue

            role_id = None
            if entry.role_name:
                role = await session.execute(
                    select(Role).where(
                        Role.organization_id == organization_id,
                        Role.role_name == entry.role_name,
                    ),
                )
                role_obj = role.scalar_one_or_none()
                if role_obj is None:
                    role = await session.execute(
                        select(Role).where(
                            Role.organization_id == organization_id,
                            Role.role_name == f"org_{organization_id}_{entry.role_name}",
                        ),
                    )
                    role_obj = role.scalar_one_or_none()
                if role_obj:
                    role_id = role_obj.role_id

            generated_password = None
            if entry.password:
                password_plain = entry.password
            else:
                password_plain = _generate_password()
                generated_password = password_plain

            user = User(
                first_name=entry.first_name,
                last_name=entry.last_name,
                username=entry.username,
                password=hash_password(password_plain),
                organization_id=organization_id,
                role_id=role_id,
            )
            session.add(user)
            await session.flush()

            if entry.email or entry.phone_number:
                contact = ContactInformation(
                    user_id=user.user_id,
                    email_id=entry.email or f"{entry.username}@noemail.local",
                    phone_number=entry.phone_number,
                )
                session.add(contact)
                await session.flush()

            created_users.append(
                BulkUserCreatedEntry(
                    user_id=user.user_id,
                    username=entry.username,
                    generated_password=generated_password,
                )
            )

        except Exception as exc:
            errors.append(
                BulkUserErrorEntry(
                    index=idx,
                    username=entry.username,
                    error=str(exc),
                )
            )

    total = len(payload.users)
    if errors and len(errors) > total * 0.5:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "More than 50% of entries failed. Entire batch rolled back.",
                "errors": [e.model_dump() for e in errors],
            },
        )

    return BulkUserCreateResponse(
        created=len(created_users),
        failed=len(errors),
        errors=errors,
        users=created_users,
    )
