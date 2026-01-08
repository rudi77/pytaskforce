"""
Unit tests for ZaiService (Zai LLM Provider).

Tests cover:
- Configuration loading and validation
- Model alias resolution
- Complete method (success/failure/retry)
- Generate method (convenience wrapper)
- Streaming method (tokens, tool calls, errors)
- Error handling
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from taskforce.infrastructure.llm.zai_service import ZaiService, RetryPolicy


@pytest.fixture
def temp_zai_config_file(tmp_path):
    """Create a temporary LLM config file with Zai provider."""
    config = {
        "default_model": "main",
        "models": {
            "main": "gpt-4.1",
            "fast": "gpt-4.1-mini",
            "powerful": "gpt-5",
        },
        "model_params": {
            "glm-4.7": {"temperature": 0.7, "max_tokens": 2000},
            "glm-4.7-flash": {"temperature": 0.9, "max_tokens": 1500},
        },
        "default_params": {
            "temperature": 1.0,
            "max_tokens": 1000,
        },
        "retry_policy": {
            "max_attempts": 3,
            "backoff_multiplier": 2,
            "timeout": 300,
            "connect_timeout": 8,
            "retry_on_errors": ["APIStatusError", "APITimeoutError"],
        },
        "providers": {
            "zai": {
                "api_key_env": "ZAI_API_KEY",
                "base_url": "https://api.z.ai/api/paas/v4/",
                "model_mapping": {
                    "main": "glm-4.7",
                    "fast": "glm-4.7-flash",
                    "powerful": "glm-4.9",
                },
            },
        },
        "logging": {"log_token_usage": True},
    }

    config_path = tmp_path / "zai_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    return str(config_path)


@pytest.fixture
def mock_zai_client():
    """Create a mock ZaiClient for testing."""
    mock_client = MagicMock()
    return mock_client


class TestZaiServiceInitialization:
    """Test ZaiService initialization and configuration loading."""

    def test_initialization_success(self, temp_zai_config_file):
        """Test successful service initialization."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            with patch("zai.ZaiClient"):
                service = ZaiService(config_path=temp_zai_config_file)

                assert service.default_model == "main"
                assert "main" in service.models
                assert service.retry_policy.max_attempts == 3
                assert service.api_key_env == "ZAI_API_KEY"
                assert service.base_url == "https://api.z.ai/api/paas/v4/"

    def test_initialization_missing_config_file(self):
        """Test initialization fails with missing config file."""
        with pytest.raises(FileNotFoundError, match="LLM config not found"):
            ZaiService(config_path="nonexistent_config.yaml")

    def test_initialization_empty_config(self, tmp_path):
        """Test initialization fails with empty config."""
        empty_config_path = tmp_path / "empty_config.yaml"
        empty_config_path.write_text("")

        with pytest.raises(ValueError, match="empty or invalid"):
            ZaiService(config_path=str(empty_config_path))

    def test_initialization_missing_models_section(self, tmp_path):
        """Test initialization fails without models section."""
        config = {"default_model": "main", "retry_policy": {}}
        config_path = tmp_path / "no_models.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        with pytest.raises(ValueError, match="must define at least one model"):
            ZaiService(config_path=str(config_path))

    def test_initialization_missing_api_key_warning(self, temp_zai_config_file, caplog):
        """Test warning when API key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove ZAI_API_KEY from environment
            os.environ.pop("ZAI_API_KEY", None)
            with patch("zai.ZaiClient"):
                # Should initialize but log a warning
                service = ZaiService(config_path=temp_zai_config_file)
                assert service is not None


class TestZaiModelResolution:
    """Test model alias resolution."""

    def test_resolve_model_with_alias(self, temp_zai_config_file):
        """Test resolving model alias to actual Zai model name."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            with patch("zai.ZaiClient"):
                service = ZaiService(config_path=temp_zai_config_file)

                # Should use Zai model mapping
                resolved = service._resolve_model("main")
                assert resolved == "glm-4.7"

                resolved = service._resolve_model("fast")
                assert resolved == "glm-4.7-flash"

    def test_resolve_model_with_none_uses_default(self, temp_zai_config_file):
        """Test resolving None model uses default."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            with patch("zai.ZaiClient"):
                service = ZaiService(config_path=temp_zai_config_file)

                resolved = service._resolve_model(None)
                # Default is "main" which maps to "glm-4.7"
                assert resolved == "glm-4.7"

    def test_resolve_model_direct_name(self, temp_zai_config_file):
        """Test resolving direct model name (not an alias)."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            with patch("zai.ZaiClient"):
                service = ZaiService(config_path=temp_zai_config_file)

                # Direct model name should be returned as-is
                resolved = service._resolve_model("glm-4.7")
                assert resolved == "glm-4.7"


