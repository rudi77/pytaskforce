"""Unit tests for LLMTool.

Tests LLM text generation tool metadata, validation, and execution.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.llm_tool import LLMTool


class TestLLMToolMetadata:
    """Test LLMTool metadata properties."""

    @pytest.fixture
    def tool(self) -> LLMTool:
        return LLMTool(llm_service=MagicMock())

    def test_name(self, tool: LLMTool) -> None:
        assert tool.name == "llm_generate"

    def test_description(self, tool: LLMTool) -> None:
        desc = tool.description.lower()
        assert "generate" in desc
        assert "text" in desc

    def test_parameters_schema(self, tool: LLMTool) -> None:
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "prompt" in schema["properties"]
        assert "context" in schema["properties"]
        assert "max_tokens" in schema["properties"]
        assert "temperature" in schema["properties"]
        assert schema["required"] == ["prompt"]

    def test_requires_approval(self, tool: LLMTool) -> None:
        assert tool.requires_approval is False

    def test_approval_risk_level(self, tool: LLMTool) -> None:
        assert tool.approval_risk_level == ApprovalRiskLevel.LOW

    def test_supports_parallelism(self, tool: LLMTool) -> None:
        assert tool.supports_parallelism is True

    def test_get_approval_preview(self, tool: LLMTool) -> None:
        preview = tool.get_approval_preview(prompt="Summarize this text")
        assert "Summarize this text" in preview
        assert tool.name in preview

    def test_get_approval_preview_truncates_long_prompt(self, tool: LLMTool) -> None:
        long_prompt = "x" * 200
        preview = tool.get_approval_preview(prompt=long_prompt)
        assert "..." in preview


class TestLLMToolValidation:
    """Test LLMTool parameter validation."""

    @pytest.fixture
    def tool(self) -> LLMTool:
        return LLMTool(llm_service=MagicMock())

    def test_valid_params(self, tool: LLMTool) -> None:
        valid, error = tool.validate_params(prompt="test prompt")
        assert valid is True
        assert error is None

    def test_missing_prompt(self, tool: LLMTool) -> None:
        valid, error = tool.validate_params()
        assert valid is False
        assert "prompt" in error

    def test_non_string_prompt(self, tool: LLMTool) -> None:
        valid, error = tool.validate_params(prompt=123)
        assert valid is False
        assert "string" in error


class TestLLMToolExecution:
    """Test LLMTool execution."""

    @pytest.fixture
    def mock_llm_service(self) -> AsyncMock:
        service = AsyncMock()
        service.generate = AsyncMock(
            return_value={
                "success": True,
                "generated_text": "Hello, this is the generated response.",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
                "latency_ms": 150,
            }
        )
        return service

    @pytest.fixture
    def tool(self, mock_llm_service: AsyncMock) -> LLMTool:
        return LLMTool(llm_service=mock_llm_service)

    async def test_successful_generation(self, tool: LLMTool) -> None:
        result = await tool.execute(prompt="Write a greeting")
        assert result["success"] is True
        assert result["generated_text"] == "Hello, this is the generated response."
        assert result["tokens_used"] == 30
        assert result["prompt_tokens"] == 10
        assert result["completion_tokens"] == 20

    async def test_passes_parameters_to_llm_service(
        self, tool: LLMTool, mock_llm_service: AsyncMock
    ) -> None:
        await tool.execute(
            prompt="test",
            context={"key": "value"},
            max_tokens=100,
            temperature=0.5,
        )
        mock_llm_service.generate.assert_called_once_with(
            prompt="test",
            context={"key": "value"},
            model="main",
            max_tokens=100,
            temperature=0.5,
        )

    async def test_default_model_alias(self) -> None:
        service = AsyncMock()
        service.generate = AsyncMock(
            return_value={"success": True, "generated_text": "ok", "usage": {}}
        )
        tool = LLMTool(llm_service=service, model_alias="fast")
        await tool.execute(prompt="test")
        assert service.generate.call_args.kwargs["model"] == "fast"

    async def test_failed_generation(self) -> None:
        service = AsyncMock()
        service.generate = AsyncMock(
            return_value={
                "success": False,
                "error": "Rate limit exceeded",
                "error_type": "RateLimitError",
            }
        )
        tool = LLMTool(llm_service=service)
        result = await tool.execute(prompt="test")
        assert result["success"] is False
        assert "Rate limit" in result["error"]
        assert result["type"] == "RateLimitError"

    async def test_exception_handling(self) -> None:
        service = AsyncMock()
        service.generate = AsyncMock(side_effect=ConnectionError("network failure"))
        tool = LLMTool(llm_service=service)
        result = await tool.execute(prompt="test")
        assert result["success"] is False
        assert "network failure" in result.get("error", "")

    async def test_context_passed_to_service(
        self, tool: LLMTool, mock_llm_service: AsyncMock
    ) -> None:
        context = {"documents": ["doc1", "doc2"]}
        await tool.execute(prompt="summarize", context=context)
        call_kwargs = mock_llm_service.generate.call_args.kwargs
        assert call_kwargs["context"] == context


class TestLLMToolErrorHints:
    """Test error hint generation."""

    @pytest.fixture
    def tool(self) -> LLMTool:
        return LLMTool(llm_service=MagicMock())

    def test_token_limit_hints(self, tool: LLMTool) -> None:
        hints = tool._get_error_hints("ValueError", "token limit exceeded")
        assert any("token" in h.lower() or "max_tokens" in h.lower() for h in hints)

    def test_network_error_hints(self, tool: LLMTool) -> None:
        hints = tool._get_error_hints("TimeoutError", "request timed out")
        assert any("retry" in h.lower() for h in hints)

    def test_auth_error_hints(self, tool: LLMTool) -> None:
        hints = tool._get_error_hints("AuthError", "invalid api key")
        assert any("api key" in h.lower() for h in hints)

    def test_default_hints(self, tool: LLMTool) -> None:
        hints = tool._get_error_hints("UnknownError", "something broke")
        assert len(hints) >= 2  # Always includes base hints
