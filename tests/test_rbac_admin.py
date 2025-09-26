import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import Role, User
from auth_microservice.settings import settings


def _bootstrap_headers(secret: str) -> dict[str, str]:
    return {"X-Bootstrap-Secret": secret}


@pytest.fixture
def bootstrap_secret() -> str:
    original = settings.bootstrap_secret
    secret = "rbac-bootstrap-secret"
    settings.bootstrap_secret = secret
    try:
        yield secret
    finally:
        settings.bootstrap_secret = original


async def _bootstrap_and_login(
    client: AsyncClient,
    fastapi_app: FastAPI,
    secret: str,
) -> tuple[int, dict[str, str]]:
    bootstrap_url = fastapi_app.url_path_for("bootstrap_organization")
    payload = {
        "organization_name": "RBAC Academy",
        "admin_user": {
            "first_name": "Rhea",
            "last_name": "Root",
            "username": "rbac_admin",
            "password": "RbacAdmin123!",
            "contact_information": {
                "email": "rbac.admin@example.com",
            },
        },
    }
    response = await client.post(
        bootstrap_url,
        json=payload,
        headers=_bootstrap_headers(secret),
    )
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
    return organization_id, headers


@pytest.mark.anyio
async def test_rbac_management_flow(
    client: AsyncClient,
    fastapi_app: FastAPI,
    dbsession: AsyncSession,
    bootstrap_secret: str,
) -> None:
    organization_id, headers = await _bootstrap_and_login(client, fastapi_app, bootstrap_secret)

    perm_create_url = fastapi_app.url_path_for("create_permission")
    perm_response = await client.post(
        perm_create_url,
        json={"permission_name": "custom.manage", "permission_description": "Custom permission"},
        headers=headers,
    )
    assert perm_response.status_code == 201
    permission_id = perm_response.json()["permission_id"]

    role_create_url = fastapi_app.url_path_for("create_role")
    role_response = await client.post(
        role_create_url,
        json={"role_name": "custom_role", "role_description": "Custom role"},
        headers=headers,
    )
    assert role_response.status_code == 201
    role_id = role_response.json()["role_id"]

    assign_perm_url = fastapi_app.url_path_for("assign_permission_to_role", role_id=str(role_id))
    assign_response = await client.post(
        assign_perm_url,
        json={"permission_id": permission_id},
        headers=headers,
    )
    assert assign_response.status_code == 204

    create_user_url = fastapi_app.url_path_for("create_user_in_organization", organization_id=str(organization_id))
    user_response = await client.post(
        create_user_url,
        json={
            "first_name": "Carl",
            "last_name": "Contributor",
            "username": "carl.contrib",
            "password": "Contributor123!",
            "contact_information": {"email": "carl.contrib@example.com"},
        },
        headers=headers,
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["user_id"]

    assign_role_url = fastapi_app.url_path_for("assign_role_to_user", user_id=str(user_id))
    assign_role_response = await client.post(
        assign_role_url,
        json={"role_id": role_id},
        headers=headers,
    )
    assert assign_role_response.status_code == 204

    effective_url = fastapi_app.url_path_for("get_effective_permissions", user_id=str(user_id))
    effective_response = await client.get(effective_url, headers=headers)
    assert effective_response.status_code == 200
    assert "custom.manage" in effective_response.json()["permissions"]

    revoke_role_url = fastapi_app.url_path_for("revoke_role_from_user", user_id=str(user_id), role_id=str(role_id))
    revoke_role_response = await client.delete(revoke_role_url, headers=headers)
    assert revoke_role_response.status_code == 204

    user_record = await dbsession.get(User, user_id)
    assert user_record is not None
    assert user_record.role_id is None

    revoke_perm_url = fastapi_app.url_path_for("revoke_permission_from_role", role_id=str(role_id), permission_id=str(permission_id))
    revoke_perm_response = await client.delete(revoke_perm_url, headers=headers)
    assert revoke_perm_response.status_code == 204

    delete_role_url = fastapi_app.url_path_for("delete_role", role_id=str(role_id))
    delete_role_response = await client.delete(delete_role_url, headers=headers)
    assert delete_role_response.status_code == 204

    role_record = await dbsession.scalar(select(Role).where(Role.role_id == role_id))
    assert role_record is None
