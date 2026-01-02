"""
MCP Tool Wrapper - Adapter from MCP tools to ToolProtocol.

Wraps MCP tool definitions to conform to the Taskforce ToolProtocol interface,
enabling seamless integration of external MCP tools into the agent framework.
"""

from typing import Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol
from taskforce.infrastructure.tools.mcp.client import MCPClient


class MCPToolWrapper(ToolProtocol):
    """
    Adapter wrapping an MCP tool to conform to ToolProtocol.

    Converts MCP tool definitions and execution to the standard Taskforce
    tool interface, handling schema conversion and parameter validation.

    Example:
        >>> ctx = MCPClient.create_stdio("python", ["server.py"])
        >>> async with ctx as client:
        ...     tools = await client.list_tools()
        ...     wrapper = MCPToolWrapper(client, tools[0])
        ...     result = await wrapper.execute(param="value")
    """

    def __init__(
        self,
        client: MCPClient,
        tool_definition: dict[str, Any],
        requires_approval: bool = False,
        risk_level: ApprovalRiskLevel = ApprovalRiskLevel.LOW,
    ):
        """
        Initialize MCP tool wrapper.

        Args:
            client: Connected MCPClient instance
            tool_definition: Tool definition from MCP server
                (name, description, input_schema)
            requires_approval: Whether this tool requires user approval
            risk_level: Risk level for approval prompts
        """
        self._client = client
        self._tool_definition = tool_definition
        self._requires_approval = requires_approval
        self._risk_level = risk_level

        # Extract tool metadata
        self._name = tool_definition.get("name", "unknown_mcp_tool")
        self._description = tool_definition.get(
            "description", "MCP tool with no description"
        )
        self._input_schema = tool_definition.get("input_schema", {})

    @property
    def name(self) -> str:
        """Return the MCP tool name."""
        return self._name

    @property
    def description(self) -> str:
        """Return the MCP tool description."""
        return self._description

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """
        Convert MCP input schema to OpenAI function calling format.

        MCP tools typically use JSON Schema format, which is compatible
        with OpenAI function calling. If the schema is missing required
        fields, we provide sensible defaults.

        Returns:
            OpenAI-compatible parameter schema
        """
        # MCP input_schema is typically already in JSON Schema format
        # which is compatible with OpenAI function calling
        if not self._input_schema:
            return {
                "type": "object",
                "properties": {},
                "required": [],
            }

        # Ensure the schema has the required structure
        schema = self._input_schema.copy()
        if "type" not in schema:
            schema["type"] = "object"
        if "properties" not in schema:
            schema["properties"] = {}
        if "required" not in schema:
            schema["required"] = []

        return schema

    @property
    def requires_approval(self) -> bool:
        """Return whether this tool requires approval."""
        return self._requires_approval

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Return the risk level for approval prompts."""
        return self._risk_level

    def get_approval_preview(self, **kwargs: Any) -> str:
        """
        Generate approval preview for this MCP tool execution.

        Args:
            **kwargs: Parameters that will be passed to execute()

        Returns:
            Formatted preview string
        """
        params_preview = "\n".join(
            f"  {key}: {value}" for key, value in kwargs.items()
        )
        return (
            f"Tool: {self.name}\n"
            f"Description: {self.description}\n"
            f"Parameters:\n{params_preview}"
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute the MCP tool via the connected client.

        Validates parameters, calls the MCP server, and returns standardized
        results conforming to ToolProtocol expectations.

        Args:
            **kwargs: Tool parameters matching the input schema

        Returns:
            Dictionary with:
            - success: bool - True if execution succeeded
            - output: str - Tool output (on success)
            - result: Any - Structured result data (on success)
            - error: str - Error message (on failure)
            - error_type: str - Exception type (on failure)
        """
        # Validate parameters before execution
        is_valid, error_msg = self.validate_params(**kwargs)
        if not is_valid:
            return {
                "success": False,
                "error": error_msg,
                "error_type": "ValidationError",
            }

        try:
            # Call the MCP tool via the client
            result = await self._client.call_tool(self._name, kwargs)

            # MCP client already returns standardized format
            if result.get("success"):
                return {
                    "success": True,
                    "output": str(result.get("result", "")),
                    "result": result.get("result"),
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown MCP error"),
                    "error_type": result.get("error_type", "MCPError"),
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """
        Validate parameters against the MCP input schema.

        Checks that all required parameters are present. Full type validation
        is delegated to the MCP server.

        Args:
            **kwargs: Parameters to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        schema = self.parameters_schema
        required_params = schema.get("required", [])

        # Check for missing required parameters
        for param in required_params:
            if param not in kwargs:
                return False, f"Missing required parameter: {param}"

        # Basic type checking for properties
        properties = schema.get("properties", {})
        for param_name, param_value in kwargs.items():
            if param_name in properties:
                expected_type = properties[param_name].get("type")
                if expected_type:
                    # Basic type validation
                    type_map = {
                        "string": str,
                        "integer": int,
                        "number": (int, float),
                        "boolean": bool,
                        "object": dict,
                        "array": list,
                    }
                    expected_python_type = type_map.get(expected_type)
                    if expected_python_type and not isinstance(
                        param_value, expected_python_type
                    ):
                        return (
                            False,
                            f"Parameter '{param_name}' must be of type "
                            f"{expected_type}",
                        )

        return True, None
