"""
Unit tests for LLM Provider Streaming functionality.

Tests cover:
- Token streaming with real-time delivery
- Tool call streaming (start → delta → end sequence)
- Done event with usage statistics
- Error handling (yields error events, no exceptions)
- Backward compatibility (existing complete() method unchanged)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from taskforce.infrastructure.llm.openai_service import OpenAIService


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary LLM config file for testing."""
    config = {
        "default_model": "main",
        "models": {
            "main": "gpt-4.1",
            "fast": "gpt-4.1-mini",
        },
        "model_params": {
            "gpt-4.1": {"temperature": 0.2, "max_tokens": 2000},
            "gpt-4.1-mini": {"temperature": 0.7, "max_tokens": 1500},
        },
        "default_params": {
            "temperature": 0.7,
            "max_tokens": 2000,
        },
        "retry_policy": {
            "max_attempts": 3,
            "backoff_multiplier": 2,
            "timeout": 30,
            "retry_on_errors": ["RateLimitError", "Timeout"],
        },
        "providers": {
            "openai": {"api_key_env": "OPENAI_API_KEY"},
            "azure": {"enabled": False},
        },
        "logging": {
            "log_token_usage": True,
            "log_parameter_mapping": True,
        },
    }

    config_path = tmp_path / "llm_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    return str(config_path)


@pytest.fixture
def temp_azure_config_file(tmp_path):
    """Create a temporary LLM config file with Azure enabled."""
    config = {
        "default_model": "main",
        "models": {
            "main": "gpt-4.1",
            "fast": "gpt-4.1-mini",
        },
        "model_params": {
            "gpt-4.1": {"temperature": 0.2, "max_tokens": 2000},
        },
        "default_params": {"temperature": 0.7, "max_tokens": 2000},
        "retry_policy": {
            "max_attempts": 3,
            "backoff_multiplier": 2,
            "timeout": 30,
            "retry_on_errors": ["RateLimitError"],
        },
        "providers": {
            "openai": {"api_key_env": "OPENAI_API_KEY"},
            "azure": {
                "enabled": True,
                "api_key_env": "AZURE_OPENAI_API_KEY",
                "endpoint_url_env": "AZURE_OPENAI_ENDPOINT",
                "api_version": "2024-02-15-preview",
                "deployment_mapping": {
                    "main": "gpt-4.1-deployment",
                    "fast": "gpt-4.1-mini-deployment",
                },
            },
        },
        "logging": {"log_token_usage": True},
    }

    config_path = tmp_path / "llm_config_azure.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    return str(config_path)


def create_mock_chunk(content=None, tool_calls=None, finish_reason=None):
    """Helper to create mock streaming chunks."""
    chunk = MagicMock()
    delta = MagicMock()

    # Set content
    delta.content = content

    # Set tool_calls
    if tool_calls:
        delta.tool_calls = tool_calls
    else:
        delta.tool_calls = None

    chunk.choices = [MagicMock(delta=delta, finish_reason=finish_reason)]
    return chunk


def create_mock_tool_call(index, tool_id=None, name=None, arguments=None):
    """Helper to create mock tool call delta."""
    tc = MagicMock()
    tc.index = index
    tc.id = tool_id

    if name or arguments:
        tc.function = MagicMock()
        tc.function.name = name
        tc.function.arguments = arguments
    else:
        tc.function = None

    return tc


async def mock_stream_generator(chunks):
    """Create an async generator from a list of chunks."""
    for chunk in chunks:
        yield chunk


@pytest.mark.asyncio
class TestCompleteStreamTokens:
    """Test token streaming functionality."""

    async def test_complete_stream_yields_tokens(self, temp_config_file):
        """Test that token chunks are yielded correctly."""
        service = OpenAIService(config_path=temp_config_file)

        # Create mock chunks with token content
        chunks = [
            create_mock_chunk(content="Hello"),
            create_mock_chunk(content=" world"),
            create_mock_chunk(content="!"),
            create_mock_chunk(finish_reason="stop"),
        ]

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_stream_generator(chunks)

            events = []
            async for event in service.complete_stream(
                messages=[{"role": "user", "content": "Say hello"}],
                model="main",
            ):
                events.append(event)

            # Verify token events
            token_events = [e for e in events if e["type"] == "token"]
            assert len(token_events) == 3
            assert token_events[0]["content"] == "Hello"
            assert token_events[1]["content"] == " world"
            assert token_events[2]["content"] == "!"

            # Verify done event
            done_events = [e for e in events if e["type"] == "done"]
            assert len(done_events) == 1
            assert "usage" in done_events[0]

    async def test_complete_stream_empty_content_ignored(self, temp_config_file):
        """Test that empty content chunks are handled gracefully."""
        service = OpenAIService(config_path=temp_config_file)

        chunks = [
            create_mock_chunk(content="Hello"),
            create_mock_chunk(content=None),  # Empty content
            create_mock_chunk(content=""),  # Empty string
            create_mock_chunk(content="World"),
            create_mock_chunk(finish_reason="stop"),
        ]

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_stream_generator(chunks)

            events = []
            async for event in service.complete_stream(
                messages=[{"role": "user", "content": "Test"}],
                model="main",
            ):
                events.append(event)

            # Only non-empty tokens should be yielded
            token_events = [e for e in events if e["type"] == "token"]
            assert len(token_events) == 2
            assert token_events[0]["content"] == "Hello"
            assert token_events[1]["content"] == "World"


