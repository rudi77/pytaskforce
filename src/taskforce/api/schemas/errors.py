"""Error response schemas for API endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    code: str
    message: str
    details: dict[str, Any] | None = None
    detail: str | None = None
