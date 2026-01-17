"""
MCP Client for connecting to local and remote MCP servers.

Provides connection management for Model Context Protocol servers via:
- stdio: Local servers launched as subprocess
- SSE: Remote servers via Server-Sent Events
"""

from contextlib import asynccontextmanager
from typing import Any

from taskforce.core.domain.errors import ToolError, tool_error_payload

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
except ImportError as e:
    raise ImportError("MCP library not installed. Install with: uv add mcp") from e


def _patch_mcp_validation():
    """
    Monkey-patch MCP ClientSession to be more lenient with tool result validation.
    
    Some MCP servers (like @modelcontextprotocol/server-memory) return structured
    content that violates their own self-declared outputSchema (e.g., including 
    additional properties like 'type' when 'additionalProperties: false' is set).
    
    This patch catches these validation errors and allows the tool execution
    to proceed, since the raw result is still available and useful.
    """
    original_validate = getattr(ClientSession, "_validate_tool_result", None)
    if not original_validate:
        return

    async def lenient_validate(self, name, result):
        try:
            await original_validate(self, name, result)
        except RuntimeError as e:
            # Check if this is a validation error we want to suppress
            error_msg = str(e)
            if "Invalid structured content returned by tool" in error_msg:
                # We log this at debug level to avoid noise, but keep the result
                import structlog
                logger = structlog.get_logger("taskforce.mcp")
                logger.debug(
                    "mcp_validation_error_suppressed",
                    tool_name=name,
                    error=error_msg,
                    hint="Server returned content violating its own schema; suppressing for compatibility"
                )
            else:
                raise

    ClientSession._validate_tool_result = lenient_validate


# Apply the patch on import
_patch_mcp_validation()


class MCPClient:
    """
    Client for connecting to MCP servers (local stdio or remote SSE).

    Manages connection lifecycle and provides methods to list and call
    tools. Supports both local servers (launched via subprocess) and
    remote servers (connected via SSE).

    Example:
        >>> ctx = MCPClient.create_stdio("python", ["server.py"])
        >>> async with ctx as client:
        ...     tools = await client.list_tools()
        ...     result = await client.call_tool("tool_name", {"p": "v"})
    """

    def __init__(
        self, session: ClientSession, read_stream: Any, write_stream: Any
    ):
        """
        Initialize MCP client with an active session.

        Args:
            session: Active MCP ClientSession
            read_stream: Read stream for the connection
            write_stream: Write stream for the connection
        """
        self.session = session
        self.read_stream = read_stream
        self.write_stream = write_stream
        self._tools_cache: list[dict[str, Any]] | None = None

    @classmethod
    @asynccontextmanager
    async def create_stdio(
        cls,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ):
        """
        Create a client connected to a local stdio MCP server.

        Args:
            command: Command to execute (e.g., "python", "node")
            args: Arguments to pass to the command (e.g., ["server.py"])
            env: Optional environment variables

        Yields:
            MCPClient: Connected client instance

        Example:
            >>> ctx = MCPClient.create_stdio("python", ["mcp_srv.py"])
            >>> async with ctx as client:
            ...     tools = await client.list_tools()
        """
        server_params = StdioServerParameters(
            command=command, args=args, env=env
        )

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield cls(session, read_stream, write_stream)

    @classmethod
    @asynccontextmanager
    async def create_sse(cls, url: str):
        """
        Create a client connected to a remote SSE MCP server.

        Args:
            url: URL of the SSE server endpoint

        Yields:
            MCPClient: Connected client instance

        Example:
            >>> ctx = MCPClient.create_sse("http://localhost:8000/sse")
            >>> async with ctx as client:
            ...     tools = await client.list_tools()
        """
        async with sse_client(url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield cls(session, read_stream, write_stream)

    async def list_tools(self) -> list[dict[str, Any]]:
        """
        List all tools available from the connected MCP server.

        Returns:
            List of tool definitions with name, description, input_schema

        Example:
            >>> tools = await client.list_tools()
            >>> for tool in tools:
            ...     print(f"{tool['name']}: {tool['description']}")
        """
        if self._tools_cache is None:
            response = await self.session.list_tools()
            self._tools_cache = [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": (
                        tool.inputSchema
                        if hasattr(tool, "inputSchema")
                        else {}
                    ),
                }
                for tool in response.tools
            ]
        return self._tools_cache

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Execute a tool on the connected MCP server.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool parameters as a dictionary

        Returns:
            Dictionary with:
            - success: bool - True if execution succeeded
            - result: Any - Tool execution result
            - error: str - Error message (if failed)

        Example:
            >>> result = await client.call_tool("read_file", {"p": "d.txt"})
            >>> if result["success"]:
            ...     print(result["result"])
        """
        try:
            response = await self.session.call_tool(tool_name, arguments)

            # MCP returns a CallToolResult with content array
            if hasattr(response, "content") and response.content:
                # Extract text content from the response
                content_items = []
                for item in response.content:
                    if hasattr(item, "text"):
                        content_items.append(item.text)
                    elif hasattr(item, "data"):
                        content_items.append(str(item.data))

                result_text = (
                    "\n".join(content_items)
                    if content_items
                    else str(response.content)
                )

                return {
                    "success": True,
                    "result": result_text,
                }
            else:
                return {
                    "success": True,
                    "result": str(response),
                }
        except Exception as e:
            tool_error = ToolError(
                f"MCP tool '{tool_name}' failed: {e}",
                tool_name=tool_name,
                details={"arguments": arguments},
            )
            return tool_error_payload(tool_error)

    async def close(self):
        """Close the connection to the MCP server."""
        # Context managers handle cleanup automatically
        pass
