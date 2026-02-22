"""Tests for domain error types and tool_error_payload helper."""

import pytest

from taskforce.core.domain.errors import (
    CancelledError,
    ConfigError,
    LLMError,
    NotFoundError,
    PluginError,
    PlanningError,
    TaskforceError,
    ToolError,
    ValidationError,
    tool_error_payload,
)
from taskforce.core.domain.exceptions import (
    AgentExecutionError,
    LeanAgentExecutionError,
    TaskforceExecutionError,
)


class TestTaskforceError:
    """Tests for TaskforceError base exception."""

    def test_create_basic(self) -> None:
        err = TaskforceError(message="Something failed")
        assert err.message == "Something failed"
        assert err.code == "taskforce_error"
        assert err.details == {}
        assert err.status_code is None

    def test_create_with_details(self) -> None:
        err = TaskforceError(
            message="Failed",
            code="custom_code",
            details={"key": "value"},
            status_code=500,
        )
        assert err.code == "custom_code"
        assert err.details == {"key": "value"}
        assert err.status_code == 500

    def test_is_exception(self) -> None:
        err = TaskforceError(message="test")
        assert isinstance(err, Exception)

    def test_str_representation(self) -> None:
        err = TaskforceError(message="Something broke")
        assert str(err) == "Something broke"

    def test_details_defaults_to_empty_dict(self) -> None:
        err = TaskforceError(message="test", details=None)
        assert err.details == {}

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(TaskforceError) as exc_info:
            raise TaskforceError(message="Raised error")
        assert str(exc_info.value) == "Raised error"


class TestLLMError:
    """Tests for LLMError exception."""

    def test_create(self) -> None:
        err = LLMError("Model timed out")
        assert err.message == "Model timed out"
        assert err.code == "llm_error"
        assert err.details == {}

    def test_create_with_details(self) -> None:
        err = LLMError("Rate limit", details={"retry_after": 30})
        assert err.details == {"retry_after": 30}

    def test_is_taskforce_error(self) -> None:
        err = LLMError("test")
        assert isinstance(err, TaskforceError)
        assert isinstance(err, Exception)


class TestToolError:
    """Tests for ToolError exception."""

    def test_create_basic(self) -> None:
        err = ToolError("File not found")
        assert err.message == "File not found"
        assert err.code == "tool_error"
        assert err.tool_name is None
        assert err.details == {}

    def test_create_with_tool_name(self) -> None:
        err = ToolError("Permission denied", tool_name="file_write")
        assert err.tool_name == "file_write"
        assert err.details["tool_name"] == "file_write"

    def test_create_with_details_and_tool_name(self) -> None:
        err = ToolError(
            "Execution failed",
            tool_name="python",
            details={"exit_code": 1},
        )
        assert err.details["tool_name"] == "python"
        assert err.details["exit_code"] == 1

    def test_tool_name_does_not_overwrite_details(self) -> None:
        """If details already has 'tool_name', it should not be overwritten."""
        err = ToolError(
            "Error",
            tool_name="python",
            details={"tool_name": "existing"},
        )
        assert err.details["tool_name"] == "existing"

    def test_is_taskforce_error(self) -> None:
        err = ToolError("test")
        assert isinstance(err, TaskforceError)


class TestPlanningError:
    """Tests for PlanningError exception."""

    def test_create(self) -> None:
        err = PlanningError("Plan generation failed")
        assert err.message == "Plan generation failed"
        assert err.code == "planning_error"

    def test_with_details(self) -> None:
        err = PlanningError("Failed", details={"step": 3})
        assert err.details["step"] == 3


class TestConfigError:
    """Tests for ConfigError exception."""

    def test_create(self) -> None:
        err = ConfigError("Invalid profile")
        assert err.message == "Invalid profile"
        assert err.code == "config_error"


class TestCancelledError:
    """Tests for CancelledError exception."""

    def test_create(self) -> None:
        err = CancelledError("User cancelled")
        assert err.message == "User cancelled"
        assert err.code == "cancelled"


class TestNotFoundError:
    """Tests for NotFoundError exception."""

    def test_create(self) -> None:
        err = NotFoundError("Session not found")
        assert err.message == "Session not found"
        assert err.code == "not_found"


