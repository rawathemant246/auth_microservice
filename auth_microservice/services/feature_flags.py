"""Feature flag storage backed by Redis."""

from __future__ import annotations

from typing import Any

from redis.asyncio import Redis


class FeatureFlagService:
    """Provide get/set helpers for organization-scoped feature flags."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, organization_id: int) -> str:
        return f"feature_flags:{organization_id}"

    async def get_flags(self, organization_id: int) -> dict[str, bool]:
        key = self._key(organization_id)
        raw = await self._redis.hgetall(key)
        if not raw:
            return {}
        return {
            (k.decode() if isinstance(k, bytes) else str(k)): (v == b"1" if isinstance(v, bytes) else bool(int(v)))
            for k, v in raw.items()
        }

    async def set_flags(self, organization_id: int, flags: dict[str, Any]) -> dict[str, bool]:
        key = self._key(organization_id)
        if not flags:
            await self._redis.delete(key)
            return {}
        mapping = {name: "1" if bool(value) else "0" for name, value in flags.items()}
        await self._redis.hset(key, mapping=mapping)
        return await self.get_flags(organization_id)
