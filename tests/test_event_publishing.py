import json

import pytest
from redis.asyncio import Redis

from auth_microservice.settings import settings


def _bootstrap_headers(secret: str) -> dict[str, str]:
    return {"X-Bootstrap-Secret": secret}


@pytest.fixture
def bootstrap_secret() -> str:
    original = settings.bootstrap_secret
    secret = "events-bootstrap-secret"
    settings.bootstrap_secret = secret
    try:
        yield secret
    finally:
        settings.bootstrap_secret = original


@pytest.mark.anyio
async def test_forgot_password_publishes_email_event(
    client,
    fastapi_app,
    bootstrap_secret: str,
    fake_redis_pool,
) -> None:
    bootstrap_url = fastapi_app.url_path_for("bootstrap_organization")
    payload = {
        "organization_name": "Event Org",
        "admin_user": {
            "first_name": "Ellie",
            "last_name": "Events",
            "username": "events.admin",
            "password": "EventsPass123!",
            "contact_information": {"email": "events.admin@example.com"},
        },
    }
    response = await client.post(bootstrap_url, json=payload, headers=_bootstrap_headers(bootstrap_secret))
    response.raise_for_status()
    admin_email = payload["admin_user"]["contact_information"]["email"]

    pool = fastapi_app.state.rmq_channel_pool
    async with pool.acquire() as channel:
        exchange = await channel.declare_exchange("email.events", auto_delete=False)
        queue = await channel.declare_queue("events-email-test", auto_delete=True)
        await queue.bind(exchange, "password.reset")

    redis = Redis(connection_pool=fake_redis_pool)
    await redis.flushdb()

    forgot_password_url = fastapi_app.url_path_for("forgot_password")
    forgot_response = await client.post(forgot_password_url, json={"email": admin_email})
    assert forgot_response.status_code == 200

    message = await queue.get()
    body = json.loads(message.body)
    assert body["email"] == admin_email
    assert body["token"]
    await message.ack()
    await queue.delete(if_unused=False, if_empty=False)


@pytest.mark.anyio
async def test_login_publishes_security_event(
    client,
    fastapi_app,
    bootstrap_secret: str,
) -> None:
    bootstrap_url = fastapi_app.url_path_for("bootstrap_organization")
    payload = {
        "organization_name": "Security Org",
        "admin_user": {
            "first_name": "Sam",
            "last_name": "Secure",
            "username": "secure.admin",
            "password": "SecurePass123!",
            "contact_information": {"email": "secure.admin@example.com"},
        },
    }
    response = await client.post(bootstrap_url, json=payload, headers=_bootstrap_headers(bootstrap_secret))
    response.raise_for_status()
    admin_user_id = response.json()["admin_user_id"]

    pool = fastapi_app.state.rmq_channel_pool
    async with pool.acquire() as channel:
        exchange = await channel.declare_exchange("security.events", auto_delete=False)
        queue = await channel.declare_queue("events-security-test", auto_delete=True)
        await queue.bind(exchange, "auth.login")

    login_url = fastapi_app.url_path_for("login")
    login_response = await client.post(
        login_url,
        json={
            "username": payload["admin_user"]["username"],
            "password": payload["admin_user"]["password"],
        },
    )
    assert login_response.status_code == 200

    message = await queue.get()
    body = json.loads(message.body)
    assert body["type"] == "auth.login"
    assert body["payload"]["user_id"] == admin_user_id
    assert "timestamp" in body
    await message.ack()
    await queue.delete(if_unused=False, if_empty=False)