class TestValidationError:
    """Tests for ValidationError exception."""

    def test_create(self) -> None:
        err = ValidationError("Field required")
        assert err.message == "Field required"
        assert err.code == "validation_error"


class TestPluginError:
    """Tests for PluginError exception."""

    def test_create_basic(self) -> None:
        err = PluginError("Load failed")
        assert err.message == "Load failed"
        assert err.code == "plugin_error"
        assert err.plugin_path is None

    def test_create_with_plugin_path(self) -> None:
        err = PluginError("Bad plugin", plugin_path="/plugins/bad")
        assert err.plugin_path == "/plugins/bad"
        assert err.details["plugin_path"] == "/plugins/bad"

    def test_plugin_path_does_not_overwrite_details(self) -> None:
        err = PluginError(
            "Error",
            plugin_path="/new",
            details={"plugin_path": "/existing"},
        )
        assert err.details["plugin_path"] == "/existing"

    def test_is_taskforce_error(self) -> None:
        err = PluginError("test")
        assert isinstance(err, TaskforceError)


class TestToolErrorPayload:
    """Tests for tool_error_payload helper function."""

    def test_basic_payload(self) -> None:
        err = ToolError("Disk full", tool_name="file_write")
        payload = tool_error_payload(err)
        assert payload["success"] is False
        assert payload["error"] == "Disk full"
        assert payload["error_type"] == "ToolError"
        assert payload["details"]["tool_name"] == "file_write"

    def test_with_extra_fields(self) -> None:
        err = ToolError("Timeout")
        payload = tool_error_payload(err, extra={"retry": True, "timeout": 30})
        assert payload["retry"] is True
        assert payload["timeout"] == 30
        assert payload["success"] is False

    def test_without_extra(self) -> None:
        err = ToolError("Failed")
        payload = tool_error_payload(err)
        assert "retry" not in payload

    def test_error_type_is_class_name(self) -> None:
        """error_type should be the class name, not the code."""
        err = ToolError("test")
        payload = tool_error_payload(err)
        assert payload["error_type"] == "ToolError"

    def test_details_empty_when_no_tool_name(self) -> None:
        err = ToolError("test")
        payload = tool_error_payload(err)
        assert payload["details"] == {}


class TestTaskforceExecutionError:
    """Tests for TaskforceExecutionError."""

    def test_create_basic(self) -> None:
        err = TaskforceExecutionError("Execution failed")
        assert err.message == "Execution failed"
        assert err.code == "execution_error"
        assert err.session_id is None
        assert err.tool_name is None
        assert err.error_code is None

    def test_create_full(self) -> None:
        err = TaskforceExecutionError(
            "Tool timeout",
            session_id="sess-1",
            tool_name="python",
            error_code="timeout",
            status_code=504,
            details={"elapsed": 30},
        )
        assert err.session_id == "sess-1"
        assert err.tool_name == "python"
        assert err.error_code == "timeout"
        assert err.status_code == 504
        assert err.details["session_id"] == "sess-1"
        assert err.details["tool_name"] == "python"
        assert err.details["error_code"] == "timeout"
        assert err.details["elapsed"] == 30

    def test_code_uses_error_code(self) -> None:
        err = TaskforceExecutionError("test", error_code="custom_code")
        assert err.code == "custom_code"

    def test_is_taskforce_error(self) -> None:
        err = TaskforceExecutionError("test")
        assert isinstance(err, TaskforceError)


class TestAgentExecutionError:
    """Tests for AgentExecutionError."""

    def test_create_with_agent_id(self) -> None:
        err = AgentExecutionError(
            "Agent crashed",
            session_id="sess-1",
            agent_id="agent-42",
        )
        assert err.agent_id == "agent-42"
        assert err.session_id == "sess-1"
        assert err.details["agent_id"] == "agent-42"

    def test_is_taskforce_execution_error(self) -> None:
        err = AgentExecutionError("test")
        assert isinstance(err, TaskforceExecutionError)
        assert isinstance(err, TaskforceError)


class TestLeanAgentExecutionErrorAlias:
    """Tests for the backward-compatible LeanAgentExecutionError alias."""

    def test_is_same_as_agent_execution_error(self) -> None:
        assert LeanAgentExecutionError is AgentExecutionError

    def test_can_instantiate(self) -> None:
        err = LeanAgentExecutionError("test")
        assert isinstance(err, AgentExecutionError)
