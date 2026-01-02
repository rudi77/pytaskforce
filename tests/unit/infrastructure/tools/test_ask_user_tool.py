"""
Unit tests for AskUserTool

Tests user interaction tool functionality.
"""

import pytest

from taskforce.infrastructure.tools.native.ask_user_tool import AskUserTool


class TestAskUserTool:
    """Test suite for AskUserTool."""

    @pytest.fixture
    def tool(self):
        """Create an AskUserTool instance."""
        return AskUserTool()

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "ask_user"
        assert "Ask the user" in tool.description
        assert tool.requires_approval is False

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "question" in schema["properties"]
        assert "missing" in schema["properties"]
        assert "question" in schema["required"]

    @pytest.mark.asyncio
    async def test_ask_user_basic(self, tool):
        """Test basic ask user functionality."""
        result = await tool.execute(question="What is your name?")

        assert result["success"] is True
        assert result["question"] == "What is your name?"
        assert result["missing"] == []

    @pytest.mark.asyncio
    async def test_ask_user_with_missing(self, tool):
        """Test ask user with missing information list."""
        result = await tool.execute(
            question="Please provide details",
            missing=["email", "phone", "address"],
        )

        assert result["success"] is True
        assert result["question"] == "Please provide details"
        assert result["missing"] == ["email", "phone", "address"]

    def test_validate_params_success(self, tool):
        """Test parameter validation with valid params."""
        valid, error = tool.validate_params(question="Test question?")

        assert valid is True
        assert error is None

    def test_validate_params_missing_question(self, tool):
        """Test parameter validation with missing question."""
        valid, error = tool.validate_params()

        assert valid is False
        assert "question" in error

    def test_validate_params_invalid_type(self, tool):
        """Test parameter validation with invalid type."""
        valid, error = tool.validate_params(question=123)

        assert valid is False
        assert "string" in error

