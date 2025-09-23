"""Domain services for user registration, login, and SSO handling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.core.security import create_access_token, hash_password, verify_password
from auth_microservice.db.models.oltp import ContactInformation, LoginMethodEnum, SsoProvider, SsoProviderName, User, UserLoginActivity
from auth_microservice.settings import settings


class AuthService:
    """Encapsulates user related authentication workflows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register_user(self, payload: dict[str, Any]) -> User:
        """Register a new user using provided payload."""

        contact_payload = payload.pop("contact_information")
        username = payload["username"]

        existing_user = await self._session.execute(
            select(User).where(User.username == username)
        )
        if existing_user.scalar_one_or_none() is not None:
            raise ValueError("username_already_exists")

        existing_email = await self._session.execute(
            select(ContactInformation).where(ContactInformation.email_id == contact_payload["email"])
        )
        if existing_email.scalar_one_or_none() is not None:
            raise ValueError("email_already_exists")

        password_plain = payload.pop("password")
        user = User(**payload)
        user.password = hash_password(password_plain)
        self._session.add(user)
        await self._session.flush()

        contact = ContactInformation(
            user_id=user.user_id,
            email_id=contact_payload["email"],
            phone_number=contact_payload.get("phone_number"),
            emergency_number=contact_payload.get("emergency_number"),
            address=contact_payload.get("address"),
            street_address=contact_payload.get("street_address"),
            city=contact_payload.get("city"),
            state=contact_payload.get("state"),
            zip_code=contact_payload.get("zip_code"),
            country=contact_payload.get("country"),
            verified_phone_number=False,
        )
        self._session.add(contact)
        await self._session.flush()
        logger.info("Registered new user id=%s", user.user_id)
        return user

    async def authenticate_user(self, username: str, password: str) -> tuple[User, str]:
        """Authenticate user by username/password and return user plus primary email."""

        query = select(User, ContactInformation.email_id).join(ContactInformation, User.user_id == ContactInformation.user_id)
        query = query.where(User.username == username)
        result = await self._session.execute(query)
        row = result.first()
        if row is None:
            raise ValueError("invalid_credentials")
        user, email = row
        if not verify_password(password, user.password):
            raise ValueError("invalid_credentials")

        user.last_login = datetime.now(timezone.utc)
        activity = UserLoginActivity(
            user_id=user.user_id,
            login_timestamp=user.last_login,
            login_method=LoginMethodEnum.STANDARD,
            login_success=True,
        )
        self._session.add(activity)
        await self._session.flush()
        return user, email

    async def issue_token(self, user: User, email: str | None = None) -> tuple[str, int]:
        """Issue JWT token for user."""

        expires = settings.jwt_access_token_expires_minutes
        claims: dict[str, Any] = {
            "username": user.username,
            "organization_id": user.organization_id,
            "role_id": user.role_id,
        }
        if email:
            claims["email"] = email
        token = create_access_token(
            subject=str(user.user_id),
            expires_minutes=expires,
            claims=claims,
        )
        return token, expires

    async def upsert_sso_provider(
        self,
        user: User,
        provider_uid: str,
        email: str,
        token_payload: dict[str, Any],
    ) -> SsoProvider:
        """Create or update SSO provider entry for user."""

        stmt = select(SsoProvider).where(SsoProvider.provider_uid == provider_uid)
        result = await self._session.execute(stmt)
        provider = result.scalar_one_or_none()
        if provider is None:
            provider = SsoProvider(
                user_id=user.user_id,
                provider_name=SsoProviderName.GOOGLE,
                provider_uid=provider_uid,
                email=email,
            )
            self._session.add(provider)
        provider.access_token = token_payload.get("access_token")
        provider.refresh_token = token_payload.get("refresh_token")
        await self._session.flush()
        return provider

    async def get_or_create_user_from_sso(self, profile: dict[str, Any], organization_id: int) -> User:
        """Resolve local user for Google SSO payload."""

        provider_uid = profile.get("sub") or profile.get("id")
        if provider_uid is None:
            raise ValueError("missing_provider_uid")
        email = profile.get("email")
        if not email:
            raise ValueError("missing_email")

        existing_provider = await self._session.execute(
            select(SsoProvider).where(SsoProvider.provider_uid == provider_uid)
        )
        provider = existing_provider.scalar_one_or_none()
        if provider is not None:
            user = await self._session.get(User, provider.user_id)
            if user is None:
                raise ValueError("orphan_sso_provider")
            return user

        existing_email = await self._session.execute(
            select(ContactInformation, User)
            .join(User, ContactInformation.user_id == User.user_id)
            .where(ContactInformation.email_id == email)
        )
        row = existing_email.first()
        if row is not None:
            contact, user = row
            return user

        display_name = profile.get("name") or profile.get("displayName") or "Google User"
        first_name, _, last_name = display_name.partition(" ")
        user = User(
            first_name=first_name,
            last_name=last_name or None,
            username=email,
            password=hash_password(profile.get("sub", email)),
            organization_id=organization_id,
        )
        self._session.add(user)
        await self._session.flush()

        contact = ContactInformation(
            user_id=user.user_id,
            email_id=email,
        )
        self._session.add(contact)
        await self._session.flush()
        return user
