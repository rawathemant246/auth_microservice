import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.settings import settings


def _bootstrap_headers(secret: str) -> dict[str, str]:
    return {"X-Bootstrap-Secret": secret}


@pytest.fixture
def bootstrap_secret() -> str:
    original = settings.bootstrap_secret
    secret = "feedback-bootstrap-secret"
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
        "organization_name": "Feedback Academy",
        "admin_user": {
            "first_name": "Fiona",
            "last_name": "Feedback",
            "username": "fiona.feedback",
            "password": "FeedbackPass123!",
            "contact_information": {"email": "fiona.feedback@example.com"},
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
async def test_feedback_flow(
    client: AsyncClient,
    fastapi_app: FastAPI,
    dbsession: AsyncSession,
    bootstrap_secret: str,
) -> None:
    organization_id, headers = await _bootstrap_and_login(client, fastapi_app, bootstrap_secret)

    create_url = fastapi_app.url_path_for("create_feedback")
    feedback_payload = {
        "organization_id": organization_id,
        "content": "The app is fantastic",
        "category": "praise",
    }
    create_response = await client.post(create_url, json=feedback_payload, headers=headers)
    assert create_response.status_code == 201
    feedback = create_response.json()
    feedback_id = feedback["feedback_id"]

    list_url = fastapi_app.url_path_for("list_feedback")
    list_response = await client.get(
        list_url,
        params={"organization_id": organization_id},
        headers=headers,
    )
    assert list_response.status_code == 200
    assert any(item["feedback_id"] == feedback_id for item in list_response.json()["items"])

    update_url = fastapi_app.url_path_for("update_feedback", feedback_id=feedback_id)
    update_response = await client.patch(
        update_url,
        json={"status": "in_review"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "in_review"
