"""
MCP Routes
==========

UI helpers for configuring MCP servers from the agent editor:

* ``POST /api/v1/mcp/probe`` — connects to a temporary MCP server using the
  user's stdio/sse config and returns the discovered tools so the editor
  can populate the ``mcp_tool_allowlist`` selector.

Probes use a hard timeout so a misconfigured server can't hang the UI.

Security
--------

The stdio probe path executes a user-supplied command via ``execve``. To
contain the blast radius:

* Probes are gated behind a permission check — by default, only requests
  that arrive on a localhost socket are accepted. Set
  ``TASKFORCE_MCP_PROBE_ALLOW_REMOTE=1`` to opt in for remote access.
* The stdio command must match an allowlist. The default allowlist covers
  the standard MCP launchers (``npx``, ``npm``, ``uv``, ``uvx``, ``python``,
  ``python3``, ``node``, ``deno``, ``pnpm``, ``yarn``, ``bun``). Override
  via ``TASKFORCE_MCP_PROBE_COMMANDS`` (comma-separated, ``*`` to disable).
* Subprocesses started during a probe are wrapped so a probe timeout
  always tears down the child process group.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import os
from pathlib import Path
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from taskforce.api.errors import http_exception as _http_exception

logger = structlog.get_logger("taskforce.api.routes.mcp")

router = APIRouter()


_DEFAULT_STDIO_ALLOWLIST: frozenset[str] = frozenset(
    {
        "npx",
        "npm",
        "uv",
        "uvx",
        "python",
        "python3",
        "node",
        "deno",
        "pnpm",
        "yarn",
        "bun",
    }
)


def _stdio_command_allowlist() -> set[str] | None:
    """Return the configured stdio command allowlist, or ``None`` for ``*``."""
    raw = os.environ.get("TASKFORCE_MCP_PROBE_COMMANDS")
    if raw is None:
        return set(_DEFAULT_STDIO_ALLOWLIST)
    raw = raw.strip()
    if raw == "*":
        return None
    return {entry.strip() for entry in raw.split(",") if entry.strip()}


def _is_loopback_client(request: Request) -> bool:
    if os.environ.get("TASKFORCE_MCP_PROBE_ALLOW_REMOTE", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        return True
    client = request.client
    if client is None:
        return False
    host = client.host
    # Starlette's ``TestClient`` reports ``testclient`` for in-process tests;
    # treat it as loopback so local pytest runs work without env opt-in.
    if host == "testclient":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _command_basename(command: str) -> str:
    """Pick the basename of a path-like command for allowlist comparison."""
    if not command:
        return ""
    return Path(command).name.lower().removesuffix(".exe").removesuffix(".cmd")


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


def _validate_request(request: McpProbeRequest) -> str | None:
    """Return an error string if ``request`` is rejected, otherwise ``None``."""
    if request.type == "stdio":
        if not request.command:
            return "stdio probe requires a command"
        allowlist = _stdio_command_allowlist()
        if allowlist is not None:
            base = _command_basename(request.command)
            if base not in allowlist:
                return (
                    f"command {request.command!r} is not on the MCP probe "
                    "allowlist (override via TASKFORCE_MCP_PROBE_COMMANDS)"
                )
    else:
        if not request.url:
            return "sse probe requires a url"
        if not (request.url.startswith("http://") or request.url.startswith("https://")):
            return "sse url must be http(s)"
    return None


async def _probe(request: McpProbeRequest, timeout: float) -> McpProbeResponse:
    from taskforce.infrastructure.tools.mcp.client import MCPClient
    import time

    start = time.perf_counter()
    rejection = _validate_request(request)
    if rejection is not None:
        return McpProbeResponse(ok=False, elapsed_ms=0, error=rejection)

    if request.type == "stdio":
        ctx = MCPClient.create_stdio(
            request.command,  # type: ignore[arg-type]
            request.args,
            request.env or None,
        )
    else:
        ctx = MCPClient.create_sse(request.url)  # type: ignore[arg-type]

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

    # Run the probe inside its own task so we can cancel it cleanly on
    # timeout. ``asyncio.wait_for`` cancels the inner task and waits for
    # it to finish unwinding, which lets the ``async with`` blocks tear
    # down their subprocess context managers (the underlying
    # ``stdio_client`` issues ``terminate`` on cancellation).
    task = asyncio.create_task(_do())
    try:
        tools = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except asyncio.TimeoutError:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
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

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return McpProbeResponse(ok=True, elapsed_ms=elapsed_ms, tools=tools)


@router.post(
    "/mcp/probe",
    response_model=McpProbeResponse,
    summary="Probe an MCP server and return its tool catalog",
)
async def probe_mcp(request: McpProbeRequest, http_request: Request) -> McpProbeResponse:
    """Connect briefly to an MCP server and list its tools.

    Used by the agent editor to validate an MCP entry and populate the
    ``mcp_tool_allowlist`` multi-select.
    """
    if not _is_loopback_client(http_request):
        raise _http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="mcp_probe_forbidden",
            message=(
                "MCP probes execute user-supplied commands and are only "
                "served to loopback clients by default. Set "
                "TASKFORCE_MCP_PROBE_ALLOW_REMOTE=1 to opt in."
            ),
        )
    return await _probe(request, timeout=10.0)
