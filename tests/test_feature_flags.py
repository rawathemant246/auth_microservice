import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from auth_microservice.settings import settings


def _headers(secret: str) -> dict[str, str]:
    return {"X-Bootstrap-Secret": secret}


@pytest.fixture
def bootstrap_secret() -> str:
    original = settings.bootstrap_secret
    secret = "flags-bootstrap-secret"
    settings.bootstrap_secret = secret
    try:
        yield secret
    finally:
        settings.bootstrap_secret = original


async def _bootstrap_and_login(
    client: AsyncClient,
    app: FastAPI,
    secret: str,
) -> tuple[int, dict[str, str]]:
    bootstrap_url = app.url_path_for("bootstrap_organization")
    payload = {
        "organization_name": "Flags Academy",
        "admin_user": {
            "first_name": "Fiona",
            "last_name": "Flags",
            "username": "flags.admin",
            "password": "FlagsPass123!",
            "contact_information": {"email": "flags.admin@example.com"},
        },
    }
    response = await client.post(bootstrap_url, json=payload, headers=_headers(secret))
    response.raise_for_status()
    organization_id = response.json()["organization_id"]

    login_url = app.url_path_for("login")
    login_response = await client.post(
        login_url,
        json={"username": payload["admin_user"]["username"], "password": payload["admin_user"]["password"]},
    )
    login_response.raise_for_status()
    tokens = login_response.json()["tokens"]
    auth_headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    return organization_id, auth_headers


@pytest.mark.anyio
async def test_feature_flag_flow(
    client: AsyncClient,
    fastapi_app: FastAPI,
    bootstrap_secret: str,
) -> None:
    organization_id, headers = await _bootstrap_and_login(client, fastapi_app, bootstrap_secret)

    flags_url = fastapi_app.url_path_for("get_feature_flags", organization_id=str(organization_id))
    response = await client.get(flags_url, headers=headers)
    assert response.status_code == 200
    assert response.json()["flags"] == {}

    update_url = fastapi_app.url_path_for("update_feature_flags", organization_id=str(organization_id))
    payload = {"flags": {"new_dashboard": True, "beta_api": False}}
    update_response = await client.put(update_url, json=payload, headers=headers)
    assert update_response.status_code == 200
    assert update_response.json()["flags"] == {"new_dashboard": True, "beta_api": False}

    response = await client.get(flags_url, headers=headers)
    assert response.status_code == 200
    assert response.json()["flags"] == {"new_dashboard": True, "beta_api": False}
