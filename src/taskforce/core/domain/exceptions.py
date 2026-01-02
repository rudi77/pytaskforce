"""Domain-specific execution exceptions with structured context."""

from __future__ import annotations

from typing import Any

from taskforce.core.domain.errors import TaskforceError


class TaskforceExecutionError(TaskforceError):
    """Base exception for execution failures with structured context."""

    def __init__(
        self,
        message: str,
        *,
        session_id: str | None = None,
        tool_name: str | None = None,
        error_code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = dict(details or {})
        if session_id:
            error_details.setdefault("session_id", session_id)
        if tool_name:
            error_details.setdefault("tool_name", tool_name)
        if error_code:
            error_details.setdefault("error_code", error_code)

        super().__init__(
            message=message,
            code=error_code or "execution_error",
            details=error_details,
            status_code=status_code,
        )
        self.session_id = session_id
        self.tool_name = tool_name
        self.error_code = error_code


class AgentExecutionError(TaskforceExecutionError):
    """Execution error tied to the legacy Agent flow."""

    def __init__(
        self,
        message: str,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        tool_name: str | None = None,
        error_code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = dict(details or {})
        if agent_id:
            error_details.setdefault("agent_id", agent_id)
        super().__init__(
            message,
            session_id=session_id,
            tool_name=tool_name,
            error_code=error_code,
            status_code=status_code,
            details=error_details,
        )
        self.agent_id = agent_id
        self.lean_agent_id = None


class LeanAgentExecutionError(TaskforceExecutionError):
    """Execution error tied to the LeanAgent flow."""

    def __init__(
        self,
        message: str,
        *,
        session_id: str | None = None,
        lean_agent_id: str | None = None,
        tool_name: str | None = None,
        error_code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = dict(details or {})
        if lean_agent_id:
            error_details.setdefault("lean_agent_id", lean_agent_id)
        super().__init__(
            message,
            session_id=session_id,
            tool_name=tool_name,
            error_code=error_code,
            status_code=status_code,
            details=error_details,
        )
        self.agent_id = None
        self.lean_agent_id = lean_agent_id
