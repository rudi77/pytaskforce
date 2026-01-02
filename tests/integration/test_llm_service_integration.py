"""
Integration tests for OpenAIService with actual LLM API calls.

These tests require:
- OPENAI_API_KEY environment variable set
- Active internet connection
- OpenAI API access

Tests are marked with @pytest.mark.integration and can be skipped with:
    pytest -m "not integration"
"""

import os
from pathlib import Path

import pytest
import yaml

from taskforce.infrastructure.llm.openai_service import OpenAIService


@pytest.fixture
def integration_config_file(tmp_path):
    """Create a config file for integration tests."""
    config = {
        "default_model": "fast",
        "models": {
            "main": "gpt-4.1",
            "fast": "gpt-4.1-mini",
        },
        "model_params": {
            "gpt-4.1": {"temperature": 0.2, "max_tokens": 100},
            "gpt-4.1-mini": {"temperature": 0.7, "max_tokens": 50},
        },
        "default_params": {"temperature": 0.7, "max_tokens": 100},
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
        "logging": {"log_token_usage": True, "log_parameter_mapping": True},
    }

    config_path = tmp_path / "integration_llm_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    return str(config_path)


@pytest.fixture
def skip_if_no_api_key():
    """Skip test if OPENAI_API_KEY is not set."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY environment variable not set")


@pytest.mark.asyncio
@pytest.mark.integration
class TestOpenAIServiceIntegration:
    """Integration tests with actual OpenAI API."""

    async def test_actual_completion_simple(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test actual LLM completion with simple prompt."""
        service = OpenAIService(config_path=integration_config_file)

        result = await service.complete(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'test passed' in exactly those words."},
            ],
            model="fast",
            max_tokens=10,
        )

        assert result["success"] is True
        assert "content" in result
        assert "test passed" in result["content"].lower()
        assert result["usage"]["total_tokens"] > 0
        assert result["latency_ms"] > 0

    async def test_actual_completion_with_parameters(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test actual completion with custom parameters."""
        service = OpenAIService(config_path=integration_config_file)

        result = await service.complete(
            messages=[
                {
                    "role": "user",
                    "content": "Count from 1 to 3, separated by commas.",
                }
            ],
            model="fast",
            temperature=0.1,  # Low temperature for deterministic output
            max_tokens=20,
        )

        assert result["success"] is True
        assert "content" in result
        # Should contain numbers 1, 2, 3
        content = result["content"].lower()
        assert "1" in content
        assert "2" in content
        assert "3" in content

    async def test_actual_generate_without_context(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test generate method with actual API."""
        service = OpenAIService(config_path=integration_config_file)

        result = await service.generate(
            prompt="What is 2+2? Answer with just the number.",
            model="fast",
            max_tokens=10,
        )

        assert result["success"] is True
        assert "generated_text" in result
        assert "4" in result["generated_text"]

    async def test_actual_generate_with_context(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test generate method with structured context."""
        service = OpenAIService(config_path=integration_config_file)

        result = await service.generate(
            prompt="What is the sum of all numbers in the data?",
            context={"data": [1, 2, 3, 4, 5]},
            model="fast",
            max_tokens=20,
        )

        assert result["success"] is True
        assert "generated_text" in result
        # Sum should be 15
        assert "15" in result["generated_text"]

    async def test_actual_completion_token_usage(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test token usage tracking in actual completion."""
        service = OpenAIService(config_path=integration_config_file)

        result = await service.complete(
            messages=[{"role": "user", "content": "Hello"}],
            model="fast",
            max_tokens=10,
        )

        assert result["success"] is True
        assert "usage" in result
        assert result["usage"]["total_tokens"] > 0
        assert result["usage"]["prompt_tokens"] > 0
        assert result["usage"]["completion_tokens"] > 0
        assert (
            result["usage"]["total_tokens"]
            == result["usage"]["prompt_tokens"] + result["usage"]["completion_tokens"]
        )

    async def test_actual_completion_multiple_messages(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test completion with conversation history."""
        service = OpenAIService(config_path=integration_config_file)

        result = await service.complete(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "My name is Alice."},
                {"role": "assistant", "content": "Hello Alice! Nice to meet you."},
                {"role": "user", "content": "What is my name?"},
            ],
            model="fast",
            max_tokens=20,
        )

        assert result["success"] is True
        assert "alice" in result["content"].lower()

    async def test_actual_completion_latency_measurement(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test latency measurement in actual completion."""
        service = OpenAIService(config_path=integration_config_file)

        result = await service.complete(
            messages=[{"role": "user", "content": "Hi"}],
            model="fast",
            max_tokens=5,
        )

        assert result["success"] is True
        assert "latency_ms" in result
        assert result["latency_ms"] > 0
        # Latency should be reasonable (less than 30 seconds)
        assert result["latency_ms"] < 30000


@pytest.mark.asyncio
@pytest.mark.integration
class TestOpenAIServiceErrorHandling:
    """Integration tests for error handling."""

    async def test_invalid_model_name(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test handling of invalid model name."""
        service = OpenAIService(config_path=integration_config_file)

        # Manually set an invalid model
        result = await service.complete(
            messages=[{"role": "user", "content": "Test"}],
            model="invalid-model-xyz",
            max_tokens=10,
        )

        assert result["success"] is False
        assert "error" in result
        assert "error_type" in result

    async def test_empty_messages_list(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test handling of empty messages list."""
        service = OpenAIService(config_path=integration_config_file)

        result = await service.complete(messages=[], model="fast", max_tokens=10)

        assert result["success"] is False
        assert "error" in result


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("AZURE_OPENAI_API_KEY") or not os.getenv("AZURE_OPENAI_ENDPOINT"),
    reason="Azure OpenAI credentials not configured",
)
class TestAzureOpenAIIntegration:
    """Integration tests for Azure OpenAI provider (optional)."""

    @pytest.fixture
    def azure_integration_config(self, tmp_path):
        """Create Azure config for integration tests."""
        config = {
            "default_model": "main",
            "models": {"main": "gpt-4.1", "fast": "gpt-4.1-mini"},
            "model_params": {
                "gpt-4.1": {"temperature": 0.2, "max_tokens": 100},
            },
            "default_params": {"temperature": 0.7, "max_tokens": 100},
            "retry_policy": {
                "max_attempts": 3,
                "backoff_multiplier": 2,
                "timeout": 30,
                "retry_on_errors": ["RateLimitError"],
            },
            "providers": {
                "azure": {
                    "enabled": True,
                    "api_key_env": "AZURE_OPENAI_API_KEY",
                    "endpoint_url_env": "AZURE_OPENAI_ENDPOINT",
                    "api_version": "2024-02-15-preview",
                    "deployment_mapping": {
                        "main": os.getenv(
                            "AZURE_DEPLOYMENT_MAIN", "gpt-4.1"
                        ),  # Allow override
                        "fast": os.getenv("AZURE_DEPLOYMENT_FAST", "gpt-4.1-mini"),
                    },
                }
            },
            "logging": {"log_token_usage": True},
        }

        config_path = tmp_path / "azure_integration_config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        return str(config_path)

    async def test_azure_actual_completion(self, azure_integration_config):
        """Test actual completion with Azure OpenAI."""
        service = OpenAIService(config_path=azure_integration_config)

        result = await service.complete(
            messages=[
                {"role": "user", "content": "Say 'azure test passed' exactly."}
            ],
            model="main",
            max_tokens=10,
        )

        assert result["success"] is True
        assert "azure test passed" in result["content"].lower()
        assert result["model"].startswith("azure/")

    async def test_azure_connection_test(self, azure_integration_config):
        """Test Azure connection diagnostic method."""
        service = OpenAIService(config_path=azure_integration_config)

        result = await service.test_azure_connection()

        assert "success" in result
        assert "deployments_tested" in result
        assert len(result["deployments_tested"]) > 0

        if result["success"]:
            assert len(result["deployments_available"]) > 0
            assert result["endpoint_reachable"] is True
            assert result["authentication_valid"] is True
        else:
            # If failed, should have errors and recommendations
            assert len(result["errors"]) > 0
            assert len(result["recommendations"]) > 0


@pytest.mark.asyncio
@pytest.mark.integration
class TestProtocolCompliance:
    """Test that OpenAIService implements LLMProviderProtocol correctly."""

    async def test_complete_signature_compliance(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test complete method signature matches protocol."""
        service = OpenAIService(config_path=integration_config_file)

        # Protocol requires: messages, model (optional), **kwargs
        result = await service.complete(
            messages=[{"role": "user", "content": "Test"}]
        )
        assert "success" in result

        result = await service.complete(
            messages=[{"role": "user", "content": "Test"}], model="fast"
        )
        assert "success" in result

        result = await service.complete(
            messages=[{"role": "user", "content": "Test"}],
            model="fast",
            temperature=0.5,
            max_tokens=10,
        )
        assert "success" in result

    async def test_generate_signature_compliance(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test generate method signature matches protocol."""
        service = OpenAIService(config_path=integration_config_file)

        # Protocol requires: prompt, context (optional), model (optional), **kwargs
        result = await service.generate(prompt="Test")
        assert "success" in result

        result = await service.generate(prompt="Test", context={"key": "value"})
        assert "success" in result

        result = await service.generate(
            prompt="Test", context={"key": "value"}, model="fast", max_tokens=10
        )
        assert "success" in result

    async def test_return_value_structure(
        self, integration_config_file, skip_if_no_api_key
    ):
        """Test return value structure matches protocol."""
        service = OpenAIService(config_path=integration_config_file)

        result = await service.complete(
            messages=[{"role": "user", "content": "Test"}], model="fast", max_tokens=10
        )

        # Protocol requires these fields on success
        assert "success" in result
        if result["success"]:
            assert "content" in result
            assert "usage" in result
            assert "model" in result
            assert "latency_ms" in result
            assert isinstance(result["usage"], dict)
            assert "total_tokens" in result["usage"]
        else:
            assert "error" in result
            assert "error_type" in result

