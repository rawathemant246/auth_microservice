"""Schemas for search endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SearchResponse(BaseModel):
    query: str
    tickets: list[dict[str, Any]]
    feedback: list[dict[str, Any]]
    logs: list[dict[str, Any]]

