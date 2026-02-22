"""Tests for configuration schema validation models and helpers."""

from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from taskforce.core.domain.config_schema import (
    AgentConfigSchema,
    AgentSourceType,
    AutoEpicConfig,
    ConfigValidationError,
    MCPServerConfigSchema,
    ProfileConfigSchema,
    _class_name_to_tool_name,
    extract_tool_names,
    validate_agent_config,
    validate_profile_config,
)


class TestAgentSourceType:
    """Tests for AgentSourceType enum."""

    def test_values(self) -> None:
        assert AgentSourceType.CUSTOM.value == "custom"
        assert AgentSourceType.PROFILE.value == "profile"
        assert AgentSourceType.PLUGIN.value == "plugin"
        assert AgentSourceType.COMMAND.value == "command"

    def test_is_str_enum(self) -> None:
        assert isinstance(AgentSourceType.CUSTOM, str)
        assert AgentSourceType.CUSTOM == "custom"


class TestMCPServerConfigSchema:
    """Tests for MCPServerConfigSchema validation."""

    def test_valid_stdio_config(self) -> None:
        config = MCPServerConfigSchema(
            type="stdio",
            command="npx",
            args=["-y", "@model/server"],
            env={"KEY": "value"},
            description="Test server",
        )
        assert config.type == "stdio"
        assert config.command == "npx"
        assert config.args == ["-y", "@model/server"]

    def test_valid_sse_config(self) -> None:
        config = MCPServerConfigSchema(
            type="sse",
            url="http://localhost:3000",
        )
        assert config.type == "sse"
        assert config.url == "http://localhost:3000"

    def test_stdio_without_command_raises(self) -> None:
        with pytest.raises(PydanticValidationError, match="stdio server requires 'command'"):
            MCPServerConfigSchema(type="stdio")

    def test_sse_without_url_raises(self) -> None:
        with pytest.raises(PydanticValidationError, match="sse server requires 'url'"):
            MCPServerConfigSchema(type="sse")

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            MCPServerConfigSchema(type="invalid", command="cmd")

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(PydanticValidationError):
            MCPServerConfigSchema(type="stdio", command="cmd", unknown_field="bad")

    def test_defaults(self) -> None:
        config = MCPServerConfigSchema(type="stdio", command="node")
        assert config.args == []
        assert config.env == {}
        assert config.description == ""
        assert config.url is None


class TestAgentConfigSchema:
    """Tests for AgentConfigSchema validation."""

    def _minimal_config(self, **overrides) -> dict:
        """Create a minimal valid config dict."""
        base = {"agent_id": "test-agent", "name": "Test Agent"}
        base.update(overrides)
        return base

    def test_valid_minimal(self) -> None:
        config = AgentConfigSchema(**self._minimal_config())
        assert config.agent_id == "test-agent"
        assert config.name == "Test Agent"
        assert config.source == AgentSourceType.CUSTOM
        assert config.planning_strategy == "native_react"
        assert config.tools == []
        assert config.base_profile == "dev"

    def test_valid_full(self) -> None:
        config = AgentConfigSchema(**self._minimal_config(
            description="A test agent",
            source=AgentSourceType.PLUGIN,
            system_prompt="You are helpful.",
            specialist="coding",
            planning_strategy="spar",
            max_steps=50,
            tools=["python", "file_read"],
            base_profile="coding_agent",
            work_dir="/tmp/work",
        ))
        assert config.specialist == "coding"
        assert config.planning_strategy == "spar"
        assert config.max_steps == 50
        assert config.tools == ["python", "file_read"]

    def test_agent_id_empty_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            AgentConfigSchema(agent_id="", name="Test")

    def test_agent_id_invalid_chars_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            AgentConfigSchema(agent_id="has spaces", name="Test")

    def test_agent_id_special_chars_allowed(self) -> None:
        config = AgentConfigSchema(agent_id="my-agent_v2:latest", name="Agent")
        assert config.agent_id == "my-agent_v2:latest"

    def test_name_empty_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            AgentConfigSchema(agent_id="test", name="")

    def test_invalid_specialist_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            AgentConfigSchema(**self._minimal_config(specialist="invalid"))

    def test_valid_specialists(self) -> None:
        for s in ["coding", "rag", "wiki"]:
            config = AgentConfigSchema(**self._minimal_config(specialist=s))
            assert config.specialist == s

    def test_invalid_planning_strategy_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            AgentConfigSchema(**self._minimal_config(planning_strategy="invalid"))

    def test_valid_planning_strategies(self) -> None:
        for ps in ["native_react", "plan_and_execute", "plan_and_react", "spar"]:
            config = AgentConfigSchema(**self._minimal_config(planning_strategy=ps))
            assert config.planning_strategy == ps

    def test_max_steps_zero_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            AgentConfigSchema(**self._minimal_config(max_steps=0))

    def test_max_steps_over_limit_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            AgentConfigSchema(**self._minimal_config(max_steps=1001))

    def test_max_steps_none_allowed(self) -> None:
        config = AgentConfigSchema(**self._minimal_config(max_steps=None))
        assert config.max_steps is None

    def test_tools_must_be_strings(self) -> None:
        with pytest.raises(PydanticValidationError, match="Tool must be a string.*not a dict"):
            AgentConfigSchema(**self._minimal_config(
                tools=[{"type": "WebSearchTool"}]
            ))

    def test_tools_non_string_non_dict_raises(self) -> None:
        with pytest.raises(PydanticValidationError, match="must be a string, got int"):
            AgentConfigSchema(**self._minimal_config(tools=[123]))

    def test_tools_not_a_list_raises(self) -> None:
        with pytest.raises(PydanticValidationError, match="tools must be a list"):
            AgentConfigSchema(**self._minimal_config(tools="python"))

    def test_mcp_servers_validation(self) -> None:
        config = AgentConfigSchema(**self._minimal_config(
            mcp_servers=[{"type": "stdio", "command": "npx", "args": ["-y", "server"]}]
        ))
        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0].command == "npx"

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(PydanticValidationError):
            AgentConfigSchema(**self._minimal_config(unknown_field="bad"))

    def test_timestamps(self) -> None:
        now = datetime.now()
        config = AgentConfigSchema(**self._minimal_config(
            created_at=now,
            updated_at=now,
        ))
        assert config.created_at == now
        assert config.updated_at == now


