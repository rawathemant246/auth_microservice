"""Casdoor SSO integration helpers."""

from __future__ import annotations

import asyncio
from typing import Any

from casdoor import CasdoorSDK

from auth_microservice.settings import settings


class CasdoorService:
    """Service wrapper around Casdoor SDK configured for Google SSO only."""

    def __init__(self) -> None:
        # CasdoorSDK signature: (endpoint, client_id, client_secret,
        # certificate, organization_name, application_name).
        self._sdk = CasdoorSDK(
            settings.casdoor_endpoint,
            settings.casdoor_client_id,
            settings.casdoor_client_secret,
            "",
            settings.casdoor_organization_name,
            settings.casdoor_application_name,
        )

    def get_login_url(self, redirect_uri: str, state: str) -> str:
        """Construct the Casdoor hosted login URL for Google SSO."""

        return self._sdk.get_auth_link(state=state, redirect_uri=redirect_uri)

    async def exchange_code(self, code: str, state: str) -> dict[str, Any]:
        """Exchange Casdoor authorization code for tokens and profile."""

        token = await asyncio.to_thread(self._sdk.get_oauth_token, code, state)
        access_token = token.get("access_token")
        profile: dict[str, Any] | None = None
        if access_token:
            profile = await asyncio.to_thread(self._sdk.parse_jwt_token, access_token)
        return {"token": token, "profile": profile or {}}