@pytest.mark.asyncio
class TestCompleteStreamToolCalls:
    """Test tool call streaming functionality."""

    async def test_complete_stream_yields_tool_calls(self, temp_config_file):
        """Test that tool calls are streamed correctly."""
        service = OpenAIService(config_path=temp_config_file)

        # Create mock chunks with tool call
        chunks = [
            create_mock_chunk(
                tool_calls=[create_mock_tool_call(0, "call_123", "get_weather", None)]
            ),
            create_mock_chunk(
                tool_calls=[create_mock_tool_call(0, None, None, '{"city":')]
            ),
            create_mock_chunk(
                tool_calls=[create_mock_tool_call(0, None, None, '"NYC"}')]
            ),
            create_mock_chunk(finish_reason="tool_calls"),
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_stream_generator(chunks)

            events = []
            async for event in service.complete_stream(
                messages=[{"role": "user", "content": "Weather in NYC?"}],
                model="main",
                tools=tools,
            ):
                events.append(event)

            # Verify tool call start
            start_events = [e for e in events if e["type"] == "tool_call_start"]
            assert len(start_events) == 1
            assert start_events[0]["id"] == "call_123"
            assert start_events[0]["name"] == "get_weather"
            assert start_events[0]["index"] == 0

            # Verify tool call deltas
            delta_events = [e for e in events if e["type"] == "tool_call_delta"]
            assert len(delta_events) == 2
            assert delta_events[0]["arguments_delta"] == '{"city":'
            assert delta_events[1]["arguments_delta"] == '"NYC"}'

            # Verify tool call end
            end_events = [e for e in events if e["type"] == "tool_call_end"]
            assert len(end_events) == 1
            assert end_events[0]["id"] == "call_123"
            assert end_events[0]["name"] == "get_weather"
            assert end_events[0]["arguments"] == '{"city":"NYC"}'
            assert end_events[0]["index"] == 0

            # Verify done event
            assert events[-1]["type"] == "done"

    async def test_complete_stream_multiple_tool_calls(self, temp_config_file):
        """Test streaming multiple parallel tool calls."""
        service = OpenAIService(config_path=temp_config_file)

        # Create mock chunks with multiple tool calls
        chunks = [
            create_mock_chunk(
                tool_calls=[
                    create_mock_tool_call(0, "call_1", "tool_a", None),
                    create_mock_tool_call(1, "call_2", "tool_b", None),
                ]
            ),
            create_mock_chunk(
                tool_calls=[
                    create_mock_tool_call(0, None, None, '{"a":1}'),
                    create_mock_tool_call(1, None, None, '{"b":2}'),
                ]
            ),
            create_mock_chunk(finish_reason="tool_calls"),
        ]

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_stream_generator(chunks)

            events = []
            async for event in service.complete_stream(
                messages=[{"role": "user", "content": "Test"}],
                model="main",
                tools=[{"type": "function", "function": {"name": "tool_a"}}],
            ):
                events.append(event)

            # Should have 2 start events, 2 delta events, 2 end events
            start_events = [e for e in events if e["type"] == "tool_call_start"]
            end_events = [e for e in events if e["type"] == "tool_call_end"]

            assert len(start_events) == 2
            assert len(end_events) == 2

            # Verify both tool calls completed
            end_ids = {e["id"] for e in end_events}
            assert end_ids == {"call_1", "call_2"}


@pytest.mark.asyncio
class TestCompleteStreamDoneEvent:
    """Test done event and usage statistics."""

    async def test_complete_stream_done_event_with_usage(self, temp_config_file):
        """Test that done event includes usage statistics when available."""
        service = OpenAIService(config_path=temp_config_file)

        chunks = [
            create_mock_chunk(content="Response"),
            create_mock_chunk(finish_reason="stop"),
        ]

        # Create a custom wrapper class that has usage attribute
        class MockStreamResponse:
            def __init__(self, chunks):
                self._chunks = chunks
                self.usage = MagicMock(
                    total_tokens=100, prompt_tokens=50, completion_tokens=50
                )

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self._chunks:
                    raise StopAsyncIteration
                return self._chunks.pop(0)

        mock_response = MockStreamResponse(chunks.copy())

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            events = []
            async for event in service.complete_stream(
                messages=[{"role": "user", "content": "Test"}],
                model="main",
            ):
                events.append(event)

            done_event = [e for e in events if e["type"] == "done"][0]
            assert done_event["type"] == "done"
            assert "usage" in done_event

    async def test_complete_stream_done_event_without_usage(self, temp_config_file):
        """Test that done event works even without usage data."""
        service = OpenAIService(config_path=temp_config_file)

        chunks = [
            create_mock_chunk(content="Response"),
            create_mock_chunk(finish_reason="stop"),
        ]

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_stream_generator(chunks)

            events = []
            async for event in service.complete_stream(
                messages=[{"role": "user", "content": "Test"}],
                model="main",
            ):
                events.append(event)

            done_event = [e for e in events if e["type"] == "done"][0]
            assert done_event["type"] == "done"
            assert done_event["usage"] == {}  # Empty dict when not available


@pytest.mark.asyncio
class TestCompleteStreamErrorHandling:
    """Test error handling - yields error events, no exceptions raised."""

    async def test_complete_stream_api_error_yields_error_event(self, temp_config_file):
        """Test that API errors yield error events instead of raising."""
        service = OpenAIService(config_path=temp_config_file)

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.side_effect = Exception("API Error: Rate limit exceeded")

            events = []
            # Should NOT raise - should yield error event
            async for event in service.complete_stream(
                messages=[{"role": "user", "content": "Test"}],
                model="main",
            ):
                events.append(event)

            # Should have exactly one error event
            assert len(events) == 1
            assert events[0]["type"] == "error"
            assert "Rate limit exceeded" in events[0]["message"]

    async def test_complete_stream_model_resolution_error(self, temp_azure_config_file):
        """Test that model resolution errors yield error events."""
        import os

        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        ):
            service = OpenAIService(config_path=temp_azure_config_file)

            events = []
            # Unknown model alias should fail for Azure
            async for event in service.complete_stream(
                messages=[{"role": "user", "content": "Test"}],
                model="unknown-alias",
            ):
                events.append(event)

            assert len(events) == 1
            assert events[0]["type"] == "error"
            assert "no deployment mapping found" in events[0]["message"]

    async def test_complete_stream_no_exception_propagation(self, temp_config_file):
        """Test that exceptions during streaming are caught and yielded."""
        service = OpenAIService(config_path=temp_config_file)

        # Create generator that raises mid-stream
        async def failing_generator():
            yield create_mock_chunk(content="Hello")
            raise Exception("Mid-stream failure")

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = failing_generator()

            events = []
            # Should NOT raise
            async for event in service.complete_stream(
                messages=[{"role": "user", "content": "Test"}],
                model="main",
            ):
                events.append(event)

            # Should have token event then error event
            assert any(e["type"] == "token" for e in events)
            assert events[-1]["type"] == "error"
            assert "Mid-stream failure" in events[-1]["message"]


