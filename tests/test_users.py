import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import ArchivedUser, User, UserStatusEnum
from auth_microservice.settings import settings


def _bootstrap_headers(secret: str) -> dict[str, str]:
    return {"X-Bootstrap-Secret": secret}


@pytest.fixture
def bootstrap_secret() -> str:
    original = settings.bootstrap_secret
    secret = "users-bootstrap-secret"
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
        "organization_name": "Users Academy",
        "admin_user": {
            "first_name": "Uma",
            "last_name": "Admin",
            "username": "uma_admin",
            "password": "UsersPass123!",
            "contact_information": {
                "email": "uma.admin@example.com",
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
async def test_user_management_flow(
    client: AsyncClient,
    fastapi_app: FastAPI,
    dbsession: AsyncSession,
    bootstrap_secret: str,
) -> None:
    organization_id, headers = await _bootstrap_and_login(client, fastapi_app, bootstrap_secret)

    create_url = fastapi_app.url_path_for("create_user_in_organization", organization_id=str(organization_id))
    create_payload = {
        "first_name": "Victor",
        "last_name": "Visitor",
        "username": "victor.visitor",
        "password": "VisitorPass123!",
        "contact_information": {
            "email": "victor.visitor@example.com",
        },
    }
    create_response = await client.post(create_url, json=create_payload, headers=headers)
    assert create_response.status_code == 201
    user_data = create_response.json()
    user_id = user_data["user_id"]
    assert user_data["organization_id"] == organization_id

    list_url = fastapi_app.url_path_for("list_users_in_organization", organization_id=str(organization_id))
    list_response = await client.get(list_url, headers=headers)
    assert list_response.status_code == 200
    users = list_response.json()["items"]
    assert any(item["user_id"] == user_id for item in users)

    detail_url = fastapi_app.url_path_for("get_user", user_id=str(user_id))
    detail_response = await client.get(detail_url, headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["username"] == create_payload["username"]

    update_url = fastapi_app.url_path_for("update_user", user_id=str(user_id))
    update_response = await client.patch(
        update_url,
        json={"last_name": "Member", "status": UserStatusEnum.INACTIVE.value},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["last_name"] == "Member"
    assert update_response.json()["status"] == UserStatusEnum.INACTIVE.value

    contact_get_url = fastapi_app.url_path_for("get_user_contact", user_id=str(user_id))
    contact_response = await client.get(contact_get_url, headers=headers)
    assert contact_response.status_code == 200
    assert contact_response.json()["email"] == create_payload["contact_information"]["email"]

    contact_update_url = fastapi_app.url_path_for("update_user_contact", user_id=str(user_id))
    new_email = "victor.member@example.com"
    contact_update_response = await client.patch(
        contact_update_url,
        json={"email": new_email, "phone_number": "+123456789"},
        headers=headers,
    )
    assert contact_update_response.status_code == 200
    assert contact_update_response.json()["email"] == new_email
    assert contact_update_response.json()["phone_number"] == "+123456789"

    delete_url = fastapi_app.url_path_for("deactivate_user", user_id=str(user_id))
    delete_response = await client.delete(delete_url, headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == UserStatusEnum.INACTIVE.value

    archived = await dbsession.scalar(
        select(ArchivedUser).where(ArchivedUser.user_id == user_id),
    )
    assert archived is not None

    user_record = await dbsession.get(User, user_id)
    assert user_record is not None
    assert user_record.status == UserStatusEnum.INACTIVE
