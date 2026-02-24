import os

from fastapi import APIRouter, status
from pydantic import BaseModel

from taskforce.api.errors import http_exception as _http_exception

router = APIRouter()


def _get_version() -> str:
    """Read version from package metadata."""
    try:
        from importlib.metadata import version

        return version("taskforce")
    except Exception:
        return "0.0.0-dev"


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    checks: dict[str, str] | None = None


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness probe - is the service running?"""
    return HealthResponse(status="healthy", version=_get_version())


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
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="not_ready",
            message="Tool registry unavailable",
            details=checks,
        ) from e

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
        or os.getenv("AZURE_API_KEY")
        or os.getenv("AZURE_OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
    )
    checks["llm_api_key"] = "configured" if llm_key_set else "not configured"

    return HealthResponse(status="ready", version=_get_version(), checks=checks)