class TestAutoEpicConfig:
    """Tests for AutoEpicConfig validation."""

    def test_defaults(self) -> None:
        config = AutoEpicConfig()
        assert config.enabled is False
        assert config.confidence_threshold == 0.7
        assert config.classifier_model is None
        assert config.default_worker_count == 3
        assert config.default_max_rounds == 3
        assert config.planner_profile == "planner"
        assert config.worker_profile == "worker"
        assert config.judge_profile == "judge"

    def test_confidence_threshold_bounds(self) -> None:
        AutoEpicConfig(confidence_threshold=0.0)
        AutoEpicConfig(confidence_threshold=1.0)
        with pytest.raises(PydanticValidationError):
            AutoEpicConfig(confidence_threshold=-0.1)
        with pytest.raises(PydanticValidationError):
            AutoEpicConfig(confidence_threshold=1.1)

    def test_worker_count_bounds(self) -> None:
        AutoEpicConfig(default_worker_count=1)
        AutoEpicConfig(default_worker_count=10)
        with pytest.raises(PydanticValidationError):
            AutoEpicConfig(default_worker_count=0)
        with pytest.raises(PydanticValidationError):
            AutoEpicConfig(default_worker_count=11)

    def test_max_rounds_bounds(self) -> None:
        AutoEpicConfig(default_max_rounds=1)
        AutoEpicConfig(default_max_rounds=10)
        with pytest.raises(PydanticValidationError):
            AutoEpicConfig(default_max_rounds=0)
        with pytest.raises(PydanticValidationError):
            AutoEpicConfig(default_max_rounds=11)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(PydanticValidationError):
            AutoEpicConfig(unknown_field="bad")


class TestProfileConfigSchema:
    """Tests for ProfileConfigSchema validation."""

    def test_defaults(self) -> None:
        config = ProfileConfigSchema()
        assert config.agent is None
        assert config.specialist is None
        assert config.tools == []
        assert config.mcp_servers == []
        assert config.persistence is None
        assert config.llm is None

    def test_with_tools(self) -> None:
        config = ProfileConfigSchema(tools=["python", "file_read"])
        assert config.tools == ["python", "file_read"]

    def test_allows_extra_fields(self) -> None:
        """Profiles allow extra fields for extensibility."""
        config = ProfileConfigSchema(profile="dev", custom_setting="value")
        assert config.model_extra.get("profile") == "dev"
        assert config.model_extra.get("custom_setting") == "value"

    def test_with_agent_section(self) -> None:
        config = ProfileConfigSchema(
            agent={"planning_strategy": "spar", "max_steps": 20}
        )
        assert config.agent["planning_strategy"] == "spar"

    def test_with_legacy_dict_tools(self) -> None:
        """Profile supports legacy dict-format tools for backward compatibility."""
        config = ProfileConfigSchema(
            tools=[{"type": "WebSearchTool"}, "python"]
        )
        assert len(config.tools) == 2


