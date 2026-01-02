"""
Unit tests for OpenAIService (LLM Provider).

Tests cover:
- Configuration loading and validation
- Model alias resolution
- Parameter mapping (GPT-4 vs GPT-5)
- Retry logic with exponential backoff
- Azure provider initialization
- Error handling and parsing
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from taskforce.infrastructure.llm.openai_service import OpenAIService, RetryPolicy


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary LLM config file for testing."""
    config = {
        "default_model": "main",
        "models": {
            "main": "gpt-4.1",
            "fast": "gpt-4.1-mini",
            "powerful": "gpt-5",
        },
        "model_params": {
            "gpt-4.1": {"temperature": 0.2, "max_tokens": 2000},
            "gpt-4.1-mini": {"temperature": 0.7, "max_tokens": 1500},
            "gpt-5": {"effort": "medium", "reasoning": "balanced", "max_tokens": 4000},
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


class TestOpenAIServiceInitialization:
    """Test OpenAIService initialization and configuration loading."""

    def test_initialization_success(self, temp_config_file):
        """Test successful service initialization."""
        service = OpenAIService(config_path=temp_config_file)

        assert service.default_model == "main"
        assert "main" in service.models
        assert "fast" in service.models
        assert service.retry_policy.max_attempts == 3

    def test_initialization_missing_config_file(self):
        """Test initialization fails with missing config file."""
        with pytest.raises(FileNotFoundError, match="LLM config not found"):
            OpenAIService(config_path="nonexistent_config.yaml")

    def test_initialization_empty_config(self, tmp_path):
        """Test initialization fails with empty config."""
        empty_config_path = tmp_path / "empty_config.yaml"
        empty_config_path.write_text("")

        with pytest.raises(ValueError, match="empty or invalid"):
            OpenAIService(config_path=str(empty_config_path))

    def test_initialization_missing_models_section(self, tmp_path):
        """Test initialization fails without models section."""
        config = {"default_model": "main", "retry_policy": {}}
        config_path = tmp_path / "no_models.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        with pytest.raises(ValueError, match="must define at least one model"):
            OpenAIService(config_path=str(config_path))


class TestModelResolution:
    """Test model alias resolution."""

    def test_resolve_model_with_alias(self, temp_config_file):
        """Test resolving model alias to actual model name."""
        service = OpenAIService(config_path=temp_config_file)

        resolved = service._resolve_model("main")
        assert resolved == "gpt-4.1"

        resolved = service._resolve_model("fast")
        assert resolved == "gpt-4.1-mini"

    def test_resolve_model_default(self, temp_config_file):
        """Test resolving None to default model."""
        service = OpenAIService(config_path=temp_config_file)

        resolved = service._resolve_model(None)
        assert resolved == "gpt-4.1"  # main alias resolves to gpt-4.1

    def test_resolve_model_unknown_alias(self, temp_config_file):
        """Test resolving unknown alias returns alias as-is."""
        service = OpenAIService(config_path=temp_config_file)

        resolved = service._resolve_model("unknown-model")
        assert resolved == "unknown-model"


class TestParameterMapping:
    """Test parameter mapping for different model families."""

    def test_map_parameters_gpt4(self, temp_config_file):
        """Test parameter mapping for GPT-4 models."""
        service = OpenAIService(config_path=temp_config_file)

        params = {
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 1000,
            "frequency_penalty": 0.1,
            "presence_penalty": 0.2,
            "extra_param": "ignored",
        }

        mapped = service._map_parameters_for_model("gpt-4.1", params)

        assert "temperature" in mapped
        assert "top_p" in mapped
        assert "max_tokens" in mapped
        assert "frequency_penalty" in mapped
        assert "presence_penalty" in mapped
        assert "extra_param" not in mapped

    def test_map_parameters_gpt5_temperature_to_effort(self, temp_config_file):
        """Test temperature is mapped to effort for GPT-5."""
        service = OpenAIService(config_path=temp_config_file)

        # Low temperature -> low effort
        params = {"temperature": 0.2, "max_tokens": 1000}
        mapped = service._map_parameters_for_model("gpt-5", params)
        assert mapped["effort"] == "low"
        assert "temperature" not in mapped

        # Medium temperature -> medium effort
        params = {"temperature": 0.5, "max_tokens": 1000}
        mapped = service._map_parameters_for_model("gpt-5", params)
        assert mapped["effort"] == "medium"

        # High temperature -> high effort
        params = {"temperature": 0.9, "max_tokens": 1000}
        mapped = service._map_parameters_for_model("gpt-5", params)
        assert mapped["effort"] == "high"

    def test_map_parameters_gpt5_explicit_effort(self, temp_config_file):
        """Test explicit effort parameter for GPT-5."""
        service = OpenAIService(config_path=temp_config_file)

        params = {"effort": "high", "reasoning": "detailed", "max_tokens": 2000}
        mapped = service._map_parameters_for_model("gpt-5", params)

        assert mapped["effort"] == "high"
        assert mapped["reasoning"] == "detailed"
        assert mapped["max_tokens"] == 2000

    def test_map_parameters_gpt5_ignores_deprecated(self, temp_config_file):
        """Test GPT-5 ignores deprecated GPT-4 parameters."""
        service = OpenAIService(config_path=temp_config_file)

        params = {
            "temperature": 0.7,
            "top_p": 0.9,
            "frequency_penalty": 0.1,
            "max_tokens": 1000,
        }

        mapped = service._map_parameters_for_model("gpt-5", params)

        # Only effort (mapped from temperature) and max_tokens should be present
        assert "effort" in mapped
        assert "max_tokens" in mapped
        assert "temperature" not in mapped
        assert "top_p" not in mapped
        assert "frequency_penalty" not in mapped


class TestModelParameters:
    """Test model-specific parameter retrieval."""

    def test_get_model_parameters_exact_match(self, temp_config_file):
        """Test getting parameters for exact model match."""
        service = OpenAIService(config_path=temp_config_file)

        params = service._get_model_parameters("gpt-4.1")
        assert params["temperature"] == 0.2
        assert params["max_tokens"] == 2000

    def test_get_model_parameters_family_match(self, temp_config_file):
        """Test getting parameters for model family match."""
        service = OpenAIService(config_path=temp_config_file)

        # gpt-4.1-turbo should match gpt-4.1 family
        params = service._get_model_parameters("gpt-4.1-turbo")
        assert params["temperature"] == 0.2
        assert params["max_tokens"] == 2000

    def test_get_model_parameters_default_fallback(self, temp_config_file):
        """Test fallback to default parameters for unknown model."""
        service = OpenAIService(config_path=temp_config_file)

        params = service._get_model_parameters("unknown-model")
        assert params["temperature"] == 0.7  # default
        assert params["max_tokens"] == 2000  # default


@pytest.mark.asyncio
class TestCompletion:
    """Test LLM completion functionality."""

    async def test_complete_success(self, temp_config_file):
        """Test successful completion."""
        service = OpenAIService(config_path=temp_config_file)

        # Mock LiteLLM response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Test response"))
        ]
        mock_response.usage = MagicMock(
            total_tokens=100, prompt_tokens=50, completion_tokens=50
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            result = await service.complete(
                messages=[{"role": "user", "content": "Hello"}],
                model="main",
                temperature=0.7,
            )

            assert result["success"] is True
            assert result["content"] == "Test response"
            assert result["usage"]["total_tokens"] == 100
            assert "latency_ms" in result

    async def test_complete_with_retry_success(self, temp_config_file):
        """Test completion succeeds after retry."""
        service = OpenAIService(config_path=temp_config_file)

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Success after retry"))
        ]
        mock_response.usage = MagicMock(
            total_tokens=50, prompt_tokens=25, completion_tokens=25
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            # First attempt fails with rate limit, second succeeds
            mock_completion.side_effect = [
                Exception("RateLimitError: Too many requests"),
                mock_response,
            ]

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await service.complete(
                    messages=[{"role": "user", "content": "Test"}], model="main"
                )

                assert result["success"] is True
                assert result["content"] == "Success after retry"
                assert mock_completion.call_count == 2

    async def test_complete_max_retries_exceeded(self, temp_config_file):
        """Test completion fails after max retries."""
        service = OpenAIService(config_path=temp_config_file)

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.side_effect = Exception(
                "RateLimitError: Too many requests"
            )

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await service.complete(
                    messages=[{"role": "user", "content": "Test"}], model="main"
                )

                assert result["success"] is False
                assert "error" in result
                assert mock_completion.call_count == 3  # max_attempts

    async def test_complete_non_retryable_error(self, temp_config_file):
        """Test completion fails immediately on non-retryable error."""
        service = OpenAIService(config_path=temp_config_file)

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.side_effect = Exception("InvalidRequest: Bad input")

            result = await service.complete(
                messages=[{"role": "user", "content": "Test"}], model="main"
            )

            assert result["success"] is False
            assert "InvalidRequest" in result["error"]
            assert mock_completion.call_count == 1  # No retry


@pytest.mark.asyncio
class TestGenerate:
    """Test generate convenience method."""

    async def test_generate_without_context(self, temp_config_file):
        """Test generate with simple prompt."""
        service = OpenAIService(config_path=temp_config_file)

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Generated text"))
        ]
        mock_response.usage = MagicMock(
            total_tokens=50, prompt_tokens=25, completion_tokens=25
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            result = await service.generate(
                prompt="Explain quantum computing", model="fast", max_tokens=500
            )

            assert result["success"] is True
            assert result["generated_text"] == "Generated text"
            assert result["content"] == "Generated text"

    async def test_generate_with_context(self, temp_config_file):
        """Test generate with structured context."""
        service = OpenAIService(config_path=temp_config_file)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary"))]
        mock_response.usage = MagicMock(
            total_tokens=50, prompt_tokens=25, completion_tokens=25
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            result = await service.generate(
                prompt="Summarize the data",
                context={"data": [1, 2, 3, 4, 5]},
                model="fast",
            )

            assert result["success"] is True
            # Check that context was included in the call
            call_args = mock_completion.call_args
            messages = call_args[1]["messages"]
            assert "Context:" in messages[0]["content"]
            assert "data:" in messages[0]["content"]


class TestAzureProvider:
    """Test Azure OpenAI provider functionality."""

    def test_azure_config_validation_success(self, temp_azure_config_file):
        """Test Azure config validation with valid config."""
        # Set required environment variables
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        ):
            service = OpenAIService(config_path=temp_azure_config_file)
            assert service.azure_api_key == "test-key"
            assert service.azure_endpoint == "https://test.openai.azure.com/"

    def test_azure_config_validation_missing_fields(self, tmp_path):
        """Test Azure config validation fails with missing fields."""
        config = {
            "default_model": "main",
            "models": {"main": "gpt-4.1"},
            "default_params": {},
            "retry_policy": {},
            "providers": {
                "azure": {
                    "enabled": True,
                    "api_key_env": "AZURE_OPENAI_API_KEY",
                    # Missing endpoint_url_env, api_version, deployment_mapping
                }
            },
        }

        config_path = tmp_path / "invalid_azure.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        with pytest.raises(ValueError, match="missing required fields"):
            OpenAIService(config_path=str(config_path))

    def test_azure_model_resolution(self, temp_azure_config_file):
        """Test model resolution with Azure deployment mapping."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        ):
            service = OpenAIService(config_path=temp_azure_config_file)

            resolved = service._resolve_model("main")
            assert resolved == "azure/gpt-4.1-deployment"

            resolved = service._resolve_model("fast")
            assert resolved == "azure/gpt-4.1-mini-deployment"

    def test_azure_model_resolution_missing_deployment(self, temp_azure_config_file):
        """Test Azure model resolution fails for unmapped alias."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        ):
            service = OpenAIService(config_path=temp_azure_config_file)

            with pytest.raises(ValueError, match="no deployment mapping found"):
                service._resolve_model("unknown-alias")

    def test_azure_endpoint_validation_https(self, temp_azure_config_file):
        """Test Azure endpoint must use HTTPS."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "http://test.openai.azure.com/",  # HTTP not HTTPS
            },
        ):
            with pytest.raises(ValueError, match="must use HTTPS protocol"):
                OpenAIService(config_path=temp_azure_config_file)


class TestAzureErrorParsing:
    """Test Azure error parsing and troubleshooting."""

    def test_parse_deployment_not_found_error(self, temp_azure_config_file):
        """Test parsing deployment not found error."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        ):
            service = OpenAIService(config_path=temp_azure_config_file)

            error = Exception(
                "DeploymentNotFound: deployment 'my-deployment' not found"
            )
            parsed = service._parse_azure_error(error)

            assert parsed["error_type"] == "Exception"
            assert "deployment_name" in parsed
            assert "hint" in parsed
            assert "Azure Portal" in parsed["hint"]

    def test_parse_authentication_error(self, temp_azure_config_file):
        """Test parsing authentication error."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        ):
            service = OpenAIService(config_path=temp_azure_config_file)

            error = Exception("AuthenticationError: Invalid API key")
            parsed = service._parse_azure_error(error)

            assert "hint" in parsed
            assert "AZURE_OPENAI_API_KEY" in parsed["hint"]

    def test_parse_rate_limit_error(self, temp_azure_config_file):
        """Test parsing rate limit error."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        ):
            service = OpenAIService(config_path=temp_azure_config_file)

            error = Exception("RateLimitError: Too many requests")
            parsed = service._parse_azure_error(error)

            assert "hint" in parsed
            assert "Rate limit" in parsed["hint"]


class TestRetryPolicy:
    """Test retry policy configuration."""

    def test_retry_policy_defaults(self):
        """Test RetryPolicy with default values."""
        policy = RetryPolicy()

        assert policy.max_attempts == 3
        assert policy.backoff_multiplier == 2.0
        assert policy.timeout == 30
        assert policy.retry_on_errors == []

    def test_retry_policy_custom_values(self):
        """Test RetryPolicy with custom values."""
        policy = RetryPolicy(
            max_attempts=5,
            backoff_multiplier=1.5,
            timeout=60,
            retry_on_errors=["RateLimitError", "Timeout"],
        )

        assert policy.max_attempts == 5
        assert policy.backoff_multiplier == 1.5
        assert policy.timeout == 60
        assert "RateLimitError" in policy.retry_on_errors


@pytest.mark.asyncio
class TestTracing:
    """Test LLM interaction tracing."""

    @pytest.fixture
    def tracing_config_file(self, tmp_path):
        """Create a config file with tracing enabled."""
        config = {
            "default_model": "main",
            "models": {"main": "gpt-4.1"},
            "providers": {"openai": {"api_key_env": "OPENAI_API_KEY"}},
            "tracing": {
                "enabled": True,
                "mode": "file",
                "file_config": {"path": str(tmp_path / "traces/llm_traces.jsonl")},
            },
            "logging": {},
            "retry_policy": {},
        }
        config_path = tmp_path / "llm_config_tracing.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        return str(config_path)

    async def test_tracing_enabled_file_mode(self, tracing_config_file):
        """Test tracing writes to file on success."""
        service = OpenAIService(config_path=tracing_config_file)

        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Traced response"))
        ]
        mock_response.usage = {"total_tokens": 10}

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            with patch.object(
                service, "_trace_to_file", new_callable=AsyncMock
            ) as mock_trace_file:
                await service.complete(
                    messages=[{"role": "user", "content": "Trace me"}], model="main"
                )

                # Yield to event loop to let create_task run
                await asyncio.sleep(0.1)

                mock_trace_file.assert_called_once()
                call_args = mock_trace_file.call_args[0][0]
                assert call_args["success"] is True
                assert call_args["response"] == "Traced response"

    async def test_tracing_failure(self, tracing_config_file):
        """Test tracing captures failures."""
        service = OpenAIService(config_path=tracing_config_file)

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.side_effect = Exception("Trace failure")

            with patch.object(
                service, "_trace_to_file", new_callable=AsyncMock
            ) as mock_trace_file:
                await service.complete(
                    messages=[{"role": "user", "content": "Fail me"}], model="main"
                )

                await asyncio.sleep(0.1)

                mock_trace_file.assert_called_once()
                call_args = mock_trace_file.call_args[0][0]
                assert call_args["success"] is False
                assert "Trace failure" in call_args["error"]

    async def test_trace_to_file_implementation(self, tracing_config_file, tmp_path):
        """Test actual file writing."""
        service = OpenAIService(config_path=tracing_config_file)
        trace_data = {"test": "data"}

        await service._trace_to_file(trace_data)

        trace_path = tmp_path / "traces/llm_traces.jsonl"
        assert trace_path.exists()
        content = trace_path.read_text(encoding="utf-8")
        assert '{"test": "data"}' in content

    async def test_tracing_disabled(self, tmp_path):
        """Test tracing does nothing when disabled."""
        config = {
            "default_model": "main",
            "models": {"main": "gpt-4.1"},
            "providers": {"openai": {"api_key_env": "OPENAI_API_KEY"}},
            "tracing": {"enabled": False},
            "retry_policy": {},
        }
        config_path = tmp_path / "llm_config_disabled.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        service = OpenAIService(config_path=str(config_path))

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="ok"))]
            )

            with patch.object(
                service, "_trace_to_file", new_callable=AsyncMock
            ) as mock_trace:
                await service.complete([], model="main")
                await asyncio.sleep(0.1)
                mock_trace.assert_not_called()
