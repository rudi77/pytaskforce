"""Protocols for resumable workflow engines.

Defines the contracts that any workflow engine (LangGraph, custom, etc.)
must implement to integrate with Taskforce's skill system, and the
persistence protocol for workflow run state.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from taskforce.core.domain.workflow import WorkflowRunRecord, WorkflowRunResult


class WorkflowEngineProtocol(Protocol):
    """Protocol for pluggable workflow engines.

    Implementations adapt external workflow engines (LangGraph, etc.)
    to Taskforce's resumable workflow mechanism. The engine is responsible
    for executing the workflow graph/steps and serializing its own
    checkpoint state for persistence.
    """

    @property
    def engine_name(self) -> str:
        """Engine identifier (e.g. 'langgraph')."""
        ...

    async def start(
        self,
        *,
        run_id: str,
        workflow_definition: Any,
        input_data: dict[str, Any],
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]],
    ) -> WorkflowRunResult:
        """Start a workflow execution.

        Args:
            run_id: Unique identifier for this run.
            workflow_definition: Engine-specific workflow object
                (e.g. compiled LangGraph graph).
            input_data: Input variables for the workflow.
            tool_executor: Callback to execute Taskforce tools by name.

        Returns:
            WorkflowRunResult with status COMPLETED, WAITING_FOR_INPUT,
            or FAILED.
        """
        ...

    async def resume(
        self,
        *,
        run_id: str,
        checkpoint: dict[str, Any],
        response: str,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]],
    ) -> WorkflowRunResult:
        """Resume a paused workflow with human response.

        Args:
            run_id: The run identifier (same as used in start).
            checkpoint: Previously saved engine checkpoint state.
            response: Human's response text.
            tool_executor: Callback to execute Taskforce tools by name.

        Returns:
            WorkflowRunResult (may pause again or complete).
        """
        ...

    def get_checkpoint(self, run_id: str) -> dict[str, Any]:
        """Get serializable checkpoint for the current run state.

        Args:
            run_id: The run identifier.

        Returns:
            JSON-serializable dictionary capturing the engine's
            internal state for later resume.
        """
        ...


class WorkflowRunStoreProtocol(Protocol):
    """Persistence protocol for workflow run state.

    Stores workflow run records so that paused workflows can be
    resumed after process restarts or long waits.
    """

    async def save(self, record: WorkflowRunRecord) -> None:
        """Save or update a workflow run record.

        Args:
            record: The workflow run record to persist.
        """
        ...

    async def load(self, run_id: str) -> WorkflowRunRecord | None:
        """Load a workflow run record by run ID.

        Args:
            run_id: The unique run identifier.

        Returns:
            The record, or None if not found.
        """
        ...

    async def load_by_session(self, session_id: str) -> WorkflowRunRecord | None:
        """Load the active workflow run for a session.

        Returns the most recent WAITING_FOR_INPUT run for the session.

        Args:
            session_id: The agent session identifier.

        Returns:
            The record, or None if no active workflow for this session.
        """
        ...

    async def delete(self, run_id: str) -> None:
        """Delete a workflow run record.

        Args:
            run_id: The run identifier to delete.
        """
        ...

    async def list_waiting(self) -> list[WorkflowRunRecord]:
        """List all workflow runs currently waiting for input.

        Returns:
            List of records with status WAITING_FOR_INPUT.
        """
        ...
