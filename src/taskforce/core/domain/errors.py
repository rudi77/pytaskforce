"""Domain-specific exception types for Taskforce."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class TaskforceError(Exception):
    """Base exception for Taskforce domain errors."""

    message: str
    code: str = "taskforce_error"
    details: Dict[str, Any] | None = None
    status_code: int | None = None

    def __post_init__(self) -> None:
        super().__init__(self.message)
        if self.details is None:
            self.details = {}


class LLMError(TaskforceError):
    """Error raised for LLM invocation failures."""

    def __init__(self, message: str, *, details: Dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="llm_error", details=details)


class ToolError(TaskforceError):
    """Error raised for tool invocation failures."""

    def __init__(
        self,
        message: str,
        *,
        tool_name: str | None = None,
        details: Dict[str, Any] | None = None,
    ) -> None:
        details = dict(details or {})
        if tool_name:
            details.setdefault("tool_name", tool_name)
        self.tool_name = tool_name
        super().__init__(message=message, code="tool_error", details=details)


class PlanningError(TaskforceError):
    """Error raised for planning failures."""

    def __init__(self, message: str, *, details: Dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="planning_error", details=details)


class ConfigError(TaskforceError):
    """Error raised for configuration failures."""

    def __init__(self, message: str, *, details: Dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="config_error", details=details)


class CancelledError(TaskforceError):
    """Error raised when execution is cancelled."""

    def __init__(self, message: str, *, details: Dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="cancelled", details=details)


class NotFoundError(TaskforceError):
    """Error raised when a resource is not found."""

    def __init__(self, message: str, *, details: Dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="not_found", details=details)


class ValidationError(TaskforceError):
    """Error raised for validation failures."""

    def __init__(self, message: str, *, details: Dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="validation_error", details=details)


def tool_error_payload(
    error: ToolError, extra: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Convert a ToolError into a standardized tool response payload."""
    payload = {
        "success": False,
        "error": str(error),
        "error_type": type(error).__name__,
        "details": error.details or {},
    }
    if extra:
        payload.update(extra)
    return payload
