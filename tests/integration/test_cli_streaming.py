"""
Integration Tests for CLI Streaming

Tests the CLI streaming integration including the --stream flag
and Rich Live Display functionality.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from taskforce.api.cli.commands.run import _execute_streaming_mission
from taskforce.application.executor import AgentExecutor, ProgressUpdate


def make_progress_update(
    event_type: str,
    message: str = "",
    details: dict = None,
) -> ProgressUpdate:
    """Helper to create a ProgressUpdate for testing."""
    return ProgressUpdate(
        timestamp=datetime.now(),
        event_type=event_type,
        message=message,
        details=details or {},
    )


async def mock_streaming_generator(updates: list[ProgressUpdate]):
    """Create an async generator from a list of updates."""
    for update in updates:
        yield update


class TestCLIStreamingFlag:
    """Tests for CLI --stream flag functionality."""

    @pytest.mark.asyncio
    async def test_streaming_displays_step_progress(self):
        """Test that step progress is displayed during streaming."""
        mock_updates = [
            make_progress_update("started", "Starting mission...", {"session_id": "test"}),
            make_progress_update("step_start", "Step 1 starting...", {"step": 1}),
            make_progress_update("final_answer", "", {"content": "Task completed"}),
            make_progress_update("complete", "Task completed", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            console = Console(force_terminal=True, width=120)
            
            # Execute streaming mission - should not raise
            await _execute_streaming_mission(
                mission="Test mission",
                profile="dev",
                session_id=None,
                lean=True,
                console=console,
            )

            # Verify streaming was called
            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs["mission"] == "Test mission"
            assert call_kwargs["use_lean_agent"] is True

    @pytest.mark.asyncio
    async def test_streaming_displays_tool_calls(self):
        """Test that tool calls are displayed during streaming."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("tool_call", "🔧 Calling: web_search", {"tool": "web_search"}),
            make_progress_update(
                "tool_result",
                "✅ web_search: Results found",
                {"tool": "web_search", "success": True, "output": "Results found"},
            ),
            make_progress_update("final_answer", "", {"content": "Done"}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            console = Console(force_terminal=True, width=120)
            
            await _execute_streaming_mission(
                mission="Search and analyze",
                profile="dev",
                session_id=None,
                lean=True,
                console=console,
            )

            mock_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_streaming_collects_tokens(self):
        """Test that LLM tokens are collected for display."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("llm_token", "Hello", {"content": "Hello"}),
            make_progress_update("llm_token", " ", {"content": " "}),
            make_progress_update("llm_token", "World", {"content": "World"}),
            make_progress_update("final_answer", "", {"content": "Hello World"}),
            make_progress_update("complete", "Hello World", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            console = Console(force_terminal=True, width=120)
            
            await _execute_streaming_mission(
                mission="Say hello",
                profile="dev",
                session_id=None,
                lean=True,
                console=console,
            )

            mock_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_streaming_handles_errors(self):
        """Test that error events are handled gracefully."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("error", "API error occurred", {"message": "API error occurred"}),
            make_progress_update("complete", "Failed", {"status": "failed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            console = Console(force_terminal=True, width=120)
            
            # Should complete without raising
            await _execute_streaming_mission(
                mission="Test error handling",
                profile="dev",
                session_id=None,
                lean=True,
                console=console,
            )

    @pytest.mark.asyncio
    async def test_streaming_handles_plan_updates(self):
        """Test that plan update events are displayed."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("plan_updated", "📋 Plan updated (create_plan)", {"action": "create_plan"}),
            make_progress_update("final_answer", "", {"content": "Plan created"}),
            make_progress_update("complete", "Plan created", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            console = Console(force_terminal=True, width=120)
            
            await _execute_streaming_mission(
                mission="Create a plan",
                profile="dev",
                session_id=None,
                lean=True,
                console=console,
            )

            mock_stream.assert_called_once()


class TestCLIStreamingMultipleToolCalls:
    """Tests for CLI streaming with multiple tool calls."""

    @pytest.mark.asyncio
    async def test_streaming_multiple_tool_results(self):
        """Test that multiple tool results are collected and displayed."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("tool_call", "", {"tool": "web_search"}),
            make_progress_update("tool_result", "", {"tool": "web_search", "success": True, "output": "Result 1"}),
            make_progress_update("step_start", "", {"step": 2}),
            make_progress_update("tool_call", "", {"tool": "web_fetch"}),
            make_progress_update("tool_result", "", {"tool": "web_fetch", "success": True, "output": "Result 2"}),
            make_progress_update("step_start", "", {"step": 3}),
            make_progress_update("tool_call", "", {"tool": "python"}),
            make_progress_update("tool_result", "", {"tool": "python", "success": True, "output": "Result 3"}),
            make_progress_update("final_answer", "", {"content": "All done"}),
            make_progress_update("complete", "All done", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            console = Console(force_terminal=True, width=120)
            
            await _execute_streaming_mission(
                mission="Multi-step task",
                profile="dev",
                session_id=None,
                lean=True,
                console=console,
            )

            mock_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_streaming_tool_failure(self):
        """Test that tool failures are displayed correctly."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("tool_call", "", {"tool": "web_fetch"}),
            make_progress_update(
                "tool_result",
                "",
                {"tool": "web_fetch", "success": False, "output": "Connection timeout"},
            ),
            make_progress_update("final_answer", "", {"content": "Failed to fetch"}),
            make_progress_update("complete", "Failed to fetch", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            console = Console(force_terminal=True, width=120)
            
            await _execute_streaming_mission(
                mission="Fetch data",
                profile="dev",
                session_id=None,
                lean=True,
                console=console,
            )

            mock_stream.assert_called_once()


class TestCLIStreamingBackwardCompatibility:
    """Tests for backward compatibility of CLI streaming."""

    @pytest.mark.asyncio
    async def test_streaming_with_legacy_agent(self):
        """Test that streaming works with legacy agent events (thought/observation)."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("thought", "Step 1: Analyzing", {"rationale": "Analyzing"}),
            make_progress_update("observation", "Step 1: success", {"success": True}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            console = Console(force_terminal=True, width=120)
            
            await _execute_streaming_mission(
                mission="Legacy test",
                profile="dev",
                session_id=None,
                lean=False,  # Use legacy agent
                console=console,
            )

            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs["use_lean_agent"] is False

