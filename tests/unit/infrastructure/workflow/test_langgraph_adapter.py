"""Tests for LangGraphAdapter.

Since LangGraph is an optional dependency, these tests mock the LangGraph
internals and verify the adapter's mapping logic (interrupt handling,
checkpoint save/restore, graph lifecycle).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.workflow import (
    WorkflowStatus,
)


def _make_adapter() -> Any:
    """Create a LangGraphAdapter with mocked LangGraph internals."""
    # We need to import conditionally since langgraph may not be installed
    try:
        from taskforce.infrastructure.workflow.langgraph_adapter import (
            HAS_LANGGRAPH,
            LangGraphAdapter,
        )

        if not HAS_LANGGRAPH:
            pytest.skip("langgraph not installed")
        return LangGraphAdapter()
    except ImportError:
        pytest.skip("langgraph not installed")


async def _noop_executor(name: str, params: dict[str, Any]) -> Any:
    return {"success": True}


class TestLangGraphAdapterStart:
    """Tests for starting workflows via the adapter."""

    @pytest.mark.asyncio
    async def test_start_completed(self) -> None:
        adapter = _make_adapter()
        graph = MagicMock()
        graph.checkpointer = MagicMock()
        graph.ainvoke = AsyncMock(return_value={"booking_id": "B-001"})

        result = await adapter.start(
            run_id="run-1",
            workflow_definition=graph,
            input_data={"file_path": "/tmp/test.pdf"},
            tool_executor=_noop_executor,
        )
        assert result.status == WorkflowStatus.COMPLETED
        assert result.outputs["booking_id"] == "B-001"
        # Graph should be cleaned up after completion
        assert "run-1" not in adapter._graphs

    @pytest.mark.asyncio
    async def test_start_failed(self) -> None:
        adapter = _make_adapter()
        graph = MagicMock()
        graph.checkpointer = MagicMock()
        graph.ainvoke = AsyncMock(side_effect=RuntimeError("engine error"))

        result = await adapter.start(
            run_id="run-1",
            workflow_definition=graph,
            input_data={},
            tool_executor=_noop_executor,
        )
        assert result.status == WorkflowStatus.FAILED
        assert "engine error" in result.error
        # Graph should be cleaned up after failure
        assert "run-1" not in adapter._graphs

    @pytest.mark.asyncio
    async def test_start_interrupt_dict(self) -> None:
        """Test that GraphInterrupt with dict value maps to HumanInputRequest."""
        try:
            from langgraph.errors import GraphInterrupt
        except ImportError:
            pytest.skip("langgraph not installed")

        adapter = _make_adapter()
        graph = MagicMock()
        graph.checkpointer = MagicMock()
        interrupt_value = {
            "question": "Missing tax number?",
            "channel": "telegram",
            "recipient_id": "sup_123",
        }
        graph.ainvoke = AsyncMock(side_effect=GraphInterrupt(interrupt_value))

        result = await adapter.start(
            run_id="run-1",
            workflow_definition=graph,
            input_data={},
            tool_executor=_noop_executor,
        )
        assert result.status == WorkflowStatus.WAITING_FOR_INPUT
        assert result.human_input_request is not None
        assert result.human_input_request.question == "Missing tax number?"
        assert result.human_input_request.channel == "telegram"
        assert result.human_input_request.recipient_id == "sup_123"
        # Graph should be kept for resume
        assert "run-1" in adapter._graphs

    @pytest.mark.asyncio
    async def test_start_interrupt_string(self) -> None:
        """Test that GraphInterrupt with plain string maps correctly."""
        try:
            from langgraph.errors import GraphInterrupt
        except ImportError:
            pytest.skip("langgraph not installed")

        adapter = _make_adapter()
        graph = MagicMock()
        graph.checkpointer = MagicMock()
        graph.ainvoke = AsyncMock(side_effect=GraphInterrupt("Please approve"))

        result = await adapter.start(
            run_id="run-1",
            workflow_definition=graph,
            input_data={},
            tool_executor=_noop_executor,
        )
        assert result.status == WorkflowStatus.WAITING_FOR_INPUT
        assert result.human_input_request.question == "Please approve"
        assert result.human_input_request.channel is None


class TestLangGraphAdapterResume:
    """Tests for resuming workflows."""

    @pytest.mark.asyncio
    async def test_resume_no_graph(self) -> None:
        adapter = _make_adapter()
        result = await adapter.resume(
            run_id="nonexistent",
            checkpoint={},
            response="yes",
            tool_executor=_noop_executor,
        )
        assert result.status == WorkflowStatus.FAILED
        assert "No graph found" in result.error

    @pytest.mark.asyncio
    async def test_resume_completed(self) -> None:
        adapter = _make_adapter()
        graph = MagicMock()
        graph.checkpointer = MagicMock()
        graph.ainvoke = AsyncMock(return_value={"result": "done"})
        adapter._graphs["run-1"] = graph

        result = await adapter.resume(
            run_id="run-1",
            checkpoint={"thread_id": "run-1"},
            response="approved",
            tool_executor=_noop_executor,
        )
        assert result.status == WorkflowStatus.COMPLETED
        assert "run-1" not in adapter._graphs  # Cleaned up


class TestLangGraphAdapterCheckpoint:
    """Tests for checkpoint operations."""

    def test_get_checkpoint_no_data(self) -> None:
        adapter = _make_adapter()
        cp = adapter.get_checkpoint("run-1")
        assert cp == {"thread_id": "run-1"}

    def test_register_graph(self) -> None:
        adapter = _make_adapter()
        graph = MagicMock()
        graph.checkpointer = MagicMock()
        adapter.register_graph("run-1", graph, _noop_executor)
        assert "run-1" in adapter._graphs
