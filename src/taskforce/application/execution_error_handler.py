"""Execution Error Handler - Extracted from AgentExecutor.

Handles error logging, exception wrapping, and error progress update
building for agent execution failures and cancellations.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog

from taskforce.application.executor import ProgressUpdate
from taskforce.core.domain.enums import EventType
from taskforce.core.domain.errors import (
    CancelledError,
    TaskforceError,
)
from taskforce.core.domain.exceptions import AgentExecutionError

logger = structlog.get_logger(__name__)


class ExecutionErrorHandler:
    """Handles error logging, wrapping, and progress update building."""

    def __init__(self) -> None:
        self._logger = logger.bind(component="execution_error_handler")

    def handle_cancellation(
        self,
        error: asyncio.CancelledError,
        session_id: str,
        agent_id: str | None,
        plugin_path: str | None,
    ) -> ProgressUpdate:
        """Log cancellation and build error update. Re-raises as CancelledError.

        Returns:
            ProgressUpdate with ERROR event type.

        Raises:
            CancelledError: Always re-raised with context.
        """
        self._logger.warning(
            "mission.streaming.cancelled",
            session_id=session_id,
            error=str(error),
            agent_id=agent_id,
            plugin_path=plugin_path,
        )

        update = ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            message=f"Execution cancelled: {error!s}",
            details={"error": str(error), "error_type": type(error).__name__},
        )

        raise CancelledError(
            f"Mission streaming cancelled: {error!s}",
            details={"session_id": session_id},
        ) from error

        return update  # noqa: B012 - unreachable but satisfies type checker

    def handle_streaming_failure(
        self,
        error: Exception,
        session_id: str,
        agent_id: str | None,
        plugin_path: str | None,
    ) -> tuple[ProgressUpdate, Exception]:
        """Log failure, build error update and wrapped exception.

        Returns:
            Tuple of (ProgressUpdate with ERROR event, wrapped exception).
        """
        self.log_execution_failure(
            event_name="mission.streaming.failed",
            error=error,
            session_id=session_id,
            agent_id=agent_id,
            plugin_path=plugin_path,
        )

        update = ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.ERROR,
            message=f"Execution failed: {error!s}",
            details={"error": str(error), "error_type": type(error).__name__},
        )

        wrapped = self.wrap_exception(
            error,
            context="Mission streaming failed",
            session_id=session_id,
            agent_id=agent_id,
        )

        return update, wrapped

    def log_execution_failure(
        self,
        event_name: str,
        error: Exception,
        session_id: str,
        agent_id: str | None,
        duration_seconds: float | None = None,
        plugin_path: str | None = None,
    ) -> None:
        """Log a structured execution failure event."""
        error_context = _extract_error_context(
            error=error, session_id=session_id, agent_id=agent_id
        )

        log_payload: dict[str, Any] = {
            "session_id": error_context["session_id"],
            "agent_id": error_context["agent_id"],
            "tool_name": error_context["tool_name"],
            "error_code": error_context["error_code"],
            "error": str(error),
            "error_type": type(error).__name__,
        }

        if duration_seconds is not None:
            log_payload["duration_seconds"] = duration_seconds
        if plugin_path is not None:
            log_payload["plugin_path"] = plugin_path

        self._logger.exception(event_name, **log_payload)

    @staticmethod
    def wrap_exception(
        error: Exception,
        *,
        context: str,
        session_id: str,
        agent_id: str | None,
    ) -> TaskforceError:
        """Wrap unknown exceptions into AgentExecutionError.

        Returns:
            TaskforceError (passthrough) or AgentExecutionError wrapper.
        """
        if isinstance(error, TaskforceError):
            return error
        if isinstance(error, asyncio.CancelledError):
            return CancelledError(
                f"{context}: {error!s}",
                details={"session_id": session_id},
            )
        error_context = _extract_error_context(
            error=error, session_id=session_id, agent_id=agent_id
        )
        details = {
            "session_id": error_context["session_id"],
            "agent_id": error_context["agent_id"],
            "tool_name": error_context["tool_name"],
            "error_code": error_context["error_code"],
            "error_type": type(error).__name__,
        }
        return AgentExecutionError(
            f"{context}: {error!s}",
            session_id=error_context["session_id"],
            agent_id=error_context["agent_id"] or agent_id,
            tool_name=error_context["tool_name"],
            error_code=error_context["error_code"],
            status_code=500,
            details=details,
        )


def _extract_error_context(
    error: Exception,
    session_id: str,
    agent_id: str | None,
) -> dict[str, str | None]:
    """Extract structured context from an exception for logging."""
    return {
        "session_id": getattr(error, "session_id", None) or session_id,
        "agent_id": getattr(error, "agent_id", None) or agent_id,
        "tool_name": getattr(error, "tool_name", None),
        "error_code": getattr(error, "error_code", None),
    }
