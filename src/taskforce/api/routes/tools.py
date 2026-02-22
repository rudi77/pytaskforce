"""
Tool Catalog API Routes
========================

HTTP endpoint for retrieving the service tool catalog.

Endpoints:
- GET /api/v1/tools - Get tool catalog

Story: 8.2 - Tool Catalog + Allowlist Validation
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from taskforce.application.tool_registry import get_tool_registry

router = APIRouter()


class ToolCatalogResponse(BaseModel):
    """Response schema for tool catalog endpoint."""

    tools: list[dict[str, Any]]


@router.get(
    "/tools",
    response_model=ToolCatalogResponse,
    summary="Get tool catalog",
    description=(
        "Retrieve the service tool catalog with all available native tools"
    ),
)
def get_tools() -> ToolCatalogResponse:
    """
    Get the service tool catalog.

    Returns all native tools with their definitions including name,
    description, parameters_schema, requires_approval, approval_risk_level,
    and origin.

    This endpoint is stable and deterministic (no MCP discovery).

    Returns:
        Tool catalog with list of native tool definitions
    """
    registry = get_tool_registry()
    tools = registry.list_native_tools()
    return ToolCatalogResponse(tools=tools)
