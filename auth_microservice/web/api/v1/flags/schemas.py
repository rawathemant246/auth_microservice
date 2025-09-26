"""Schemas for feature flag management."""

from __future__ import annotations

from typing import Dict

from pydantic import BaseModel


class FeatureFlagsResponse(BaseModel):
    flags: Dict[str, bool]


class FeatureFlagsUpdateRequest(BaseModel):
    flags: Dict[str, bool]
