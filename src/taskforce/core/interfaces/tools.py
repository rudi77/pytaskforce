"""
Tool Execution Protocol

This module defines the protocol interface for tool implementations.
Tools are executable capabilities that agents can invoke to perform actions
(file operations, code execution, web searches, API calls, etc.).

Protocol implementations must provide:
- Tool metadata (name, description, parameter schema)
- Parameter validation
- Async execution with error handling
- OpenAI function calling schema generation
"""

from enum import Enum
from typing import Any, Protocol


class ApprovalRiskLevel(str, Enum):
    """Risk level for tool approval prompts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolProtocol(Protocol):
    """
    Protocol defining the contract for tool implementations.

    Tools are executable capabilities that agents can invoke during mission execution.
    Each tool must provide metadata, parameter validation, and async execution.

    Tool Lifecycle:
        1. Agent queries tool metadata (name, description, parameters_schema)
        2. Agent validates parameters using validate_params()
        3. Agent requests approval (if requires_approval is True)
        4. Agent executes tool via execute() or execute_safe()
        5. Tool returns standardized result dictionary

    Parameter Schema:
        Tools must provide OpenAI function calling compatible parameter schemas:
        {
            "type": "object",
            "properties": {
                "param_name": {
                    "type": "string|integer|boolean|number|object|array",
                    "description": "Parameter description"
                }
            },
            "required": ["param1", "param2"]
        }

    Result Format:
        All execute() methods must return Dict with:
        - success: bool - True if execution succeeded
        - Additional fields based on tool (output, error, etc.)

    Error Handling:
        Tools should catch exceptions and return {"success": False, "error": "..."}
        rather than raising exceptions. The execute_safe() wrapper provides
        additional retry logic and timeout handling.
    """

    @property
    def name(self) -> str:
        """
        Unique identifier for the tool.

        Must be:
        - Lowercase with underscores (snake_case)
        - Descriptive and concise (e.g., "file_read", "python_execute")
        - Unique across all tools in the agent's toolset

        Returns:
            Tool name string

        Example:
            >>> tool.name
            'file_read'
        """
        ...

    @property
    def description(self) -> str:
        """
        Human-readable description of tool's purpose and behavior.

        Should include:
        - What the tool does (1-2 sentences)
        - Key parameters and their purpose
        - Expected output format
        - Any important constraints or limitations

        Used by:
        - LLM for tool selection during planning
        - OpenAI function calling schema
        - User-facing tool documentation

        Returns:
            Tool description string (1-3 sentences)

        Example:
            >>> tool.description
            'Read contents of a file from the filesystem. Returns file content as string or error if file not found.'
        """
        ...

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """
        OpenAI function calling compatible parameter schema.

        Defines the structure and types of parameters accepted by execute().
        Schema format follows JSON Schema specification with OpenAI extensions.

        The schema should:
        - List all parameters with types and descriptions
        - Mark required parameters in "required" array
        - Provide enums for constrained choices
        - Include format hints (e.g., "format": "path", "format": "url")

        Returns:
            Dictionary with JSON Schema structure:
            {
                "type": "object",
                "properties": {
                    "param_name": {
                        "type": "string",
                        "description": "Parameter description",
                        "enum": ["option1", "option2"]  # Optional
                    }
                },
                "required": ["param_name"]
            }

        Example:
            >>> tool.parameters_schema
            {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Path to file to read"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)",
                        "enum": ["utf-8", "ascii", "latin-1"]
                    }
                },
                "required": ["filename"]
            }

        Auto-Generation:
            Implementations can auto-generate schema from execute() method
            signature using inspect.signature(), but explicit schemas are
            preferred for better LLM understanding.
        """
        ...

    @property
    def requires_approval(self) -> bool:
        """
        Whether this tool requires user approval before execution.

        Set to True for tools that:
        - Modify external state (file writes, API calls, git commits)
        - Execute arbitrary code (python, shell commands)
        - Incur costs (paid API calls, cloud resources)
        - Access sensitive data

        Set to False for read-only tools:
        - File reads
        - Web searches (GET requests)
        - Data transformations

        Returns:
            True if approval required, False otherwise (default: False)

        Example:
            >>> file_read_tool.requires_approval
            False
            >>> file_write_tool.requires_approval
            True
        """
        ...

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """
        Risk level for approval prompts (LOW, MEDIUM, HIGH).

        Used to determine approval UI styling and warnings:
        - LOW: Minimal risk, simple confirmation
        - MEDIUM: Moderate risk, show operation preview
        - HIGH: High risk, require explicit confirmation with warnings

        Returns:
            ApprovalRiskLevel enum value

        Example:
            >>> file_write_tool.approval_risk_level
            ApprovalRiskLevel.MEDIUM
            >>> shell_execute_tool.approval_risk_level
            ApprovalRiskLevel.HIGH
        """
        ...

    def get_approval_preview(self, **kwargs: Any) -> str:
        """
        Generate human-readable preview of operation for approval prompt.

        Should format the operation in a way that allows the user to understand
        what will happen before approving. Include:
        - Tool name and description
        - Key parameters with values
        - Expected outcome

        Args:
            **kwargs: Parameters that will be passed to execute()

        Returns:
            Formatted preview string (multi-line)

        Example:
            >>> preview = file_write_tool.get_approval_preview(
            ...     filename="report.txt",
            ...     content="Hello World"
            ... )
            >>> print(preview)
            Tool: file_write
            Operation: Write content to a file
            Parameters:
              filename: report.txt
              content: Hello World (12 characters)
        """
        ...

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute the tool with provided parameters.

        This is the core method that performs the tool's action. Must be async
        to support I/O operations without blocking.

        The implementation should:
        1. Validate parameters (or assume validate_params was called)
        2. Perform the tool's action
        3. Catch exceptions and return error dict
        4. Return standardized result dictionary
        5. Log execution details

        Args:
            **kwargs: Tool-specific parameters matching parameters_schema

        Returns:
            Dictionary with at minimum:
            - success: bool - True if execution succeeded, False otherwise

            On success, additional fields based on tool:
            - output: str - Primary output (file content, command output, etc.)
            - result: Any - Structured result data
            - metadata: Dict - Additional execution metadata

            On failure:
            - error: str - Error message
            - error_type: str - Exception class name (optional)
            - traceback: str - Full traceback (optional, for debugging)

        Example:
            >>> result = await file_read_tool.execute(filename="data.txt")
            >>> if result["success"]:
            ...     print(result["output"])
            ... else:
            ...     print(f"Error: {result['error']}")

        Error Handling:
            Prefer returning {"success": False, "error": "..."} over raising
            exceptions. This allows agents to handle errors gracefully and
            potentially retry with different parameters.
        """
        ...

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """
        Validate parameters before execution.

        Checks that:
        - All required parameters are provided
        - Parameter types match schema (basic validation)
        - Enum values are valid (if applicable)

        This is a lightweight validation. Full type checking is handled by
        Pydantic models or execute() implementation.

        Args:
            **kwargs: Parameters to validate

        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
            - (True, None) if valid
            - (False, "error message") if invalid

        Example:
            >>> valid, error = tool.validate_params(filename="data.txt")
            >>> if not valid:
            ...     print(f"Validation error: {error}")
            >>> else:
            ...     result = await tool.execute(filename="data.txt")

        Default Implementation:
            Can use inspect.signature() to check for required parameters:
            - Iterate over execute() method parameters
            - Check if required params (no default) are in kwargs
            - Return (False, "Missing required parameter: X") if missing
        """
        ...
