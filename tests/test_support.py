import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import SupportPriorityEnum, TicketStatusEnum
from auth_microservice.settings import settings


@pytest.fixture
def bootstrap_secret() -> str:
    original = settings.bootstrap_secret
    secret = "support-bootstrap-secret"
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
        "bootstrap_secret": secret,
        "organization_name": "Support Academy",
        "admin_user": {
            "first_name": "Sue",
            "last_name": "Support",
            "username": "sue.support",
            "password": "SupportPass123!",
            "contact_information": {"email": "sue.support@example.com"},
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
    return organization_id, headers


@pytest.mark.anyio
async def test_support_ticket_flow(
    client: AsyncClient,
    fastapi_app: FastAPI,
    dbsession: AsyncSession,
    bootstrap_secret: str,
) -> None:
    organization_id, headers = await _bootstrap_and_login(client, fastapi_app, bootstrap_secret)

    create_url = fastapi_app.url_path_for("create_ticket")
    payload = {
        "subject": "Cannot access dashboard",
        "description": "The dashboard returns 500",
        "priority": SupportPriorityEnum.HIGH.value,
    }
    create_response = await client.post(create_url, json=payload, headers=headers)
    assert create_response.status_code == 201
    ticket = create_response.json()
    ticket_id = ticket["ticket_id"]
    assert ticket["priority"] == SupportPriorityEnum.HIGH.value

    list_url = fastapi_app.url_path_for("list_tickets")
    list_response = await client.get(list_url, headers=headers)
    assert list_response.status_code == 200
    assert any(item["ticket_id"] == ticket_id for item in list_response.json()["items"])

    detail_url = fastapi_app.url_path_for("get_ticket", ticket_id=str(ticket_id))
    detail_response = await client.get(detail_url, headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["subject"] == payload["subject"]

    update_url = fastapi_app.url_path_for("update_ticket", ticket_id=str(ticket_id))
    update_response = await client.patch(
        update_url,
        json={"status": TicketStatusEnum.RESOLVED.value},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == TicketStatusEnum.RESOLVED.value

    comment_url = fastapi_app.url_path_for("add_comment", ticket_id=str(ticket_id))
    comment_response = await client.post(
        comment_url,
        json={"comment": "Issue acknowledged"},
        headers=headers,
    )
    assert comment_response.status_code == 201
    comment_id = comment_response.json()["comment_id"]
    assert comment_id is not None

    comments_list_url = fastapi_app.url_path_for("list_comments", ticket_id=str(ticket_id))
    comments_response = await client.get(comments_list_url, headers=headers)
    assert comments_response.status_code == 200
    comments = comments_response.json()["items"]
    assert any(comment["comment_id"] == comment_id for comment in comments)
