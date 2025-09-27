import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.core.security import verify_password
from auth_microservice.db.models.oltp import User
from auth_microservice.services.auth.service import AuthService

RESET_EMAIL = "platform_root@example.com"


@pytest.mark.anyio
async def test_password_reset_tokens_stored_in_redis(
    dbsession: AsyncSession,
    fake_redis_pool,
) -> None:
    redis = Redis(connection_pool=fake_redis_pool)
    await redis.flushdb()

    auth_service = AuthService(dbsession)
    token = await auth_service.create_password_reset_token(RESET_EMAIL, redis=redis)
    assert token is not None

    stored_user_id = await redis.get(f"password_reset:token:{token}")
    assert stored_user_id is not None
    user_id = int(stored_user_id)
    assert user_id > 0

    current_token = await redis.get(f"password_reset:user:{user_id}")
    assert current_token is not None
    assert current_token.decode() == token

    ttl = await redis.ttl(f"password_reset:token:{token}")
    assert ttl is not None and ttl > 0

    await auth_service.reset_password(token, "NewPass123!", redis=redis)

    assert await redis.get(f"password_reset:token:{token}") is None
    assert await redis.get(f"password_reset:user:{user_id}") is None

    user_record = await dbsession.get(User, user_id)
    assert user_record is not None
    assert verify_password("NewPass123!", user_record.password)

    await redis.flushdb()


@pytest.mark.anyio
async def test_password_reset_rate_limiting(
    dbsession: AsyncSession,
    fake_redis_pool,
) -> None:
    redis = Redis(connection_pool=fake_redis_pool)
    await redis.flushdb()

    auth_service = AuthService(dbsession)
    tokens: list[str | None] = []
    for _ in range(5):
        tokens.append(await auth_service.create_password_reset_token(RESET_EMAIL, redis=redis))

    assert all(token is not None for token in tokens)
    assert await auth_service.create_password_reset_token(RESET_EMAIL, redis=redis) is None

    latest_token = tokens[-1]
    assert latest_token is not None
    previous_token = tokens[-2]
    assert previous_token is not None
    assert await redis.get(f"password_reset:token:{previous_token}") is None
    assert await redis.get(f"password_reset:token:{latest_token}") is not None

    await redis.flushdb()