class TestConfigValidationError:
    """Tests for ConfigValidationError exception."""

    def test_message_only(self) -> None:
        err = ConfigValidationError("Something went wrong")
        assert "Something went wrong" in str(err)
        assert err.file_path is None
        assert err.field_path is None

    def test_with_file_path(self) -> None:
        err = ConfigValidationError("Bad config", file_path=Path("/etc/config.yaml"))
        assert "File: /etc/config.yaml" in str(err)
        assert "Bad config" in str(err)

    def test_with_field_path(self) -> None:
        err = ConfigValidationError("Invalid value", field_path="agent.max_steps")
        assert "Field: agent.max_steps" in str(err)
        assert "Invalid value" in str(err)

    def test_with_both_paths(self) -> None:
        err = ConfigValidationError(
            "Out of range",
            file_path=Path("config.yaml"),
            field_path="agent.max_steps",
        )
        msg = str(err)
        assert "File: config.yaml" in msg
        assert "Field: agent.max_steps" in msg
        assert "Out of range" in msg

    def test_is_exception(self) -> None:
        err = ConfigValidationError("test")
        assert isinstance(err, Exception)


class TestValidateAgentConfig:
    """Tests for validate_agent_config helper function."""

    def test_valid_config(self) -> None:
        result = validate_agent_config({"agent_id": "test", "name": "Test"})
        assert isinstance(result, AgentConfigSchema)
        assert result.agent_id == "test"

    def test_invalid_config_raises_config_validation_error(self) -> None:
        with pytest.raises(ConfigValidationError):
            validate_agent_config({"agent_id": "", "name": ""})

    def test_includes_file_path_in_error(self) -> None:
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_agent_config(
                {"agent_id": "", "name": ""},
                file_path=Path("agents.yaml"),
            )
        assert exc_info.value.file_path == Path("agents.yaml")


class TestValidateProfileConfig:
    """Tests for validate_profile_config helper function."""

    def test_valid_config(self) -> None:
        result = validate_profile_config({"tools": ["python", "shell"]})
        assert isinstance(result, ProfileConfigSchema)
        assert result.tools == ["python", "shell"]

    def test_empty_config(self) -> None:
        result = validate_profile_config({})
        assert isinstance(result, ProfileConfigSchema)


class TestExtractToolNames:
    """Tests for extract_tool_names helper function."""

    def test_string_tools(self) -> None:
        result = extract_tool_names(["python", "file_read", "web_search"])
        assert result == ["python", "file_read", "web_search"]

    def test_dict_tools(self) -> None:
        result = extract_tool_names([{"type": "WebSearchTool"}])
        assert result == ["web_search"]

    def test_mixed_tools(self) -> None:
        result = extract_tool_names([
            "python",
            {"type": "FileReadTool"},
            "shell",
        ])
        assert result == ["python", "file_read", "shell"]

    def test_empty_list(self) -> None:
        result = extract_tool_names([])
        assert result == []

    def test_dict_without_type_key(self) -> None:
        result = extract_tool_names([{"name": "something"}])
        assert result == []

    def test_dict_with_empty_type(self) -> None:
        result = extract_tool_names([{"type": ""}])
        assert result == []


class TestClassNameToToolName:
    """Tests for _class_name_to_tool_name helper."""

    def test_basic_conversion(self) -> None:
        assert _class_name_to_tool_name("WebSearchTool") == "web_search"
        assert _class_name_to_tool_name("FileReadTool") == "file_read"
        assert _class_name_to_tool_name("PythonTool") == "python"

    def test_no_tool_suffix(self) -> None:
        assert _class_name_to_tool_name("WebSearch") == "web_search"

    def test_single_word(self) -> None:
        assert _class_name_to_tool_name("Shell") == "shell"

    def test_single_word_with_tool(self) -> None:
        assert _class_name_to_tool_name("ShellTool") == "shell"

    def test_multi_word_camel_case(self) -> None:
        assert _class_name_to_tool_name("AzureAISearchTool") == "azure_a_i_search"

    def test_already_lowercase(self) -> None:
        assert _class_name_to_tool_name("python") == "python"

    def test_empty_string(self) -> None:
        assert _class_name_to_tool_name("") == ""

    def test_tool_only(self) -> None:
        assert _class_name_to_tool_name("Tool") == ""
