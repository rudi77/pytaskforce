"""FastAPI exception handlers shared by the standalone server and embedded apps.

Lives in its own module so :mod:`taskforce.host` (and any host application
that wants the same error semantics) can import the handler without
triggering :mod:`taskforce.api.server`'s module-level app construction
and plugin discovery.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse


async def taskforce_http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Return standardized error responses for Taskforce exceptions.

    Recognises HTTPExceptions tagged with the ``X-Taskforce-Error: 1``
    header and a dict ``detail`` payload (the structured ``ErrorResponse``
    shape) and serialises the dict directly. Falls back to FastAPI's
    default handler for everything else.
    """
    if exc.headers and exc.headers.get("X-Taskforce-Error") == "1" and isinstance(exc.detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers=exc.headers,
        )
    return await http_exception_handler(request, exc)
