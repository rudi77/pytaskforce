"""Unit tests for BaseTool convenience base class."""

import pytest

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.base_tool import BaseTool, _sanitize_kwargs


# ------------------------------------------------------------------ #
# Concrete test subclass
# ------------------------------------------------------------------ #


class DummyTool(BaseTool):
    """Minimal concrete tool for testing."""

    tool_name = "dummy"
    tool_description = "A dummy tool for testing"
    tool_parameters_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "A message"},
            "count": {"type": "integer", "description": "A count"},
            "mode": {"type": "string", "enum": ["fast", "slow"]},
            "tags": {"type": "array", "description": "Tags list"},
            "flag": {"type": "boolean", "description": "A flag"},
            "rate": {"type": "number", "description": "A rate"},
            "meta": {"type": "object", "description": "Metadata dict"},
        },
        "required": ["message"],
    }

    async def _execute(self, **kwargs) -> dict:
        return {"success": True, "echo": kwargs.get("message")}


class FailingTool(BaseTool):
    """Tool that always raises an exception."""

    tool_name = "failing"
    tool_description = "Always fails"
    tool_parameters_schema = {}

    async def _execute(self, **kwargs) -> dict:
        raise RuntimeError("something broke")


class ApprovalTool(BaseTool):
    """Tool requiring approval."""

    tool_name = "approval_tool"
    tool_description = "Needs approval"
    tool_parameters_schema = {}
    tool_requires_approval = True
    tool_approval_risk_level = ApprovalRiskLevel.HIGH
    tool_supports_parallelism = True

    async def _execute(self, **kwargs) -> dict:
        return {"success": True}


# ------------------------------------------------------------------ #
# Tests: Metadata properties
# ------------------------------------------------------------------ #


class TestBaseToolMetadata:
    """Test that class-level attributes map to ToolProtocol properties."""

    @pytest.fixture
    def tool(self):
        return DummyTool()

    def test_name(self, tool):
        assert tool.name == "dummy"

    def test_description(self, tool):
        assert tool.description == "A dummy tool for testing"

    def test_parameters_schema(self, tool):
        assert tool.parameters_schema["type"] == "object"
        assert "message" in tool.parameters_schema["properties"]

    def test_defaults(self, tool):
        assert tool.requires_approval is False
        assert tool.approval_risk_level == ApprovalRiskLevel.LOW
        assert tool.supports_parallelism is False

    def test_custom_approval_settings(self):
        tool = ApprovalTool()
        assert tool.requires_approval is True
        assert tool.approval_risk_level == ApprovalRiskLevel.HIGH
        assert tool.supports_parallelism is True


# ------------------------------------------------------------------ #
# Tests: validate_params
# ------------------------------------------------------------------ #


class TestValidateParams:
    @pytest.fixture
    def tool(self):
        return DummyTool()

    def test_valid_params(self, tool):
        ok, err = tool.validate_params(message="hello")
        assert ok is True
        assert err is None

    def test_missing_required_param(self, tool):
        ok, err = tool.validate_params(count=5)
        assert ok is False
        assert "Missing required parameter: message" in err

    def test_wrong_type_string(self, tool):
        ok, err = tool.validate_params(message=123)
        assert ok is False
        assert "must be a string" in err

    def test_wrong_type_integer(self, tool):
        ok, err = tool.validate_params(message="hi", count="not_int")
        assert ok is False
        assert "must be a integer" in err

    def test_number_accepts_int_and_float(self, tool):
        ok1, _ = tool.validate_params(message="hi", rate=1.5)
        ok2, _ = tool.validate_params(message="hi", rate=3)
        assert ok1 is True
        assert ok2 is True

    def test_wrong_type_boolean(self, tool):
        ok, err = tool.validate_params(message="hi", flag="yes")
        assert ok is False
        assert "must be a boolean" in err

    def test_wrong_type_array(self, tool):
        ok, err = tool.validate_params(message="hi", tags="not a list")
        assert ok is False
        assert "must be a array" in err

    def test_wrong_type_object(self, tool):
        ok, err = tool.validate_params(message="hi", meta="not a dict")
        assert ok is False
        assert "must be a object" in err

    def test_enum_valid(self, tool):
        ok, err = tool.validate_params(message="hi", mode="fast")
        assert ok is True
        assert err is None

    def test_enum_invalid(self, tool):
        ok, err = tool.validate_params(message="hi", mode="turbo")
        assert ok is False
        assert "must be one of" in err

    def test_none_value_skips_type_check(self, tool):
        """None values should not trigger type validation."""
        ok, err = tool.validate_params(message="hi", count=None)
        assert ok is True

    def test_unknown_param_ignored(self, tool):
        """Parameters not in schema should be silently ignored."""
        ok, err = tool.validate_params(message="hi", unknown_param=42)
        assert ok is True

    def test_empty_schema(self):
        tool = FailingTool()
        ok, err = tool.validate_params(anything="goes")
        assert ok is True
        assert err is None


# ------------------------------------------------------------------ #
# Tests: Execution
# ------------------------------------------------------------------ #


class TestExecution:
    async def test_successful_execute(self):
        tool = DummyTool()
        result = await tool.execute(message="hello")
        assert result["success"] is True
        assert result["echo"] == "hello"

    async def test_execute_safe_catches_exception(self):
        tool = FailingTool()
        result = await tool.execute()
        assert result["success"] is False
        assert "something broke" in result["error"]
        assert result["error_type"] == "ToolError"

    async def test_not_implemented_by_default(self):
        """BaseTool._execute raises NotImplementedError if not overridden."""

        class BareTool(BaseTool):
            tool_name = "bare"
            tool_description = "bare"
            tool_parameters_schema = {}

        tool = BareTool()
        result = await tool.execute()
        assert result["success"] is False
        assert "must implement _execute" in result["error"]


# ------------------------------------------------------------------ #
# Tests: get_approval_preview
# ------------------------------------------------------------------ #


class TestApprovalPreview:
    def test_basic_preview(self):
        tool = DummyTool()
        preview = tool.get_approval_preview(message="hi", count=3)
        assert "Tool: dummy" in preview
        assert "message: hi" in preview
        assert "count: 3" in preview

    def test_long_value_truncated(self):
        tool = DummyTool()
        long_value = "x" * 200
        preview = tool.get_approval_preview(data=long_value)
        assert "..." in preview
        # Truncated to 120 chars + "..."
        lines = preview.split("\n")
        data_line = [l for l in lines if "data:" in l][0]
        # 120 chars of value + "..." = 123, plus "  data: " prefix
        assert len(data_line) < 200


# ------------------------------------------------------------------ #
# Tests: _sanitize_kwargs
# ------------------------------------------------------------------ #


class TestSanitizeKwargs:
    def test_short_strings_unchanged(self):
        result = _sanitize_kwargs({"key": "short"})
        assert result == {"key": "short"}

    def test_long_strings_truncated(self):
        long_val = "a" * 300
        result = _sanitize_kwargs({"key": long_val})
        assert result["key"].endswith("...")
        assert len(result["key"]) == 203  # 200 + len("...")

    def test_non_string_values_unchanged(self):
        result = _sanitize_kwargs({"num": 42, "flag": True, "items": [1, 2]})
        assert result == {"num": 42, "flag": True, "items": [1, 2]}

    def test_custom_max_len(self):
        result = _sanitize_kwargs({"key": "abcdefghij"}, max_str_len=5)
        assert result["key"] == "abcde..."

    def test_empty_dict(self):
        assert _sanitize_kwargs({}) == {}
