import sqlalchemy as sa
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from auth_microservice.cli import _create_superuser
from auth_microservice.db.models.oltp import Organization, Role, User
from auth_microservice.settings import settings


def _bootstrap_headers(secret: str) -> dict[str, str]:
    return {"X-Bootstrap-Secret": secret}


async def _reset_bootstrap_state(engine: AsyncEngine) -> None:
    truncate_stmt = sa.text(
        "TRUNCATE TABLE "
        "role_permissions, user_login_activity, user_activity_logs, security_alerts, "
        "uuh_password_reset, uuh_user_login, uuh_contact_information, uuh_users, "
        "uuh_roles, uuh_permission, organization RESTART IDENTITY CASCADE"
    )
    async with engine.begin() as conn:
        await conn.execute(truncate_stmt)


@pytest.fixture
def bootstrap_secret() -> str:
    original = settings.bootstrap_secret
    secret = "bootstrap-root-secret"
    settings.bootstrap_secret = secret
    try:
        yield secret
    finally:
        settings.bootstrap_secret = original


@pytest.mark.anyio
async def test_bootstrap_endpoint_creates_root_when_empty(
    client: AsyncClient,
    fastapi_app: FastAPI,
    bootstrap_secret: str,
    _engine: AsyncEngine,
) -> None:
    await _reset_bootstrap_state(_engine)

    bootstrap_url = fastapi_app.url_path_for("bootstrap_organization")
    payload = {
        "organization_name": "ShouldBeIgnored",
        "admin_user": {
            "first_name": "Root",
            "last_name": "Admin",
            "username": "root.bootstrap",
            "password": "RootBootstrap123!",
            "contact_information": {"email": "root.bootstrap@example.com"},
        },
    }
    response = await client.post(
        bootstrap_url,
        json=payload,
        headers=_bootstrap_headers(bootstrap_secret),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["organization_name"] == "RootOrg"

    session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with session_factory() as session:
        organization = await session.get(Organization, body["organization_id"])
        assert organization is not None
        assert organization.organization_name == "RootOrg"

        role = await session.get(Role, body["admin_role_id"])
        assert role is not None
        assert role.role_name == "super_admin"

        user = await session.get(User, body["admin_user_id"])
        assert user is not None
        assert user.organization_id == organization.organization_id
        assert user.role_id == role.role_id


@pytest.mark.anyio
async def test_cli_creates_superuser_when_empty(
    _engine: AsyncEngine,
) -> None:
    await _reset_bootstrap_state(_engine)

    payload = {
        "username": "cli.super",
        "password": "CliSuper123!",
        "first_name": "Cli",
        "last_name": "Admin",
        "contact_information": {"email": "cli.super@example.com"},
    }
    created, user_id, role_id, organization_id = await _create_superuser(payload)
    assert created is True
    assert user_id > 0
    assert role_id > 0
    assert organization_id > 0

    session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert user.role_id == role_id
        assert user.organization_id == organization_id

    created_again, *_ = await _create_superuser(payload)
    assert created_again is False
