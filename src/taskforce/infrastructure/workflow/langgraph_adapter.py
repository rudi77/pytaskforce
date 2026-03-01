"""LangGraph adapter for the WorkflowEngineProtocol.

Maps LangGraph's ``interrupt()`` / ``Command(resume=...)`` mechanism to
Taskforce's ``HumanInputRequest`` / resume pattern.

Requires the optional ``workflow`` dependency group::

    uv sync --extra workflow
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from taskforce.core.domain.workflow import (
    HumanInputRequest,
    WorkflowRunResult,
    WorkflowStatus,
)

logger = structlog.get_logger(__name__)

# LangGraph is an optional dependency.
try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.errors import GraphInterrupt
    from langgraph.types import Command, interrupt  # noqa: F401

    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False
    GraphInterrupt = None  # type: ignore[assignment,misc]
    Command = None  # type: ignore[assignment,misc]
    MemorySaver = None  # type: ignore[assignment,misc]


def _require_langgraph() -> None:
    if not HAS_LANGGRAPH:
        raise ImportError("LangGraph is not installed. " "Install with: uv sync --extra workflow")


class LangGraphAdapter:
    """Adapts a compiled LangGraph ``StateGraph`` to ``WorkflowEngineProtocol``.

    The adapter uses LangGraph's built-in ``MemorySaver`` checkpointer
    and maps ``GraphInterrupt`` exceptions to ``WAITING_FOR_INPUT`` results.
    On resume it feeds the human response back via ``Command(resume=...)``.
    """

    def __init__(self) -> None:
        _require_langgraph()
        self._checkpointer = MemorySaver()
        self._graphs: dict[str, Any] = {}

    @property
    def engine_name(self) -> str:
        """Engine identifier."""
        return "langgraph"

    async def start(
        self,
        *,
        run_id: str,
        workflow_definition: Any,
        input_data: dict[str, Any],
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]],
    ) -> WorkflowRunResult:
        """Start a LangGraph workflow.

        Args:
            run_id: Unique run identifier (used as LangGraph thread_id).
            workflow_definition: A compiled ``StateGraph``. If it does not
                already have a checkpointer, one will be assigned.
            input_data: Input state for the graph.
            tool_executor: Callback to execute Taskforce tools.

        Returns:
            WorkflowRunResult.
        """
        _require_langgraph()

        graph = self._prepare_graph(run_id, workflow_definition, tool_executor)
        config = {"configurable": {"thread_id": run_id}}

        try:
            result = await graph.ainvoke(input_data, config)
            return WorkflowRunResult(
                status=WorkflowStatus.COMPLETED,
                outputs=dict(result) if isinstance(result, dict) else {"result": result},
            )
        except GraphInterrupt as exc:
            return self._handle_interrupt(run_id, exc)
        except Exception as exc:
            logger.error("langgraph.start_failed", run_id=run_id, error=str(exc))
            return WorkflowRunResult(
                status=WorkflowStatus.FAILED,
                error=str(exc),
            )

    async def resume(
        self,
        *,
        run_id: str,
        checkpoint: dict[str, Any],
        response: str,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]],
    ) -> WorkflowRunResult:
        """Resume a paused LangGraph workflow with human response.

        Args:
            run_id: The run identifier.
            checkpoint: Previously saved checkpoint (used to restore
                MemorySaver state if the adapter was recreated).
            response: Human's response text.
            tool_executor: Callback to execute Taskforce tools.

        Returns:
            WorkflowRunResult (may pause again or complete).
        """
        _require_langgraph()

        # Restore checkpoint state if adapter was recreated (e.g. after restart).
        self._restore_checkpoint_if_needed(run_id, checkpoint)

        graph = self._graphs.get(run_id)
        if graph is None:
            return WorkflowRunResult(
                status=WorkflowStatus.FAILED,
                error=f"No graph found for run {run_id}. "
                "The workflow definition must be reloaded after restart.",
            )

        config = {"configurable": {"thread_id": run_id}}

        try:
            result = await graph.ainvoke(Command(resume=response), config)
            return WorkflowRunResult(
                status=WorkflowStatus.COMPLETED,
                outputs=dict(result) if isinstance(result, dict) else {"result": result},
            )
        except GraphInterrupt as exc:
            return self._handle_interrupt(run_id, exc)
        except Exception as exc:
            logger.error("langgraph.resume_failed", run_id=run_id, error=str(exc))
            return WorkflowRunResult(
                status=WorkflowStatus.FAILED,
                error=str(exc),
            )

    def get_checkpoint(self, run_id: str) -> dict[str, Any]:
        """Get serializable checkpoint data from MemorySaver."""
        try:
            config = {"configurable": {"thread_id": run_id}}
            cp = self._checkpointer.get(config)
            if cp is not None:
                return {
                    "thread_id": run_id,
                    "checkpoint": cp,
                }
        except Exception:
            logger.debug("langgraph.checkpoint_get_failed", run_id=run_id)
        return {"thread_id": run_id}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prepare_graph(
        self,
        run_id: str,
        workflow_definition: Any,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]],
    ) -> Any:
        """Compile or reuse a graph with checkpointer and tool executor."""
        # If the graph doesn't have a checkpointer, recompile with ours.
        graph = workflow_definition
        if not getattr(graph, "checkpointer", None):
            # The definition is a compiled graph; we need to recompile with
            # our checkpointer. LangGraph's CompiledStateGraph exposes
            # ``builder`` for this.
            builder = getattr(graph, "builder", None)
            if builder is not None:
                graph = builder.compile(checkpointer=self._checkpointer)
            else:
                # Fallback: assign checkpointer directly (works for most cases).
                graph.checkpointer = self._checkpointer

        # Store the tool_executor on the graph's config for node access.
        # Nodes can retrieve it via ``config["tool_executor"]``.
        graph._taskforce_tool_executor = tool_executor

        self._graphs[run_id] = graph
        return graph

    def _handle_interrupt(
        self,
        run_id: str,
        exc: Exception,
    ) -> WorkflowRunResult:
        """Convert a GraphInterrupt into a WAITING_FOR_INPUT result."""
        # GraphInterrupt.args[0] is the interrupt value passed by the node.
        interrupt_value = exc.args[0] if exc.args else {}
        if isinstance(interrupt_value, list) and len(interrupt_value) > 0:
            # LangGraph wraps interrupt values in a list of Interrupt objects.
            first = interrupt_value[0]
            interrupt_value = getattr(first, "value", first)

        if isinstance(interrupt_value, dict):
            hir = HumanInputRequest(
                question=str(interrupt_value.get("question", "")),
                channel=interrupt_value.get("channel"),
                recipient_id=interrupt_value.get("recipient_id"),
                timeout_seconds=interrupt_value.get("timeout_seconds"),
                metadata={
                    k: v
                    for k, v in interrupt_value.items()
                    if k not in ("question", "channel", "recipient_id", "timeout_seconds")
                },
            )
        else:
            hir = HumanInputRequest(question=str(interrupt_value))

        logger.info(
            "langgraph.interrupted",
            run_id=run_id,
            channel=hir.channel,
            recipient_id=hir.recipient_id,
        )
        return WorkflowRunResult(
            status=WorkflowStatus.WAITING_FOR_INPUT,
            human_input_request=hir,
        )

    def _restore_checkpoint_if_needed(self, run_id: str, checkpoint: dict[str, Any]) -> None:
        """Restore MemorySaver state from a persisted checkpoint dict."""
        saved_cp = checkpoint.get("checkpoint")
        if saved_cp is None:
            return
        try:
            config = {"configurable": {"thread_id": run_id}}
            existing = self._checkpointer.get(config)
            if existing is None:
                self._checkpointer.put(config, saved_cp, {}, {})
        except Exception:
            logger.debug("langgraph.checkpoint_restore_failed", run_id=run_id)
