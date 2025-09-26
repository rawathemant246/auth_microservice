"""Domain services for user registration, login, and SSO handling."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.core.security import create_access_token, hash_password, verify_password
from auth_microservice.observability import ACTIVE_SESSIONS_GAUGE
from auth_microservice.db.models.oltp import (
    ContactInformation,
    LoginMethodEnum,
    PasswordReset,
    SsoProvider,
    SsoProviderName,
    User,
    UserLogin,
    UserLoginActivity,
    UserStatusEnum,
)
from auth_microservice.settings import settings
from redis.asyncio import Redis


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
        await self._session.refresh(user)
        return user

    async def authenticate_user(
        self,
        username: str,
        password: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str]:
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
        if user.status != UserStatusEnum.ACTIVE:
            raise ValueError("account_inactive")

        user.last_login = datetime.now(timezone.utc)
        activity = UserLoginActivity(
            user_id=user.user_id,
            login_timestamp=user.last_login,
            login_method=LoginMethodEnum.STANDARD,
            login_success=True,
            login_ip_address=ip_address,
            device_info=user_agent[:255] if user_agent else None,
        )
        self._session.add(activity)
        await self._session.flush()
        return user, email

    async def issue_token(
        self,
        user: User,
        email: str | None = None,
        *,
        session_id: int | None = None,
    ) -> tuple[str, int]:
        """Issue JWT access token for user."""

        expires = settings.jwt_access_token_expires_minutes
        claims: dict[str, Any] = {
            "username": user.username,
            "organization_id": user.organization_id,
            "role_id": user.role_id,
        }
        if email:
            claims["email"] = email
        if session_id is not None:
            claims["session_id"] = session_id
        token = create_access_token(
            subject=str(user.user_id),
            expires_minutes=expires,
            claims=claims,
        )
        return token, expires

    async def create_session(
        self,
        user: User,
        email: str | None,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Create a login session with refresh/access tokens."""

        now = datetime.now(timezone.utc)
        refresh_ttl = timedelta(minutes=settings.jwt_refresh_token_expires_minutes)
        refresh_expires = now + refresh_ttl
        refresh_token = secrets.token_urlsafe(48)

        session_entry = UserLogin(
            user_id=user.user_id,
            refresh_token_hash=hash_password(refresh_token),
            refresh_token_expires_at=refresh_expires,
            issued_at=now,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
        )
        self._session.add(session_entry)
        await self._session.flush()
        ACTIVE_SESSIONS_GAUGE.labels(organization_id=str(user.organization_id)).inc()

        access_token, expires_minutes = await self.issue_token(
            user,
            email,
            session_id=session_entry.login_id,
        )

        return {
            "session": session_entry,
            "access_token": access_token,
            "access_token_expires_minutes": expires_minutes,
            "refresh_token": refresh_token,
            "refresh_token_expires_at": refresh_expires,
        }

    async def get_session(self, session_id: int) -> UserLogin | None:
        """Fetch a login session by identifier."""

        return await self._session.get(UserLogin, session_id)

    async def revoke_session(self, session: UserLogin) -> None:
        """Mark a session as revoked."""

        session.revoked_at = datetime.now(timezone.utc)
        organization_id = await self._session.scalar(
            select(User.organization_id).where(User.user_id == session.user_id)
        )
        await self._session.flush()
        if organization_id is not None:
            ACTIVE_SESSIONS_GAUGE.labels(organization_id=str(organization_id)).dec()

    async def refresh_session(
        self,
        session: UserLogin,
        refresh_token: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Rotate refresh token and issue new access token."""

        if session.revoked_at is not None:
            raise ValueError("session_revoked")

        now = datetime.now(timezone.utc)
        if session.refresh_token_expires_at < now:
            raise ValueError("refresh_expired")

        if not verify_password(refresh_token, session.refresh_token_hash):
            raise ValueError("invalid_refresh_token")

        new_refresh_token = secrets.token_urlsafe(48)
        session.refresh_token_hash = hash_password(new_refresh_token)
        session.refresh_token_expires_at = now + timedelta(
            minutes=settings.jwt_refresh_token_expires_minutes
        )
        session.last_refreshed_at = now
        if ip_address:
            session.ip_address = ip_address
        if user_agent:
            session.user_agent = user_agent[:255]

        await self._session.flush()

        user = session.user
        if user is None:
            user = await self._session.get(User, session.user_id)
        if user is None:
            raise ValueError("user_not_found")

        email = await self.get_primary_email(session.user_id)
        access_token, expires_minutes = await self.issue_token(
            user,
            email,
            session_id=session.login_id,
        )

        return {
            "access_token": access_token,
            "access_token_expires_minutes": expires_minutes,
            "refresh_token": new_refresh_token,
            "refresh_token_expires_at": session.refresh_token_expires_at,
            "user": user,
            "email": email,
        }

    async def get_primary_email(self, user_id: int) -> str | None:
        """Fetch the primary email for a user if available."""

        stmt = select(ContactInformation.email_id).where(ContactInformation.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_password_reset_token(
        self,
        email: str,
        *,
        redis: Redis | None = None,
    ) -> str | None:
        """Create a password reset token for the given email if user exists."""

        stmt = (
            select(User)
            .join(ContactInformation, ContactInformation.user_id == User.user_id)
            .where(ContactInformation.email_id == email)
        )
        result = await self._session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return None

        now = datetime.now(timezone.utc)
        expires_minutes = settings.password_reset_token_expires_minutes
        expires = now + timedelta(minutes=expires_minutes)
        token = secrets.token_urlsafe(32)

        if redis is not None:
            rate_key = f"password_reset:rate:{user.user_id}"
            attempts = await redis.incr(rate_key)
            if attempts == 1:
                await redis.expire(rate_key, 3600)
            if attempts > 5:
                logger.warning("Password reset rate limited for user id=%s", user.user_id)
                return None

            user_key = f"password_reset:user:{user.user_id}"
            previous_token = await redis.get(user_key)
            if previous_token:
                token_value = previous_token.decode() if isinstance(previous_token, bytes) else str(previous_token)
                await redis.delete(f"password_reset:token:{token_value}")

            pipeline = redis.pipeline()
            pipeline.setex(
                f"password_reset:token:{token}",
                expires_minutes * 60,
                user.user_id,
            )
            pipeline.setex(user_key, expires_minutes * 60, token)
            await pipeline.execute()
            logger.info("Created password reset token for user id=%s (redis)", user.user_id)
            return token

        reset_entry = PasswordReset(
            user_id=user.user_id,
            reset_token=token,
            expires_at=expires,
            token_used=False,
        )
        self._session.add(reset_entry)
        await self._session.flush()
        logger.info("Created password reset token for user id=%s", user.user_id)
        return token

    async def reset_password(
        self,
        token: str,
        new_password: str,
        *,
        redis: Redis | None = None,
    ) -> User:
        """Reset password for token if valid."""

        if redis is not None:
            user_id_bytes = await redis.get(f"password_reset:token:{token}")
            if user_id_bytes is None:
                raise ValueError("invalid_token")
            user_id = int(user_id_bytes)
            user = await self._session.get(User, user_id)
            if user is None:
                raise ValueError("user_not_found")
            pipeline = redis.pipeline()
            pipeline.delete(f"password_reset:token:{token}")
            pipeline.delete(f"password_reset:user:{user.user_id}")
            await pipeline.execute()
        else:
            stmt = select(PasswordReset).where(PasswordReset.reset_token == token)
            result = await self._session.execute(stmt)
            reset_entry = result.scalar_one_or_none()
            if reset_entry is None:
                raise ValueError("invalid_token")
            if reset_entry.token_used:
                raise ValueError("token_used")
            now = datetime.now(timezone.utc)
            if reset_entry.expires_at < now:
                raise ValueError("token_expired")

            user = await self._session.get(User, reset_entry.user_id)
            if user is None:
                raise ValueError("user_not_found")

            reset_entry.token_used = True

        now = datetime.now(timezone.utc)
        user.password = hash_password(new_password)
        user.updated_at = now
        if redis is None:
            reset_entry.token_used = True
        await self._session.flush()
        logger.info("Password reset for user id=%s", user.user_id)
        return user

    async def unlink_sso_provider(self, user_id: int, provider: SsoProviderName) -> bool:
        """Remove an SSO provider link for a user."""

        stmt = (
            select(SsoProvider)
            .where(SsoProvider.user_id == user_id, SsoProvider.provider_name == provider)
        )
        result = await self._session.execute(stmt)
        provider_entry = result.scalar_one_or_none()
        if provider_entry is None:
            return False

        await self._session.delete(provider_entry)
        await self._session.flush()
        return True

    async def list_sso_providers(self, user_id: int) -> list[SsoProvider]:
        """List all linked SSO providers for a user."""

        stmt = select(SsoProvider).where(SsoProvider.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars())

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
        elif provider.user_id != user.user_id:
            raise ValueError("provider_already_linked")
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
