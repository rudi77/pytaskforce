import os
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from taskforce.api.schemas.errors import ErrorResponse

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    checks: dict[str, str] | None = None


def _http_exception(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> HTTPException:
    """Build standardized HTTPException with ErrorResponse payload."""
    return HTTPException(
        status_code=status_code,
        detail=ErrorResponse(
            code=code, message=message, details=details, detail=message
        ).model_dump(exclude_none=True),
        headers={"X-Taskforce-Error": "1"},
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness probe - is the service running?"""
    return HealthResponse(status="healthy", version="1.0.0")


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check() -> HealthResponse:
    """Readiness probe - can the service handle requests?

    Verifies that core dependencies are reachable:
    - Tool registry can be loaded
    - Profile configuration directory exists
    """
    checks: dict[str, str] = {}

    # Check tool registry
    try:
        from taskforce.application.tool_registry import get_tool_registry

        registry = get_tool_registry()
        tool_count = len(registry.get_native_tool_names())
        checks["tool_registry"] = f"ok ({tool_count} tools)"
    except Exception as e:
        checks["tool_registry"] = f"failed: {e}"
        raise _http_exception(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "not_ready",
            "Tool registry unavailable",
            checks,
        )

    # Check config directory
    try:
        from taskforce.core.utils.paths import get_base_path

        base = get_base_path()
        config_dir = base / "src" / "taskforce_extensions" / "configs"
        if config_dir.exists():
            checks["config_dir"] = "ok"
        else:
            checks["config_dir"] = "missing (using defaults)"
    except Exception as e:
        checks["config_dir"] = f"failed: {e}"

    # Check LLM API key availability (without making a call)
    llm_key_set = bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("AZURE_OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
    )
    checks["llm_api_key"] = "configured" if llm_key_set else "not configured"

    return HealthResponse(status="ready", version="1.0.0", checks=checks)

