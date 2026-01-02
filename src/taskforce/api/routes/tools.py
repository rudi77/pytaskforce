"""
Tool Catalog API Routes
========================

HTTP endpoint for retrieving the service tool catalog.

Endpoints:
- GET /api/v1/tools - Get tool catalog

Story: 8.2 - Tool Catalog + Allowlist Validation
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, List

from taskforce.application.tool_catalog import get_tool_catalog

router = APIRouter()


class ToolCatalogResponse(BaseModel):
    """Response schema for tool catalog endpoint."""

    tools: List[Dict[str, Any]]


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
    catalog = get_tool_catalog()
    tools = catalog.get_native_tools()
    return ToolCatalogResponse(tools=tools)
