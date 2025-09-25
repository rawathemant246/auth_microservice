"""User management helpers for administrative endpoints."""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import (
    ArchivedUser,
    ContactInformation,
    Role,
    User,
    UserStatusEnum,
)


class UserService:
    """Encapsulates administrative operations on users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def list_users(
        self,
        organization_id: int,
        *,
        statuses: Iterable[UserStatusEnum] | None = None,
    ) -> list[tuple[User, ContactInformation | None]]:
        stmt: Select[Any] = (
            select(User, ContactInformation)
            .outerjoin(ContactInformation, ContactInformation.user_id == User.user_id)
            .where(User.organization_id == organization_id)
            .order_by(User.user_id)
        )
        if statuses:
            if isinstance(statuses, UserStatusEnum):
                statuses_list = [statuses]
            else:
                statuses_list = list(statuses)
            stmt = stmt.where(User.status.in_(statuses_list))
        result = await self._session.execute(stmt)
        return list(result.all())

    async def update_user(
        self,
        user: User,
        updates: dict[str, Any],
    ) -> User:
        allowed_fields = {
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "gender",
            "nationality",
            "status",
            "role_id",
        }
        for field, value in updates.items():
            if field not in allowed_fields:
                continue
            if field == "status" and value is not None:
                if isinstance(value, str):
                    value = UserStatusEnum(value)
                elif not isinstance(value, UserStatusEnum):
                    raise ValueError("invalid_status")
            setattr(user, field, value)

        if user.role_id is not None:
            await self.ensure_role_in_organization(user.organization_id, user.role_id)

        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def deactivate_user(self, user: User) -> User:
        user.status = UserStatusEnum.INACTIVE
        archive_entry = ArchivedUser(
            user_id=user.user_id,
            organization_id=user.organization_id,
        )
        self._session.add(archive_entry)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def get_contact_information(self, user_id: int) -> ContactInformation | None:
        stmt = select(ContactInformation).where(ContactInformation.user_id == user_id)
        return await self._session.scalar(stmt)

    async def upsert_contact_information(
        self,
        user: User,
        payload: dict[str, Any],
    ) -> ContactInformation:
        contact = await self.get_contact_information(user.user_id)

        email_provided = "email" in payload
        email = payload.get("email")

        if email_provided and email is None:
            raise ValueError("email_required")

        if email is not None:
            await self._ensure_unique_email(email, exclude_user_id=user.user_id)

        if contact is None:
            if email is None:
                raise ValueError("email_required")
            contact = ContactInformation(user_id=user.user_id, email_id=email)
            self._session.add(contact)
        for field, value in payload.items():
            if field == "email" and value is not None:
                contact.email_id = value
            elif field != "email" and hasattr(contact, field):
                setattr(contact, field, value)

        await self._session.flush()
        await self._session.refresh(contact)
        return contact

    async def ensure_role_in_organization(self, organization_id: int, role_id: int) -> None:
        exists = await self._session.scalar(
            select(func.count()).select_from(Role).where(
                Role.role_id == role_id,
                Role.organization_id == organization_id,
            )
        )
        if not exists:
            raise ValueError("role_not_in_organization")

    async def _ensure_unique_email(self, email: str, *, exclude_user_id: int) -> None:
        stmt = (
            select(func.count())
            .select_from(ContactInformation)
            .where(ContactInformation.email_id == email)
            .where(ContactInformation.user_id != exclude_user_id)
        )
        exists = await self._session.scalar(stmt)
        if exists:
            raise ValueError("email_already_exists")