@pytest.mark.asyncio
class TestCompleteStreamBackwardCompatibility:
    """Test that existing complete() method remains unchanged."""

    async def test_complete_still_works(self, temp_config_file):
        """Test that non-streaming complete() method works as before."""
        service = OpenAIService(config_path=temp_config_file)

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Test response", tool_calls=None))
        ]
        mock_response.usage = MagicMock(
            total_tokens=100, prompt_tokens=50, completion_tokens=50
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            result = await service.complete(
                messages=[{"role": "user", "content": "Hello"}],
                model="main",
            )

            assert result["success"] is True
            assert result["content"] == "Test response"
            assert "latency_ms" in result

    async def test_complete_with_tools_still_works(self, temp_config_file):
        """Test that complete() with native tool calling works as before."""
        service = OpenAIService(config_path=temp_config_file)

        # Mock tool call response - properly configure all attributes
        mock_function = MagicMock()
        mock_function.name = "get_weather"
        mock_function.arguments = '{"city":"NYC"}'

        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.type = "function"
        mock_tool_call.function = mock_function

        mock_message = MagicMock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(
            total_tokens=50, prompt_tokens=30, completion_tokens=20
        )

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            result = await service.complete(
                messages=[{"role": "user", "content": "Weather?"}],
                model="main",
                tools=tools,
            )

            assert result["success"] is True
            assert result["tool_calls"] is not None
            assert len(result["tool_calls"]) == 1
            assert result["tool_calls"][0]["function"]["name"] == "get_weather"

