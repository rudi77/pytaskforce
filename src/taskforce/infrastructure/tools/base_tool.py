"""Base tool class that reduces boilerplate for ToolProtocol implementations.

Provides:
- Class-level attributes for ``name``, ``description``, ``parameters_schema``
  instead of requiring ``@property`` methods on every tool.
- A default ``validate_params`` that checks required parameters from the schema.
- An ``_execute_safe`` wrapper that catches unexpected exceptions and returns
  a standardised error payload via ``tool_error_payload``.
- Sensible defaults for ``requires_approval``, ``approval_risk_level``,
  ``supports_parallelism``, and ``get_approval_preview``.

All existing tools that implement ``ToolProtocol`` directly continue to work
unchanged.  New tools can subclass ``BaseTool`` to avoid the repetitive
property boilerplate.

This class lives in the **infrastructure** layer and does NOT modify
``ToolProtocol`` in ``core/interfaces``.
"""

from __future__ import annotations

import structlog
from typing import Any

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel

logger = structlog.get_logger(__name__)

# Type mapping from JSON Schema type names to Python built-in types.
_JSON_SCHEMA_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


class BaseTool:
    """Convenience base class for tools that satisfy ``ToolProtocol``.

    Subclasses must set at minimum:
      - ``tool_name``  (``str``)
      - ``tool_description`` (``str``)
      - ``tool_parameters_schema`` (``dict``)

    And override ``_execute`` with the actual tool logic.

    The class exposes the standard ``ToolProtocol`` surface (``name``,
    ``description``, ``parameters_schema``, ``execute``, ``validate_params``,
    etc.) so instances are structurally compatible without inheriting from
    the protocol.
    """

    # ------------------------------------------------------------------ #
    # Subclass configuration (override these)
    # ------------------------------------------------------------------ #

    tool_name: str = ""
    """Unique snake_case identifier for the tool (e.g. ``"memory"``)."""

    tool_description: str = ""
    """Human-readable description used by the LLM for tool selection."""

    tool_parameters_schema: dict[str, Any] = {}
    """OpenAI function-calling compatible JSON Schema for parameters."""

    tool_requires_approval: bool = False
    """Whether the tool requires user approval before execution."""

    tool_approval_risk_level: ApprovalRiskLevel = ApprovalRiskLevel.LOW
    """Risk level shown in the approval prompt."""

    tool_supports_parallelism: bool = False
    """Whether this tool can safely run concurrently with others."""

    # ------------------------------------------------------------------ #
    # ToolProtocol-compatible properties
    # ------------------------------------------------------------------ #

    @property
    def name(self) -> str:
        """Return the tool name."""
        return self.tool_name

    @property
    def description(self) -> str:
        """Return the tool description."""
        return self.tool_description

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return the parameters JSON Schema."""
        return self.tool_parameters_schema

    @property
    def requires_approval(self) -> bool:
        """Return whether user approval is required."""
        return self.tool_requires_approval

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Return the risk level for approval prompts."""
        return self.tool_approval_risk_level

    @property
    def supports_parallelism(self) -> bool:
        """Return whether parallel execution is safe."""
        return self.tool_supports_parallelism

    # ------------------------------------------------------------------ #
    # Default implementations
    # ------------------------------------------------------------------ #

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate a human-readable preview of the operation.

        Builds a generic preview from the tool name and provided kwargs.
        Subclasses can override for more specific formatting.

        Args:
            **kwargs: Parameters that will be passed to ``execute()``.

        Returns:
            Formatted preview string.
        """
        lines = [f"Tool: {self.name}"]
        for key, value in kwargs.items():
            display_value = str(value)
            if len(display_value) > 120:
                display_value = display_value[:120] + "..."
            lines.append(f"  {key}: {display_value}")
        return "\n".join(lines)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters against ``parameters_schema``.

        Checks that:
        - All ``required`` parameters are present.
        - Parameter types match the schema (basic type check).
        - Enum values are valid when specified.

        Args:
            **kwargs: Parameters to validate.

        Returns:
            ``(True, None)`` when valid, ``(False, "error message")`` otherwise.
        """
        schema = self.parameters_schema
        if not schema:
            return True, None

        required = schema.get("required", [])
        properties = schema.get("properties", {})

        # Check required parameters are present.
        for param_name in required:
            if param_name not in kwargs:
                return False, f"Missing required parameter: {param_name}"

        # Validate types and enum values for provided parameters.
        for param_name, value in kwargs.items():
            if param_name not in properties:
                continue

            prop_schema = properties[param_name]

            # Type check
            expected_type_name = prop_schema.get("type")
            if expected_type_name and value is not None:
                expected_types = _JSON_SCHEMA_TYPE_MAP.get(expected_type_name)
                if expected_types and not isinstance(value, expected_types):
                    return (
                        False,
                        f"Parameter '{param_name}' must be a {expected_type_name}",
                    )

            # Enum check
            allowed_values = prop_schema.get("enum")
            if allowed_values is not None and value not in allowed_values:
                return (
                    False,
                    f"Parameter '{param_name}' must be one of {allowed_values}",
                )

        return True, None

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the tool, delegating to ``_execute`` with error handling.

        Subclasses should override ``_execute`` rather than this method.
        If a subclass needs full control over error handling it can override
        ``execute`` directly instead.

        Args:
            **kwargs: Tool-specific parameters matching ``parameters_schema``.

        Returns:
            Standardised result dictionary with at least a ``success`` key.
        """
        return await self._execute_safe(**kwargs)

    async def _execute(self, **kwargs: Any) -> dict[str, Any]:
        """Actual tool logic to be implemented by subclasses.

        Args:
            **kwargs: Tool-specific parameters.

        Returns:
            Result dictionary.  Must include ``success: bool``.

        Raises:
            Any exception -- will be caught by ``_execute_safe`` and
            converted to a standardised error payload.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _execute()"
        )

    async def _execute_safe(self, **kwargs: Any) -> dict[str, Any]:
        """Call ``_execute`` and convert unexpected exceptions to error payloads.

        This wrapper catches any ``Exception`` raised by ``_execute`` and
        returns a standardised error dictionary produced by
        ``tool_error_payload``, so the agent always receives a well-formed
        response.

        Args:
            **kwargs: Forwarded to ``_execute``.

        Returns:
            Result dictionary from ``_execute`` on success, or a
            ``tool_error_payload`` dictionary on failure.
        """
        try:
            return await self._execute(**kwargs)
        except Exception as exc:
            logger.error(
                "tool.execute_failed",
                tool=self.name,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            tool_error = ToolError(
                f"{self.name} failed: {exc}",
                tool_name=self.name,
                details={"kwargs": _sanitize_kwargs(kwargs)},
            )
            return tool_error_payload(tool_error)


def _sanitize_kwargs(kwargs: dict[str, Any], max_str_len: int = 200) -> dict[str, Any]:
    """Create a loggable copy of kwargs with long strings truncated.

    Prevents enormous values (e.g. file content) from ending up in error
    payloads or log lines.

    Args:
        kwargs: Original keyword arguments.
        max_str_len: Maximum length for string values before truncation.

    Returns:
        Sanitised shallow copy.
    """
    sanitized: dict[str, Any] = {}
    for key, value in kwargs.items():
        if isinstance(value, str) and len(value) > max_str_len:
            sanitized[key] = value[:max_str_len] + "..."
        else:
            sanitized[key] = value
    return sanitized
