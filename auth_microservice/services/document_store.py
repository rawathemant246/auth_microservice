"""Wrapper around the document database (MongoDB/JSONB)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument


class DocumentStoreService:
    """High-level accessors for semi-structured organization documents."""

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._db = database

    async def get_organization_settings(self, organization_id: int) -> dict[str, Any] | None:
        document = await self._db.organization_settings.find_one(
            {"organization_id": organization_id},
            {"_id": 0},
        )
        if document is not None:
            document.pop("organization_id", None)
        return document

    async def get_privacy_settings(self, organization_id: int) -> dict[str, Any] | None:
        document = await self._db.privacy_settings.find_one(
            {"organization_id": organization_id},
            {"_id": 0},
        )
        if document is not None:
            document.pop("organization_id", None)
        return document

    async def get_user_feedback(self, organization_id: int, user_id: int | None = None) -> list[dict[str, Any]]:
        return await self.list_feedback(
            organization_id=organization_id,
            user_id=user_id,
        )

    async def upsert_organization_settings(
        self,
        organization_id: int,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {"organization_id": organization_id, **settings}
        await self._db.organization_settings.update_one(
            {"organization_id": organization_id},
            {"$set": payload},
            upsert=True,
        )
        result = dict(payload)
        result.pop("organization_id", None)
        return result

    async def upsert_privacy_settings(
        self,
        organization_id: int,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {"organization_id": organization_id, **settings}
        await self._db.privacy_settings.update_one(
            {"organization_id": organization_id},
            {"$set": payload},
            upsert=True,
        )
        result = dict(payload)
        result.pop("organization_id", None)
        return result

    async def create_feedback(
        self,
        *,
        organization_id: int,
        user_id: int,
        content: str,
        category: str,
        status: str,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        document = {
            "feedback_id": uuid4().hex,
            "organization_id": organization_id,
            "user_id": user_id,
            "content": content,
            "category": category,
            "status": status,
            "created_at": now,
            "updated_at": now,
        }
        await self._db.user_feedback.insert_one(document)
        return self._normalize_feedback(document)

    async def list_feedback(
        self,
        *,
        organization_id: int,
        user_id: int | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"organization_id": organization_id}
        if user_id is not None:
            query["user_id"] = user_id
        if status is not None:
            query["status"] = status
        cursor = self._db.user_feedback.find(query)
        documents = await cursor.to_list(length=None)
        return [self._normalize_feedback(doc) for doc in documents]

    async def update_feedback(
        self,
        feedback_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        updates = {**updates, "updated_at": datetime.utcnow()}
        result = await self._db.user_feedback.find_one_and_update(
            {"feedback_id": feedback_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        return self._normalize_feedback(result)

    async def search_feedback(
        self,
        *,
        organization_id: int,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        regex = {"$regex": query, "$options": "i"}
        cursor = self._db.user_feedback.find(
            {
                "organization_id": organization_id,
                "$or": [
                    {"content": regex},
                    {"category": regex},
                    {"status": regex},
                ],
            },
        ).limit(limit)
        documents = await cursor.to_list(length=None)
        return [self._normalize_feedback(doc) for doc in documents]

    @staticmethod
    def _normalize_feedback(document: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(document)
        normalized.pop("_id", None)
        created_at = normalized.get("created_at")
        updated_at = normalized.get("updated_at")
        if isinstance(created_at, datetime):
            normalized["created_at"] = created_at.isoformat()
        if isinstance(updated_at, datetime):
            normalized["updated_at"] = updated_at.isoformat()
        return normalized