class TestZaiParameterHandling:
    """Test parameter handling for Zai models."""

    def test_get_model_parameters_exact_match(self, temp_zai_config_file):
        """Test getting parameters for exact model match."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            with patch("zai.ZaiClient"):
                service = ZaiService(config_path=temp_zai_config_file)

                params = service._get_model_parameters("glm-4.7")
                assert params["temperature"] == 0.7
                assert params["max_tokens"] == 2000

    def test_get_model_parameters_fallback_to_defaults(self, temp_zai_config_file):
        """Test falling back to defaults for unknown model."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            with patch("zai.ZaiClient"):
                service = ZaiService(config_path=temp_zai_config_file)

                params = service._get_model_parameters("unknown-model")
                # Should use defaults (filtered to supported params)
                assert "temperature" in params
                assert "max_tokens" in params


@pytest.mark.asyncio
class TestZaiCompletion:
    """Test Zai completion functionality."""

    async def test_complete_success(self, temp_zai_config_file):
        """Test successful completion."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            # Mock ZaiClient
            mock_client = MagicMock()
            mock_message = MagicMock()
            mock_message.content = "Test response"
            mock_message.tool_calls = None

            mock_choice = MagicMock()
            mock_choice.message = mock_message

            mock_usage = MagicMock()
            mock_usage.total_tokens = 100
            mock_usage.prompt_tokens = 50
            mock_usage.completion_tokens = 50

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage

            mock_client.chat.completions.create.return_value = mock_response

            with patch("zai.ZaiClient", return_value=mock_client):
                service = ZaiService(config_path=temp_zai_config_file)

                result = await service.complete(
                    messages=[{"role": "user", "content": "Hello"}],
                    model="main",
                )

                assert result["success"] is True
                assert result["content"] == "Test response"
                assert result["usage"]["total_tokens"] == 100
                assert result["model"] == "glm-4.7"

    async def test_complete_with_tool_calls(self, temp_zai_config_file):
        """Test completion with tool calls."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            mock_client = MagicMock()

            # Mock tool call
            mock_function = MagicMock()
            mock_function.name = "get_weather"
            mock_function.arguments = '{"location": "Beijing"}'

            mock_tool_call = MagicMock()
            mock_tool_call.id = "call_123"
            mock_tool_call.type = "function"
            mock_tool_call.function = mock_function

            mock_message = MagicMock()
            mock_message.content = None
            mock_message.tool_calls = [mock_tool_call]

            mock_choice = MagicMock()
            mock_choice.message = mock_message

            mock_usage = MagicMock()
            mock_usage.total_tokens = 50
            mock_usage.prompt_tokens = 30
            mock_usage.completion_tokens = 20

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage

            mock_client.chat.completions.create.return_value = mock_response

            with patch("zai.ZaiClient", return_value=mock_client):
                service = ZaiService(config_path=temp_zai_config_file)

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

                result = await service.complete(
                    messages=[{"role": "user", "content": "Weather?"}],
                    model="main",
                    tools=tools,
                )

                assert result["success"] is True
                assert result["tool_calls"] is not None
                assert len(result["tool_calls"]) == 1
                assert result["tool_calls"][0]["function"]["name"] == "get_weather"

    async def test_complete_failure_no_retry(self, temp_zai_config_file):
        """Test completion failure without retry."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception("API Error")

            with patch("zai.ZaiClient", return_value=mock_client):
                service = ZaiService(config_path=temp_zai_config_file)

                result = await service.complete(
                    messages=[{"role": "user", "content": "Hello"}],
                    model="main",
                )

                assert result["success"] is False
                assert "API Error" in result["error"]
                assert result["error_type"] == "Exception"

    async def test_complete_retry_on_specific_error(self, temp_zai_config_file):
        """Test retry logic on specific error types."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            mock_client = MagicMock()

            # First call fails with retryable error, second succeeds
            mock_message = MagicMock()
            mock_message.content = "Success after retry"
            mock_message.tool_calls = None

            mock_choice = MagicMock()
            mock_choice.message = mock_message

            mock_usage = MagicMock()
            mock_usage.total_tokens = 100
            mock_usage.prompt_tokens = 50
            mock_usage.completion_tokens = 50

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage

            class APIStatusError(Exception):
                pass

            mock_client.chat.completions.create.side_effect = [
                APIStatusError("Rate limited"),
                mock_response,
            ]

            with patch("zai.ZaiClient", return_value=mock_client):
                service = ZaiService(config_path=temp_zai_config_file)

                result = await service.complete(
                    messages=[{"role": "user", "content": "Hello"}],
                    model="main",
                )

                assert result["success"] is True
                assert result["content"] == "Success after retry"


