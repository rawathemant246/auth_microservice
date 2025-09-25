import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import AuditLog, SupportPriorityEnum
from auth_microservice.settings import settings


@pytest.fixture
def bootstrap_secret() -> str:
    original = settings.bootstrap_secret
    secret = "search-bootstrap-secret"
    settings.bootstrap_secret = secret
    try:
        yield secret
    finally:
        settings.bootstrap_secret = original


async def _bootstrap_and_login(
    client: AsyncClient,
    fastapi_app: FastAPI,
    secret: str,
) -> tuple[int, int, dict[str, str]]:
    bootstrap_url = fastapi_app.url_path_for("bootstrap_organization")
    payload = {
        "bootstrap_secret": secret,
        "organization_name": "Search Academy",
        "admin_user": {
            "first_name": "Sid",
            "last_name": "Search",
            "username": "sid.search",
            "password": "SearchPass123!",
            "contact_information": {"email": "sid.search@example.com"},
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
    body = login_response.json()
    tokens = body["tokens"]
    user_id = body["user"]["user_id"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    return organization_id, user_id, headers


@pytest.mark.anyio
async def test_search_across_resources(
    client: AsyncClient,
    fastapi_app: FastAPI,
    dbsession: AsyncSession,
    bootstrap_secret: str,
) -> None:
    organization_id, user_id, headers = await _bootstrap_and_login(client, fastapi_app, bootstrap_secret)

    create_ticket_url = fastapi_app.url_path_for("create_ticket")
    await client.post(
        create_ticket_url,
        json={
            "subject": "Search latency issue",
            "description": "Search results are delayed",
            "priority": SupportPriorityEnum.MEDIUM.value,
        },
        headers=headers,
    )

    create_feedback_url = fastapi_app.url_path_for("create_feedback")
    await client.post(
        create_feedback_url,
        json={
            "organization_id": organization_id,
            "content": "Search feature could be faster",
            "category": "feature",
        },
        headers=headers,
    )

    audit_log = AuditLog(
        user_id=user_id,
        action_type="search_test",
        action_description="Investigated search performance",
    )
    dbsession.add(audit_log)
    await dbsession.flush()

    search_url = fastapi_app.url_path_for("search")
    response = await client.get(search_url, params={"query": "search"}, headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert any("search" in item["subject"].lower() or "search" in item["description"].lower() for item in payload["tickets"])
    assert any("search" in item["content"].lower() for item in payload["feedback"])
    assert any("search" in (item["action_description"] or "").lower() or "search" in item["action_type"].lower() for item in payload["logs"])
