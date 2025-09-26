from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import (
    AlertStatusEnum,
    AuditLog,
    LoginMethodEnum,
    SecurityAlert,
    UserActivityLog,
    UserLoginActivity,
)
from auth_microservice.settings import settings


def _bootstrap_headers(secret: str) -> dict[str, str]:
    return {"X-Bootstrap-Secret": secret}


@pytest.fixture
def bootstrap_secret() -> str:
    original = settings.bootstrap_secret
    secret = "security-bootstrap-secret"
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
        "organization_name": "Security Academy",
        "admin_user": {
            "first_name": "Sec",
            "last_name": "Admin",
            "username": "sec.admin",
            "password": "SecurePass123!",
            "contact_information": {"email": "sec.admin@example.com"},
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
    body = login_response.json()
    tokens = body["tokens"]
    user_id = body["user"]["user_id"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    return organization_id, user_id, headers


@pytest.mark.anyio
async def test_security_audit_activity_endpoints(
    client: AsyncClient,
    fastapi_app: FastAPI,
    dbsession: AsyncSession,
    bootstrap_secret: str,
) -> None:
    organization_id, user_id, headers = await _bootstrap_and_login(client, fastapi_app, bootstrap_secret)

    alert = SecurityAlert(
        user_id=user_id,
        alert_type="unusual_login",
        alert_message="Multiple failed attempts detected",
        alert_status=AlertStatusEnum.OPEN,
    )
    dbsession.add(alert)

    now = datetime.now(timezone.utc)
    audit_log = AuditLog(
        user_id=user_id,
        action_type="update_settings",
        action_description="Updated security policies",
        affected_table="security_policies",
        action_timestamp=now,
        ip_address="127.0.0.1",
    )
    dbsession.add(audit_log)

    login_activity = UserLoginActivity(
        user_id=user_id,
        login_timestamp=now,
        login_ip_address="127.0.0.1",
        device_info="pytest",
        login_success=False,
        failed_attempt_count=2,
        login_method=LoginMethodEnum.STANDARD,
        login_location="local",
    )
    dbsession.add(login_activity)

    user_activity = UserActivityLog(
        user_id=user_id,
        activity_type="policy_review",
        activity_description="Reviewed security policies",
        activity_timestamp=now,
        ip_address="127.0.0.1",
    )
    dbsession.add(user_activity)

    await dbsession.flush()

    alerts_url = fastapi_app.url_path_for("list_security_alerts")
    alerts_response = await client.get(alerts_url, headers=headers)
    assert alerts_response.status_code == 200
    alerts_payload = alerts_response.json()
    assert len(alerts_payload["items"]) == 1
    assert alerts_payload["items"][0]["alert_type"] == "unusual_login"

    alert_id = alerts_payload["items"][0]["alert_id"]
    update_url = fastapi_app.url_path_for("update_security_alert", alert_id=str(alert_id))
    update_response = await client.patch(
        update_url,
        json={"alert_status": AlertStatusEnum.RESOLVED.value},
        headers=headers,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["alert_status"] == AlertStatusEnum.RESOLVED.value
    assert updated["resolved_at"] is not None

    logs_url = fastapi_app.url_path_for("list_audit_logs")
    logs_response = await client.get(
        logs_url,
        params={"actor": user_id},
        headers=headers,
    )
    assert logs_response.status_code == 200
    logs_payload = logs_response.json()
    assert len(logs_payload["items"]) == 1
    assert logs_payload["items"][0]["affected_table"] == "security_policies"

    login_activity_url = fastapi_app.url_path_for("list_login_activity")
    login_response = await client.get(
        login_activity_url,
        params={"success": "false"},
        headers=headers,
    )
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert len(login_payload["items"]) == 1
    assert login_payload["items"][0]["login_success"] is False

    user_activity_url = fastapi_app.url_path_for("list_user_activity")
    user_activity_response = await client.get(
        user_activity_url,
        params={"activity_type": "policy_review"},
        headers=headers,
    )
    assert user_activity_response.status_code == 200
    user_activity_payload = user_activity_response.json()
    assert len(user_activity_payload["items"]) == 1
    assert user_activity_payload["items"][0]["activity_type"] == "policy_review"
