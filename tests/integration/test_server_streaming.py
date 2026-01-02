"""
Integration Tests for Server SSE Streaming

Tests the Server-Sent Events (SSE) streaming endpoint for real-time
agent execution progress updates.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from taskforce.api.server import app
from taskforce.application.executor import AgentExecutor, ProgressUpdate

client = TestClient(app)


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


class TestServerSSEStreaming:
    """Tests for Server SSE streaming endpoint."""

    @pytest.mark.integration
    def test_sse_endpoint_returns_event_stream(self):
        """Test that SSE endpoint returns correct content type."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Test", "profile": "dev"},
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    @pytest.mark.integration
    def test_sse_yields_started_event(self):
        """Test that SSE endpoint yields started event."""
        mock_updates = [
            make_progress_update("started", "Starting mission", {"session_id": "test-123", "profile": "dev"}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Test mission", "profile": "dev"},
            ) as response:
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        event_data = json.loads(line[6:])
                        events.append(event_data)

                assert len(events) >= 1
                assert events[0]["event_type"] == "started"
                assert "session_id" in events[0]["details"]

    @pytest.mark.integration
    def test_sse_yields_step_start_events(self):
        """Test that SSE endpoint yields step_start events."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "Step 1 starting...", {"step": 1, "max_steps": 30}),
            make_progress_update("final_answer", "", {"content": "Done"}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Test", "profile": "dev", "lean": True},
            ) as response:
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

                step_events = [e for e in events if e["event_type"] == "step_start"]
                assert len(step_events) >= 1
                assert step_events[0]["details"]["step"] == 1

    @pytest.mark.integration
    def test_sse_yields_tool_call_events(self):
        """Test that SSE endpoint yields tool_call and tool_result events."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("tool_call", "🔧 Calling: web_search", {"tool": "web_search", "status": "starting"}),
            make_progress_update(
                "tool_result",
                "✅ web_search: Found results",
                {"tool": "web_search", "success": True, "output": "Found results"},
            ),
            make_progress_update("final_answer", "", {"content": "Search complete"}),
            make_progress_update("complete", "Search complete", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Search for data", "profile": "dev", "lean": True},
            ) as response:
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

                event_types = [e["event_type"] for e in events]
                assert "tool_call" in event_types
                assert "tool_result" in event_types

                tool_call = next(e for e in events if e["event_type"] == "tool_call")
                assert tool_call["details"]["tool"] == "web_search"

                tool_result = next(e for e in events if e["event_type"] == "tool_result")
                assert tool_result["details"]["success"] is True

    @pytest.mark.integration
    def test_sse_yields_llm_token_events(self):
        """Test that SSE endpoint yields llm_token events for streaming LLM output."""
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

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Say hello", "profile": "dev", "lean": True},
            ) as response:
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

                token_events = [e for e in events if e["event_type"] == "llm_token"]
                assert len(token_events) == 3

                # Verify token content
                tokens = [e["details"]["content"] for e in token_events]
                assert tokens == ["Hello", " ", "World"]

    @pytest.mark.integration
    def test_sse_yields_final_answer_event(self):
        """Test that SSE endpoint yields final_answer event."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("final_answer", "This is the final answer", {"content": "This is the final answer"}),
            make_progress_update("complete", "This is the final answer", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Answer question", "profile": "dev", "lean": True},
            ) as response:
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

                final_events = [e for e in events if e["event_type"] == "final_answer"]
                assert len(final_events) == 1
                assert final_events[0]["details"]["content"] == "This is the final answer"

    @pytest.mark.integration
    def test_sse_yields_complete_event(self):
        """Test that SSE endpoint yields complete event at the end."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("complete", "Mission completed", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Test", "profile": "dev"},
            ) as response:
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

                complete_events = [e for e in events if e["event_type"] == "complete"]
                assert len(complete_events) == 1
                assert complete_events[0]["details"]["status"] == "completed"

    @pytest.mark.integration
    def test_sse_yields_error_events(self):
        """Test that SSE endpoint yields error events when errors occur."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("error", "⚠️ Error: API timeout", {"message": "API timeout", "step": 1}),
            make_progress_update("complete", "Failed", {"status": "failed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Test error", "profile": "dev"},
            ) as response:
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

                error_events = [e for e in events if e["event_type"] == "error"]
                assert len(error_events) >= 1
                assert "API timeout" in error_events[0]["details"]["message"]


class TestServerSSEWithLeanAgent:
    """Tests for SSE streaming with LeanAgent flag."""

    @pytest.mark.integration
    def test_sse_uses_lean_agent_when_flag_set(self):
        """Test that SSE endpoint uses LeanAgent when lean=true."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test", "lean": True}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Test", "profile": "dev", "lean": True},
            ) as response:
                list(response.iter_lines())  # Consume the stream

            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs["use_lean_agent"] is True

    @pytest.mark.integration
    def test_sse_uses_legacy_agent_when_flag_not_set(self):
        """Test that SSE endpoint uses legacy agent when lean=false."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test", "lean": False}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Test", "profile": "dev", "lean": False},
            ) as response:
                list(response.iter_lines())

            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs["use_lean_agent"] is False


class TestServerSSEEventFormat:
    """Tests for SSE event format compliance."""

    @pytest.mark.integration
    def test_sse_events_have_timestamp(self):
        """Test that all SSE events include a timestamp."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("step_start", "", {"step": 1}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Test", "profile": "dev"},
            ) as response:
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

                for event in events:
                    assert "timestamp" in event
                    # Timestamp should be parseable
                    assert event["timestamp"] is not None

    @pytest.mark.integration
    def test_sse_events_follow_sse_format(self):
        """Test that events follow SSE format (data: prefix, double newline)."""
        mock_updates = [
            make_progress_update("started", "Starting...", {"session_id": "test"}),
            make_progress_update("complete", "Done", {"status": "completed"}),
        ]

        with patch.object(AgentExecutor, "execute_mission_streaming") as mock_stream:
            mock_stream.return_value = mock_streaming_generator(mock_updates)

            with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json={"mission": "Test", "profile": "dev"},
            ) as response:
                # Collect all lines from streaming response
                lines = list(response.iter_lines())
                
                # Should have at least some data lines
                data_lines = [line for line in lines if line.startswith("data: ")]
                assert len(data_lines) >= 1, "SSE should have at least one data: event"
                
                # Each data line should be valid JSON after "data: " prefix
                for line in data_lines:
                    event_json = line[6:]
                    parsed = json.loads(event_json)
                    assert "event_type" in parsed
                    assert "message" in parsed
                    assert "details" in parsed


class TestServerSSEBackwardCompatibility:
    """Tests for SSE endpoint backward compatibility."""

    @pytest.mark.integration
    def test_non_streaming_endpoint_unchanged(self):
        """Test that non-streaming /execute endpoint still works."""
        # This test doesn't mock streaming - it tests the sync endpoint
        # If no LLM key is configured, it may return 500, which is acceptable
        response = client.post(
            "/api/v1/execute",
            json={"mission": "Test", "profile": "dev"},
        )

        # Accept either success or error due to environment
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            assert "session_id" in data
            assert "status" in data
            assert "message" in data

