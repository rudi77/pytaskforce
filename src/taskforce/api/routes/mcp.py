"""
MCP Routes
==========

UI helpers for configuring MCP servers from the agent editor:

* ``POST /api/v1/mcp/probe`` — connects to a temporary MCP server using the
  user's stdio/sse config and returns the discovered tools so the editor
  can populate the ``mcp_tool_allowlist`` selector.

Probes use a hard timeout so a misconfigured server can't hang the UI.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import structlog
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from taskforce.api.errors import http_exception as _http_exception

logger = structlog.get_logger("taskforce.api.routes.mcp")

router = APIRouter()


class McpProbeRequest(BaseModel):
    type: Literal["stdio", "sse"]
    command: str | None = Field(default=None, description="stdio: command to run")
    args: list[str] = Field(default_factory=list, description="stdio: args")
    env: dict[str, str] = Field(
        default_factory=dict, description="stdio: env vars"
    )
    url: str | None = Field(default=None, description="sse: server URL")


class McpToolEntry(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = None


class McpProbeResponse(BaseModel):
    ok: bool
    elapsed_ms: int
    tools: list[McpToolEntry] = Field(default_factory=list)
    error: str | None = None


async def _probe(request: McpProbeRequest, timeout: float) -> McpProbeResponse:
    from taskforce.infrastructure.tools.mcp.client import MCPClient
    import time

    start = time.perf_counter()
    try:
        if request.type == "stdio":
            if not request.command:
                return McpProbeResponse(
                    ok=False,
                    elapsed_ms=0,
                    error="stdio probe requires a command",
                )
            ctx = MCPClient.create_stdio(
                request.command, request.args, request.env or None
            )
        else:
            if not request.url:
                return McpProbeResponse(
                    ok=False,
                    elapsed_ms=0,
                    error="sse probe requires a url",
                )
            ctx = MCPClient.create_sse(request.url)

        async def _do() -> list[McpToolEntry]:
            async with ctx as client:
                raw = await client.list_tools()
                tools: list[McpToolEntry] = []
                for entry in raw:
                    tools.append(
                        McpToolEntry(
                            name=entry.get("name", ""),
                            description=entry.get("description", "") or "",
                            input_schema=entry.get("input_schema")
                            or entry.get("inputSchema"),
                        )
                    )
                return tools

        tools = await asyncio.wait_for(_do(), timeout=timeout)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return McpProbeResponse(ok=True, elapsed_ms=elapsed_ms, tools=tools)
    except asyncio.TimeoutError:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return McpProbeResponse(
            ok=False,
            elapsed_ms=elapsed_ms,
            error=f"probe timed out after {timeout}s",
        )
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return McpProbeResponse(
            ok=False, elapsed_ms=elapsed_ms, error=f"{type(exc).__name__}: {exc}"
        )


@router.post(
    "/mcp/probe",
    response_model=McpProbeResponse,
    summary="Probe an MCP server and return its tool catalog",
)
async def probe_mcp(request: McpProbeRequest) -> McpProbeResponse:
    """Connect briefly to an MCP server and list its tools.

    Used by the agent editor to validate an MCP entry and populate the
    ``mcp_tool_allowlist`` multi-select.
    """
    if request.type not in ("stdio", "sse"):
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_mcp_type",
            message=f"Unknown MCP type: {request.type!r}",
        )
    return await _probe(request, timeout=10.0)
