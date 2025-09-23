"""Wrapper around the document database (MongoDB/JSONB)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


class DocumentStoreService:
    """High-level accessors for semi-structured organization documents."""

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._db = database

    async def get_organization_settings(self, organization_id: int) -> dict[str, Any] | None:
        document = await self._db.organization_settings.find_one(
            {"organization_id": organization_id},
            {"_id": 0},
        )
        return document

    async def get_privacy_settings(self, organization_id: int) -> dict[str, Any] | None:
        document = await self._db.privacy_settings.find_one(
            {"organization_id": organization_id},
            {"_id": 0},
        )
        return document

    async def get_user_feedback(self, organization_id: int, user_id: int | None = None) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"organization_id": organization_id}
        if user_id is not None:
            query["user_id"] = user_id
        cursor = self._db.user_feedback.find(query, {"_id": 0})
        return await cursor.to_list(length=None)
