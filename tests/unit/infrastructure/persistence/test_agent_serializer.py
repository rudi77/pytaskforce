"""Tests for agent serializer.

Verifies serialization and deserialization of agent YAML definitions,
including custom agent parsing, profile agent parsing, and YAML dict building.
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import Mock

from taskforce.core.domain.agent_models import CustomAgentDefinition, ProfileAgentDefinition
from taskforce.core.interfaces.tool_mapping import ToolMapperProtocol
from taskforce.infrastructure.persistence.agent_serializer import (
    build_agent_yaml,
    parse_custom_agent_yaml,
    parse_profile_agent_yaml,
)


@pytest.fixture
def mock_tool_mapper():
    """Create a mock ToolMapperProtocol."""
    mapper = Mock(spec=ToolMapperProtocol)
    mapper.get_tool_name.side_effect = lambda t: {"PythonTool": "python", "ShellTool": "shell"}.get(
        t
    )
    mapper.map_tools.return_value = [
        {"type": "PythonTool", "module": "tools.python"},
        {"type": "ShellTool", "module": "tools.shell"},
    ]
    return mapper


class TestParseCustomAgentYaml:
    """Tests for parse_custom_agent_yaml."""

    def test_parses_minimal_data(self):
        data = {"name": "My Agent", "system_prompt": "You are helpful."}

        result = parse_custom_agent_yaml(data, agent_id="my-agent")

        assert isinstance(result, CustomAgentDefinition)
        assert result.agent_id == "my-agent"
        assert result.name == "My Agent"
        assert result.system_prompt == "You are helpful."
        assert result.description == ""
        assert result.tool_allowlist == []

    def test_uses_agent_id_from_data(self):
        data = {"agent_id": "from-data", "name": "Agent"}

        result = parse_custom_agent_yaml(data, agent_id="fallback-id")

        assert result.agent_id == "from-data"

    def test_falls_back_to_agent_id_param(self):
        data = {"name": "Agent"}

        result = parse_custom_agent_yaml(data, agent_id="fallback-id")

        assert result.agent_id == "fallback-id"

    def test_parses_string_tools(self):
        data = {"tools": ["python", "file_read", "shell"]}

        result = parse_custom_agent_yaml(data, agent_id="test")

        assert result.tool_allowlist == ["python", "file_read", "shell"]

    def test_parses_dict_tools_with_mapper(self, mock_tool_mapper):
        data = {"tools": [{"type": "PythonTool"}, {"type": "ShellTool"}]}

        result = parse_custom_agent_yaml(data, agent_id="test", tool_mapper=mock_tool_mapper)

        assert result.tool_allowlist == ["python", "shell"]

    def test_ignores_dict_tools_without_mapper(self):
        data = {"tools": [{"type": "PythonTool"}, "file_read"]}

        result = parse_custom_agent_yaml(data, agent_id="test")

        assert result.tool_allowlist == ["file_read"]

    def test_skips_unknown_dict_tools(self, mock_tool_mapper):
        data = {"tools": [{"type": "UnknownTool"}]}

        result = parse_custom_agent_yaml(data, agent_id="test", tool_mapper=mock_tool_mapper)

        assert result.tool_allowlist == []

    def test_skips_dict_tools_without_type(self, mock_tool_mapper):
        data = {"tools": [{"module": "some.module"}]}

        result = parse_custom_agent_yaml(data, agent_id="test", tool_mapper=mock_tool_mapper)

        assert result.tool_allowlist == []

    def test_mixed_string_and_dict_tools(self, mock_tool_mapper):
        data = {"tools": ["file_read", {"type": "PythonTool"}, "web_search"]}

        result = parse_custom_agent_yaml(data, agent_id="test", tool_mapper=mock_tool_mapper)

        assert result.tool_allowlist == ["file_read", "python", "web_search"]

    def test_tool_allowlist_overrides_tools(self):
        data = {
            "tools": ["python", "shell"],
            "tool_allowlist": ["file_read", "web_search"],
        }

        result = parse_custom_agent_yaml(data, agent_id="test")

        assert result.tool_allowlist == ["file_read", "web_search"]

    def test_parses_all_optional_fields(self):
        data = {
            "agent_id": "full-agent",
            "name": "Full Agent",
            "description": "A complete agent definition",
            "system_prompt": "You are a full agent.",
            "tools": ["python"],
            "mcp_servers": [{"type": "stdio", "command": "npx"}],
            "mcp_tool_allowlist": ["mcp_tool_1"],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-02T00:00:00",
        }

        result = parse_custom_agent_yaml(data, agent_id="fallback")

        assert result.agent_id == "full-agent"
        assert result.description == "A complete agent definition"
        assert result.mcp_servers == [{"type": "stdio", "command": "npx"}]
        assert result.mcp_tool_allowlist == ["mcp_tool_1"]
        assert result.created_at == "2026-01-01T00:00:00"
        assert result.updated_at == "2026-01-02T00:00:00"

    def test_defaults_for_missing_fields(self):
        data = {}

        result = parse_custom_agent_yaml(data, agent_id="test")

        assert result.agent_id == "test"
        assert result.name == "test"
        assert result.description == ""
        assert result.system_prompt == ""
        assert result.tool_allowlist == []
        assert result.mcp_servers == []
        assert result.mcp_tool_allowlist == []
        assert result.created_at == ""
        assert result.updated_at == ""


class TestParseProfileAgentYaml:
    """Tests for parse_profile_agent_yaml."""

    def test_parses_valid_profile(self, tmp_path):
        profile = tmp_path / "dev.yaml"
        profile.write_text(
            yaml.safe_dump(
                {
                    "specialist": "coding",
                    "tools": ["python", "shell"],
                    "mcp_servers": [{"type": "stdio"}],
                    "llm": {"default_model": "main"},
                    "persistence": {"type": "file"},
                }
            ),
            encoding="utf-8",
        )

        result = parse_profile_agent_yaml(profile)

        assert isinstance(result, ProfileAgentDefinition)
        assert result.profile == "dev"
        assert result.specialist == "coding"
        assert result.tools == ["python", "shell"]
        assert result.mcp_servers == [{"type": "stdio"}]
        assert result.llm == {"default_model": "main"}
        assert result.persistence == {"type": "file"}

    def test_uses_filename_stem_as_profile(self, tmp_path):
        profile = tmp_path / "coding_agent.yaml"
        profile.write_text(yaml.safe_dump({"tools": []}), encoding="utf-8")

        result = parse_profile_agent_yaml(profile)

        assert result.profile == "coding_agent"

    def test_defaults_for_missing_keys(self, tmp_path):
        profile = tmp_path / "minimal.yaml"
        profile.write_text(yaml.safe_dump({"profile": "minimal"}), encoding="utf-8")

        result = parse_profile_agent_yaml(profile)

        assert result.specialist is None
        assert result.tools == []
        assert result.mcp_servers == []
        assert result.llm == {}
        assert result.persistence == {}

    def test_returns_none_for_nonexistent_file(self, tmp_path):
        path = tmp_path / "missing.yaml"

        result = parse_profile_agent_yaml(path)

        assert result is None

    def test_returns_none_for_corrupt_yaml(self, tmp_path):
        profile = tmp_path / "corrupt.yaml"
        profile.write_text("{{broken: yaml: [}", encoding="utf-8")

        result = parse_profile_agent_yaml(profile)

        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path):
        profile = tmp_path / "empty.yaml"
        profile.write_text("", encoding="utf-8")

        result = parse_profile_agent_yaml(profile)

        # yaml.safe_load("") returns None, .get() on None raises AttributeError
        assert result is None


class TestBuildAgentYaml:
    """Tests for build_agent_yaml."""

    def test_builds_basic_yaml(self):
        result = build_agent_yaml(
            agent_id="test-agent",
            name="Test Agent",
            description="A test agent",
            system_prompt="You are a test agent.",
            tool_allowlist=["python", "shell"],
            mcp_servers=[],
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-02T00:00:00",
        )

        assert result["agent_id"] == "test-agent"
        assert result["name"] == "Test Agent"
        assert result["description"] == "A test agent"
        assert result["system_prompt"] == "You are a test agent."
        assert result["created_at"] == "2026-01-01T00:00:00"
        assert result["updated_at"] == "2026-01-02T00:00:00"

    def test_includes_standard_structure(self):
        result = build_agent_yaml(
            agent_id="my-agent",
            name="My Agent",
            description="",
            system_prompt="",
            tool_allowlist=[],
            mcp_servers=[],
            created_at="",
            updated_at="",
        )

        assert result["profile"] == "my-agent"
        assert result["specialist"] == "generic"
        assert result["agent"]["enable_fast_path"] is True
        assert result["agent"]["router"]["use_llm_classification"] is True
        assert result["agent"]["router"]["max_follow_up_length"] == 100
        assert result["persistence"]["type"] == "file"
        assert result["persistence"]["work_dir"] == ".taskforce_my-agent"
        assert result["llm"]["config_path"] == "src/taskforce/configs/llm_config.yaml"
        assert result["llm"]["default_model"] == "main"
        assert result["logging"]["level"] == "DEBUG"
        assert result["logging"]["format"] == "console"

    def test_tools_empty_without_mapper(self):
        result = build_agent_yaml(
            agent_id="test",
            name="Test",
            description="",
            system_prompt="",
            tool_allowlist=["python", "shell"],
            mcp_servers=[],
            created_at="",
            updated_at="",
        )

        assert result["tools"] == []

    def test_tools_expanded_with_mapper(self, mock_tool_mapper):
        result = build_agent_yaml(
            agent_id="test",
            name="Test",
            description="",
            system_prompt="",
            tool_allowlist=["python", "shell"],
            mcp_servers=[],
            created_at="",
            updated_at="",
            tool_mapper=mock_tool_mapper,
        )

        mock_tool_mapper.map_tools.assert_called_once_with(["python", "shell"])
        assert result["tools"] == [
            {"type": "PythonTool", "module": "tools.python"},
            {"type": "ShellTool", "module": "tools.shell"},
        ]

    def test_includes_mcp_servers(self):
        servers = [{"type": "stdio", "command": "npx", "args": ["-y", "server"]}]

        result = build_agent_yaml(
            agent_id="test",
            name="Test",
            description="",
            system_prompt="",
            tool_allowlist=[],
            mcp_servers=servers,
            created_at="",
            updated_at="",
        )

        assert result["mcp_servers"] == servers

    def test_output_is_yaml_serializable(self):
        result = build_agent_yaml(
            agent_id="test",
            name="Test Agent",
            description="Description",
            system_prompt="You are a test.",
            tool_allowlist=["python"],
            mcp_servers=[{"type": "stdio"}],
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-02T00:00:00",
        )

        # Should not raise
        serialized = yaml.safe_dump(result)
        reloaded = yaml.safe_load(serialized)
        assert reloaded["agent_id"] == "test"
        assert reloaded["name"] == "Test Agent"
