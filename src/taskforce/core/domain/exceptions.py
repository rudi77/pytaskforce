"""Domain-specific exception types with structured context."""

from __future__ import annotations


class TaskforceExecutionError(Exception):
    """Base exception for execution failures with structured context."""

    def __init__(
        self,
        message: str,
        *,
        session_id: str | None = None,
        tool_name: str | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
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
    ) -> None:
        super().__init__(
            message,
            session_id=session_id,
            tool_name=tool_name,
            error_code=error_code,
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
    ) -> None:
        super().__init__(
            message,
            session_id=session_id,
            tool_name=tool_name,
            error_code=error_code,
        )
        self.agent_id = None
        self.lean_agent_id = lean_agent_id
