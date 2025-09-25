import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import (
    LicenseStatusEnum,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
)
from auth_microservice.services.organizations import ADMIN_PERMISSION_NAMES
from auth_microservice.settings import settings


@pytest.fixture
def bootstrap_secret() -> str:
    original = settings.bootstrap_secret
    secret = "test-bootstrap-secret"
    settings.bootstrap_secret = secret
    try:
        yield secret
    finally:
        settings.bootstrap_secret = original


@pytest.mark.anyio
async def test_bootstrap_organization(
    client: AsyncClient,
    fastapi_app: FastAPI,
    dbsession: AsyncSession,
    bootstrap_secret: str,
) -> None:
    url = fastapi_app.url_path_for("bootstrap_organization")
    payload = {
        "bootstrap_secret": bootstrap_secret,
        "organization_name": "Bootstrap Academy",
        "admin_user": {
            "first_name": "Alice",
            "last_name": "Admin",
            "username": "bootstrap_admin",
            "password": "SecretPass123!",
            "contact_information": {
                "email": "alice@example.com",
            },
        },
    }

    response = await client.post(url, json=payload)
    assert response.status_code == 201
    data = response.json()

    organization = await dbsession.get(Organization, data["organization_id"])
    assert organization is not None
    assert organization.organization_name == "Bootstrap Academy"
    assert organization.user_id == data["admin_user_id"]

    role = await dbsession.get(Role, data["admin_role_id"])
    assert role is not None
    assert role.role_name == f"org_{organization.organization_id}_admin"

    result = await dbsession.execute(
        select(Permission.permission_name)
        .join(RolePermission, Permission.permission_id == RolePermission.permission_id)
        .where(RolePermission.role_id == role.role_id)
    )
    role_permissions = set(result.scalars().all())
    assert set(ADMIN_PERMISSION_NAMES).issubset(role_permissions)


@pytest.mark.anyio
async def test_organization_admin_flow(
    client: AsyncClient,
    fastapi_app: FastAPI,
    dbsession: AsyncSession,
    bootstrap_secret: str,
) -> None:
    bootstrap_url = fastapi_app.url_path_for("bootstrap_organization")
    bootstrap_payload = {
        "bootstrap_secret": bootstrap_secret,
        "organization_name": "Launch School",
        "admin_user": {
            "first_name": "Lara",
            "last_name": "Launch",
            "username": "launch_admin",
            "password": "LaunchPass123!",
            "contact_information": {
                "email": "lara@example.com",
            },
        },
    }
    bootstrap_response = await client.post(bootstrap_url, json=bootstrap_payload)
    assert bootstrap_response.status_code == 201

    login_url = fastapi_app.url_path_for("login")
    login_response = await client.post(
        login_url,
        json={
            "username": bootstrap_payload["admin_user"]["username"],
            "password": bootstrap_payload["admin_user"]["password"],
        },
    )
    assert login_response.status_code == 200
    tokens = login_response.json()["tokens"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    create_url = fastapi_app.url_path_for("create_organization")
    create_response = await client.post(
        create_url,
        json={"organization_name": "Second Campus"},
        headers=headers,
    )
    assert create_response.status_code == 201
    created = create_response.json()
    organization_id = created["organization_id"]
    assert created["organization_name"] == "Second Campus"

    admin_url = fastapi_app.url_path_for("create_org_admin", organization_id=str(organization_id))
    admin_response = await client.post(
        admin_url,
        json={
            "first_name": "Sam",
            "last_name": "Secondary",
            "username": "second_admin",
            "password": "AdminPass123!",
            "contact_information": {
                "email": "sam.secondary@example.com",
            },
        },
        headers=headers,
    )
    assert admin_response.status_code == 201
    admin_data = admin_response.json()
    assert admin_data["organization_id"] == organization_id

    update_url = fastapi_app.url_path_for(
        "update_organization",
        organization_id=str(organization_id),
    )
    update_response = await client.patch(
        update_url,
        json={"organization_name": "Second Campus Updated"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["organization_name"] == "Second Campus Updated"

    list_url = fastapi_app.url_path_for("list_organizations")
    list_response = await client.get(list_url, headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) >= 2

    deactivate_url = fastapi_app.url_path_for(
        "deactivate_organization",
        organization_id=str(organization_id),
    )
    deactivate_response = await client.delete(deactivate_url, headers=headers)
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["license_status"] == LicenseStatusEnum.SUSPENDED.value

    new_admin_user = await dbsession.scalar(
        select(User).where(User.username == "second_admin")
    )
    assert new_admin_user is not None
    assert new_admin_user.organization_id == organization_id
@pytest.mark.anyio
async def test_settings_and_privacy_flow(
    client: AsyncClient,
    fastapi_app: FastAPI,
    bootstrap_secret: str,
) -> None:
    bootstrap_url = fastapi_app.url_path_for("bootstrap_organization")
    payload = {
        "bootstrap_secret": bootstrap_secret,
        "organization_name": "Settings School",
        "admin_user": {
            "first_name": "Sally",
            "last_name": "Settings",
            "username": "sally.settings",
            "password": "SettingsPass123!",
            "contact_information": {"email": "sally.settings@example.com"},
        },
    }
    response = await client.post(bootstrap_url, json=payload)
    assert response.status_code == 201
    organization_id = response.json()["organization_id"]

    login_url = fastapi_app.url_path_for("login")
    login_response = await client.post(
        login_url,
        json={"username": payload["admin_user"]["username"], "password": payload["admin_user"]["password"]},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()["tokens"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    settings_get_url = fastapi_app.url_path_for("get_organization_settings", organization_id=str(organization_id))
    settings_response = await client.get(settings_get_url, headers=headers)
    assert settings_response.status_code == 200
    assert settings_response.json()["settings"] is None

    settings_payload = {"settings": {"theme": "dark", "timezone": "UTC"}}
    settings_put_url = fastapi_app.url_path_for("upsert_organization_settings", organization_id=str(organization_id))
    settings_put_response = await client.put(settings_put_url, json=settings_payload, headers=headers)
    assert settings_put_response.status_code == 200
    assert settings_put_response.json()["settings"] == settings_payload["settings"]

    settings_response = await client.get(settings_get_url, headers=headers)
    assert settings_response.status_code == 200
    assert settings_response.json()["settings"] == settings_payload["settings"]

    privacy_get_url = fastapi_app.url_path_for("get_privacy_settings", organization_id=str(organization_id))
    privacy_response = await client.get(privacy_get_url, headers=headers)
    assert privacy_response.status_code == 200
    assert privacy_response.json()["settings"] is None

    privacy_payload = {"settings": {"share_data": False, "retention_days": 30}}
    privacy_put_url = fastapi_app.url_path_for("upsert_privacy_settings", organization_id=str(organization_id))
    privacy_put_response = await client.put(privacy_put_url, json=privacy_payload, headers=headers)
    assert privacy_put_response.status_code == 200
    assert privacy_put_response.json()["settings"] == privacy_payload["settings"]

    privacy_response = await client.get(privacy_get_url, headers=headers)
    assert privacy_response.status_code == 200
    assert privacy_response.json()["settings"] == privacy_payload["settings"]