@pytest.mark.asyncio
class TestZaiGenerate:
    """Test Zai generate method."""

    async def test_generate_success(self, temp_zai_config_file):
        """Test successful text generation."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_message = MagicMock()
            mock_message.content = "Generated text"
            mock_message.tool_calls = None

            mock_choice = MagicMock()
            mock_choice.message = mock_message

            mock_usage = MagicMock()
            mock_usage.total_tokens = 50
            mock_usage.prompt_tokens = 25
            mock_usage.completion_tokens = 25

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage

            mock_client.chat.completions.create.return_value = mock_response

            with patch("zai.ZaiClient", return_value=mock_client):
                service = ZaiService(config_path=temp_zai_config_file)

                result = await service.generate(
                    prompt="Write a poem",
                    model="main",
                )

                assert result["success"] is True
                assert result["content"] == "Generated text"
                assert result["generated_text"] == "Generated text"

    async def test_generate_with_context(self, temp_zai_config_file):
        """Test generation with context."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_message = MagicMock()
            mock_message.content = "Generated with context"
            mock_message.tool_calls = None

            mock_choice = MagicMock()
            mock_choice.message = mock_message

            mock_usage = MagicMock()
            mock_usage.total_tokens = 50
            mock_usage.prompt_tokens = 25
            mock_usage.completion_tokens = 25

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage

            mock_client.chat.completions.create.return_value = mock_response

            with patch("zai.ZaiClient", return_value=mock_client):
                service = ZaiService(config_path=temp_zai_config_file)

                result = await service.generate(
                    prompt="Summarize this",
                    context={"data": [1, 2, 3]},
                    model="main",
                )

                assert result["success"] is True
                # Verify context was included in the call
                call_args = mock_client.chat.completions.create.call_args
                messages = call_args[1]["messages"]
                assert "Context:" in messages[0]["content"]


@pytest.mark.asyncio
class TestZaiStreaming:
    """Test Zai streaming functionality."""

    async def test_complete_stream_yields_tokens(self, temp_zai_config_file):
        """Test that token chunks are yielded correctly."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            mock_client = MagicMock()

            # Create mock chunks
            mock_delta1 = MagicMock()
            mock_delta1.content = "Hello "
            mock_delta1.tool_calls = None

            mock_delta2 = MagicMock()
            mock_delta2.content = "World"
            mock_delta2.tool_calls = None

            mock_choice1 = MagicMock()
            mock_choice1.delta = mock_delta1
            mock_choice1.finish_reason = None

            mock_choice2 = MagicMock()
            mock_choice2.delta = mock_delta2
            mock_choice2.finish_reason = "stop"

            mock_chunk1 = MagicMock()
            mock_chunk1.choices = [mock_choice1]

            mock_chunk2 = MagicMock()
            mock_chunk2.choices = [mock_choice2]

            # Mock streaming response as iterable
            mock_client.chat.completions.create.return_value = iter(
                [mock_chunk1, mock_chunk2]
            )

            with patch("zai.ZaiClient", return_value=mock_client):
                service = ZaiService(config_path=temp_zai_config_file)

                events = []
                async for event in service.complete_stream(
                    messages=[{"role": "user", "content": "Hello"}],
                    model="main",
                ):
                    events.append(event)

                # Should have token events and done event
                token_events = [e for e in events if e.get("type") == "token"]
                assert len(token_events) == 2
                assert token_events[0]["content"] == "Hello "
                assert token_events[1]["content"] == "World"

                done_events = [e for e in events if e.get("type") == "done"]
                assert len(done_events) == 1

    async def test_complete_stream_yields_error(self, temp_zai_config_file):
        """Test that errors are yielded as events."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception("Stream error")

            with patch("zai.ZaiClient", return_value=mock_client):
                service = ZaiService(config_path=temp_zai_config_file)

                events = []
                async for event in service.complete_stream(
                    messages=[{"role": "user", "content": "Hello"}],
                    model="main",
                ):
                    events.append(event)

                # Should have exactly one error event
                error_events = [e for e in events if e.get("type") == "error"]
                assert len(error_events) == 1
                assert "Stream error" in error_events[0]["message"]


class TestRetryPolicy:
    """Test RetryPolicy dataclass."""

    def test_default_values(self):
        """Test default retry policy values."""
        policy = RetryPolicy()

        assert policy.max_attempts == 3
        assert policy.backoff_multiplier == 2.0
        assert policy.timeout == 300.0
        assert policy.connect_timeout == 8.0
        assert policy.retry_on_errors == []

    def test_custom_values(self):
        """Test custom retry policy values."""
        policy = RetryPolicy(
            max_attempts=5,
            backoff_multiplier=1.5,
            timeout=60.0,
            connect_timeout=5.0,
            retry_on_errors=["RateLimitError"],
        )

        assert policy.max_attempts == 5
        assert policy.backoff_multiplier == 1.5
        assert policy.timeout == 60.0
        assert policy.connect_timeout == 5.0
        assert policy.retry_on_errors == ["RateLimitError"]
