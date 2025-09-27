from pathlib import Path

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from auth_microservice.db.models.oltp import (
    LicenseStatusEnum,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
)
from auth_microservice.rbac.service import RbacService
from auth_microservice.core.security import hash_password


@pytest.mark.anyio
async def test_rbac_decisions_are_cached(
    dbsession: AsyncSession,
    fake_redis_pool,
) -> None:
    redis = Redis(connection_pool=fake_redis_pool)
    await redis.flushdb()

    organization = Organization(
        organization_name="CacheOrg",
        license_status=LicenseStatusEnum.ACTIVE,
    )
    dbsession.add(organization)
    await dbsession.flush()

    role = Role(
        organization_id=organization.organization_id,
        role_name="cache_role",
        role_description="Role for caching tests",
    )
    permission = Permission(
        permission_name="cache.permission",
        permission_description="Cache permission",
    )
    dbsession.add_all([role, permission])
    await dbsession.flush()

    dbsession.add(
        RolePermission(
            role_id=role.role_id,
            permission_id=permission.permission_id,
            organization_id=organization.organization_id,
        )
    )

    user = User(
        first_name="Cache",
        last_name="Tester",
        username="cache.tester",
        password=hash_password("CachePass123!"),
        organization_id=organization.organization_id,
        role_id=role.role_id,
    )
    dbsession.add(user)
    await dbsession.flush()

    session_factory = async_sessionmaker(bind=dbsession.bind, expire_on_commit=False)
    model_path = Path(__file__).resolve().parent.parent / "auth_microservice" / "rbac" / "model.conf"
    rbac_service = RbacService(session_factory, model_path, fake_redis_pool)

    await rbac_service.reload_policies()

    cache_key = f"rbac:decision:{user.user_id}:{organization.organization_id}:{permission.permission_name}:access"

    original_enforce = rbac_service.enforcer.enforce
    call_count = 0

    def tracked(*args, **kwargs):  # type: ignore[override]
        nonlocal call_count
        call_count += 1
        return original_enforce(*args, **kwargs)

    try:
        rbac_service.enforcer.enforce = tracked  # type: ignore[assignment]

        decision_1 = await rbac_service.enforce(
            user.user_id,
            permission.permission_name,
            organization.organization_id,
        )
        assert decision_1 is True
        assert call_count == 1

        cached_value = await redis.get(cache_key)
        assert cached_value == b"1"
        ttl = await redis.ttl(cache_key)
        assert ttl is not None and ttl > 0

        decision_2 = await rbac_service.enforce(
            user.user_id,
            permission.permission_name,
            organization.organization_id,
        )
        assert decision_2 is True
        assert call_count == 1  # Cached path should avoid extra enforce calls
    finally:
        rbac_service.enforcer.enforce = original_enforce  # type: ignore[assignment]

    await redis.flushdb()
