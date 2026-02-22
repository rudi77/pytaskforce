"""Shared error-handling utilities for API routes.

Provides a single ``http_exception`` helper so that every route module
produces the same standardized ``ErrorResponse`` payload with the
``X-Taskforce-Error: 1`` header.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from taskforce.api.schemas.errors import ErrorResponse


def http_exception(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    """Build a standardized HTTPException with ErrorResponse payload.

    Args:
        status_code: HTTP status code.
        code: Machine-readable error code (e.g. ``"not_found"``).
        message: Human-readable error description.
        details: Optional structured error details.

    Returns:
        HTTPException ready to be raised from a route handler.
    """
    return HTTPException(
        status_code=status_code,
        detail=ErrorResponse(
            code=code, message=message, details=details, detail=message
        ).model_dump(exclude_none=True),
        headers={"X-Taskforce-Error": "1"},
    )
