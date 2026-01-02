"""Domain-specific error types for Taskforce."""

from __future__ import annotations

from typing import Any


class TaskforceError(Exception):
    """Base class for Taskforce domain/application errors."""

    default_code = "taskforce_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.details = details
        self.status_code = status_code


class PlanningError(TaskforceError):
    """Raised when planning or plan validation fails."""

    default_code = "planning_error"


class ConfigError(TaskforceError):
    """Raised when configuration is invalid or missing."""

    default_code = "config_error"


class ToolError(TaskforceError):
    """Raised when tool execution fails."""

    default_code = "tool_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        upstream: bool | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            details=details,
            status_code=status_code,
        )
        self.upstream = upstream


class CancelledError(TaskforceError):
    """Raised when execution is cancelled."""

    default_code = "cancelled_error"


class LLMError(TaskforceError):
    """Raised when LLM service fails."""

    default_code = "llm_error"
