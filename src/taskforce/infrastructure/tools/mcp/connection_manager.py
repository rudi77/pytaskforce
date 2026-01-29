"""
MCP Connection Manager

Centralizes MCP server connection logic to eliminate duplication between
AgentFactory and InfrastructureBuilder. Provides a single, consistent way
to connect to MCP servers (stdio or SSE) and wrap their tools.

Part of the codebase simplification refactoring.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from taskforce.core.interfaces.tools import ToolProtocol

if TYPE_CHECKING:
    from taskforce.core.domain.agent_definition import MCPServerConfig


@dataclass
class MCPConnectionResult:
    """Result from connecting to an MCP server."""

    tools: list[ToolProtocol]
    context: Any  # The async context manager that must be kept alive
    server_type: str
    tool_names: list[str]


@dataclass
class MCPConnectionManager:
    """
    Centralized MCP server connection management.

    Handles:
    - Memory directory creation for memory servers
    - stdio and SSE connection establishment
    - Tool wrapping with MCPToolWrapper
    - Output filtering for specific tools
    - Graceful error handling

    Example:
        >>> manager = MCPConnectionManager()
        >>> tools, contexts = await manager.connect_all(mcp_servers)
        >>> # tools are ready to use
        >>> # contexts must be kept alive for tools to work
    """

    logger: Any = field(default_factory=lambda: structlog.get_logger(__name__))
    output_filters: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = field(
        default_factory=dict
    )

    async def connect(self, server_config: MCPServerConfig) -> MCPConnectionResult | None:
        """
        Connect to a single MCP server.

        Args:
            server_config: MCP server configuration (stdio or SSE)

        Returns:
            MCPConnectionResult with tools and context, or None if connection failed
        """

        server_type = server_config.type

        try:
            if server_type == "stdio":
                return await self._connect_stdio(server_config)
            elif server_type == "sse":
                return await self._connect_sse(server_config)
            else:
                self.logger.warning(
                    "unknown_mcp_server_type",
                    server_type=server_type,
                    hint="Supported types: 'stdio', 'sse'",
                )
                return None

        except Exception as e:
            self.logger.warning(
                "mcp_server_connection_failed",
                server_type=server_type,
                command=getattr(server_config, "command", None),
                url=getattr(server_config, "url", None),
                error=str(e),
                error_type=type(e).__name__,
                hint="Agent will continue without this MCP server",
            )
            return None

    async def connect_all(
        self,
        configs: list[MCPServerConfig],
        tool_filter: list[str] | None = None,
    ) -> tuple[list[ToolProtocol], list[Any]]:
        """
        Connect to multiple MCP servers.

        Args:
            configs: List of MCP server configurations
            tool_filter: Optional list of allowed tool names (None = all allowed)

        Returns:
            Tuple of (tools, contexts) where contexts must be kept alive
        """
        if not configs:
            self.logger.debug("no_mcp_servers_configured")
            return [], []

        all_tools: list[ToolProtocol] = []
        all_contexts: list[Any] = []

        for config in configs:
            result = await self.connect(config)
            if result is None:
                continue

            # Filter tools if allowlist provided
            tools = result.tools
            if tool_filter:
                original_count = len(tools)
                tools = [t for t in tools if t.name in tool_filter]
                self.logger.debug(
                    "mcp_tools_filtered",
                    server_type=result.server_type,
                    original_count=original_count,
                    filtered_count=len(tools),
                    filter=tool_filter,
                )

            # Apply output filters
            filtered_tools = self._apply_output_filters(tools)

            all_tools.extend(filtered_tools)
            all_contexts.append(result.context)

            self.logger.info(
                "mcp_server_connected",
                server_type=result.server_type,
                tools_count=len(filtered_tools),
                tool_names=[t.name for t in filtered_tools],
            )

        return all_tools, all_contexts

    async def _connect_stdio(self, server_config: MCPServerConfig) -> MCPConnectionResult | None:
        """Connect to a stdio MCP server."""
        from taskforce.infrastructure.tools.mcp.client import MCPClient
        from taskforce.infrastructure.tools.mcp.wrapper import MCPToolWrapper

        command = server_config.command
        if not command:
            self.logger.warning(
                "mcp_server_missing_command",
                server_type="stdio",
                hint="stdio server requires 'command' field",
            )
            return None

        # Prepare environment with memory path if needed
        env = self._prepare_env_with_memory_path(dict(server_config.env))

        self.logger.info(
            "connecting_to_mcp_server",
            server_type="stdio",
            command=command,
            args=server_config.args,
        )

        # Create context manager and enter it
        ctx = MCPClient.create_stdio(
            command=command,
            args=server_config.args,
            env=env if env else None,
        )
        client = await ctx.__aenter__()

        # Get tools
        tools_list = await client.list_tools()
        tools: list[ToolProtocol] = [MCPToolWrapper(client, tool_def) for tool_def in tools_list]

        return MCPConnectionResult(
            tools=tools,
            context=ctx,
            server_type="stdio",
            tool_names=[t.name for t in tools],
        )

    async def _connect_sse(self, server_config: MCPServerConfig) -> MCPConnectionResult | None:
        """Connect to an SSE MCP server."""
        from taskforce.infrastructure.tools.mcp.client import MCPClient
        from taskforce.infrastructure.tools.mcp.wrapper import MCPToolWrapper

        url = server_config.url
        if not url:
            self.logger.warning(
                "mcp_server_missing_url",
                server_type="sse",
                hint="sse server requires 'url' field",
            )
            return None

        self.logger.info(
            "connecting_to_mcp_server",
            server_type="sse",
            url=url,
        )

        # Create context manager and enter it
        ctx = MCPClient.create_sse(url)
        client = await ctx.__aenter__()

        # Get tools
        tools_list = await client.list_tools()
        tools: list[ToolProtocol] = [MCPToolWrapper(client, tool_def) for tool_def in tools_list]

        return MCPConnectionResult(
            tools=tools,
            context=ctx,
            server_type="sse",
            tool_names=[t.name for t in tools],
        )

    def _prepare_env_with_memory_path(self, env: dict[str, str]) -> dict[str, str]:
        """
        Prepare environment variables, creating memory directory if needed.

        If MEMORY_FILE_PATH is set, ensures the parent directory exists and
        converts relative paths to absolute paths.

        Args:
            env: Environment variables dictionary

        Returns:
            Updated environment variables dictionary
        """
        if "MEMORY_FILE_PATH" not in env:
            return env

        memory_path = Path(env["MEMORY_FILE_PATH"])

        # Convert relative paths to absolute
        if not memory_path.is_absolute():
            memory_path = memory_path.resolve()

        # Ensure parent directory exists
        memory_dir = memory_path.parent
        if not memory_dir.exists():
            memory_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(
                "memory_directory_created",
                memory_dir=str(memory_dir),
                memory_file=str(memory_path),
            )

        # Update env with absolute path
        env["MEMORY_FILE_PATH"] = str(memory_path)
        return env

    def _apply_output_filters(self, tools: list[ToolProtocol]) -> list[ToolProtocol]:
        """
        Apply output filters to tools that need them.

        Args:
            tools: List of tools to potentially wrap

        Returns:
            List of tools with filters applied where configured
        """
        from taskforce.infrastructure.tools.wrappers import OutputFilteringTool

        if not self.output_filters:
            return tools

        filtered_tools: list[ToolProtocol] = []
        for tool in tools:
            if tool.name in self.output_filters:
                filter_func = self.output_filters[tool.name]
                self.logger.debug(
                    "wrapping_tool_with_filter",
                    tool_name=tool.name,
                    filter=getattr(filter_func, "__name__", "unknown"),
                )
                filtered_tools.append(OutputFilteringTool(tool, filter_func))
            else:
                filtered_tools.append(tool)

        return filtered_tools


def create_default_connection_manager() -> MCPConnectionManager:
    """
    Create an MCPConnectionManager with default output filters.

    Returns:
        MCPConnectionManager configured with standard filters
    """
    from taskforce.infrastructure.tools.filters import simplify_wiki_list_output

    return MCPConnectionManager(
        output_filters={
            "list_wiki": simplify_wiki_list_output,
        }
    )
