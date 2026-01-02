"""
MCP Client for connecting to local and remote MCP servers.

Provides connection management for Model Context Protocol servers via:
- stdio: Local servers launched as subprocess
- SSE: Remote servers via Server-Sent Events
"""

from contextlib import asynccontextmanager
from typing import Any

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
except ImportError as e:
    raise ImportError("MCP library not installed. Install with: uv add mcp") from e


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
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def close(self):
        """Close the connection to the MCP server."""
        # Context managers handle cleanup automatically
        pass
