"""Platform-wide settings endpoints (MongoDB backed)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request

from auth_microservice.settings import settings

router = APIRouter(tags=["admin-settings"])


def _verify_secret(request: Request) -> None:
    secret = request.headers.get("X-Internal-Secret")
    expected = settings.internal_api_secret
    if not expected or not secret or not secrets.compare_digest(secret, expected):
        raise HTTPException(status_code=403, detail="invalid_internal_secret")


@router.get("/admin/settings/platform")
async def get_platform_settings(request: Request) -> dict:
    _verify_secret(request)
    db = request.app.state.document_store._db
    doc = await db.platform_settings.find_one({"_id": "platform"})
    if doc is None:
        return {"data": {}}
    doc.pop("_id", None)
    return {"data": doc}


@router.put("/admin/settings/platform")
async def update_platform_settings(request: Request) -> dict:
    _verify_secret(request)
    body = await request.json()
    db = request.app.state.document_store._db
    await db.platform_settings.update_one(
        {"_id": "platform"},
        {"$set": body},
        upsert=True,
    )
    return {"message": "Platform settings updated"}
