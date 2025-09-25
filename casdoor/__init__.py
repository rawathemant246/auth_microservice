"""Test stub for Casdoor SDK."""

from __future__ import annotations

from typing import Any, Dict


class CasdoorSDK:
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401 - simple stub
        pass

    def get_auth_link(self, *, state: str, redirect_uri: str) -> str:
        return redirect_uri

    def get_oauth_token(self, code: str, state: str) -> Dict[str, Any]:  # noqa: ARG002
        return {}

    def parse_jwt_token(self, token: str) -> Dict[str, Any]:  # noqa: ARG002
        return {}
