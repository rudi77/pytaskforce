"""
Tool Result Data Types

Defines typed data structures for tool execution results,
replacing Dict[str, Any] with concrete types.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """
    Structured result from tool execution.

    Replaces Dict[str, Any] for tool return values with a typed dataclass.

    Attributes:
        success: Whether the tool execution succeeded.
        output: Primary output string (file content, command output, etc.).
        message: Human-readable status message.
        error: Error message if execution failed.
        error_type: Exception class name for debugging.
        metadata: Additional execution metadata (optional).
    """

    success: bool
    output: str = ""
    message: str = ""
    error: str = ""
    error_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for backward compatibility.

        Returns:
            Dictionary representation of the result.
        """
        result: dict[str, Any] = {"success": self.success}
        if self.output:
            result["output"] = self.output
        if self.message:
            result["message"] = self.message
        if self.error:
            result["error"] = self.error
        if self.error_type:
            result["error_type"] = self.error_type
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolResult":
        """
        Create ToolResult from dictionary.

        Args:
            data: Dictionary with tool result data.

        Returns:
            ToolResult instance.
        """
        return cls(
            success=data.get("success", False),
            output=data.get("output", ""),
            message=data.get("message", ""),
            error=data.get("error", ""),
            error_type=data.get("error_type", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def success_result(
        cls,
        output: str = "",
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        """
        Create a successful result.

        Args:
            output: Primary output string.
            message: Human-readable success message.
            metadata: Additional metadata.

        Returns:
            ToolResult with success=True.
        """
        return cls(
            success=True,
            output=output,
            message=message,
            metadata=metadata or {},
        )

    @classmethod
    def error_result(
        cls,
        error: str,
        error_type: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        """
        Create a failed result.

        Args:
            error: Error message.
            error_type: Exception class name.
            metadata: Additional metadata.

        Returns:
            ToolResult with success=False.
        """
        return cls(
            success=False,
            error=error,
            error_type=error_type,
            metadata=metadata or {},
        )


@dataclass
class PlanTask:
    """
    A single task in a plan.

    Replaces Dict with "description" and "status" keys.
    """

    description: str
    status: str = "PENDING"

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for serialization."""
        return {"description": self.description, "status": self.status}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "PlanTask":
        """Create PlanTask from dictionary."""
        return cls(
            description=data.get("description", ""),
            status=data.get("status", "PENDING"),
        )
