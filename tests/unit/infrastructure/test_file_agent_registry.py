"""
Unit tests for FileAgentRegistry helpers.
"""

from taskforce.api.schemas.agent_schemas import CustomAgentResponse
from taskforce.infrastructure.persistence.file_agent_registry import FileAgentRegistry


def test_build_agent_yaml_maps_tools(tmp_path):
    """Tool allowlist should map to full tool definitions."""
    registry = FileAgentRegistry(configs_dir=str(tmp_path))

    payload = registry._build_agent_yaml(
        agent_id="agent-1",
        name="Agent 1",
        description="Test agent",
        system_prompt="Prompt",
        tool_allowlist=["python"],
        mcp_servers=[],
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    assert payload["agent_id"] == "agent-1"
    assert payload["tools"][0]["type"] == "PythonTool"


def test_parse_custom_agent_yaml_uses_tool_definitions(tmp_path):
    """Parser should extract tool allowlist from tool definitions."""
    registry = FileAgentRegistry(configs_dir=str(tmp_path))
    data = registry._build_agent_yaml(
        agent_id="agent-2",
        name="Agent 2",
        description="Test agent",
        system_prompt="Prompt",
        tool_allowlist=["python"],
        mcp_servers=[],
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    parsed = registry._parse_custom_agent_yaml(data, agent_id="agent-2")

    assert isinstance(parsed, CustomAgentResponse)
    assert parsed.tool_allowlist == ["python"]


def test_parse_custom_agent_yaml_prefers_tool_allowlist(tmp_path):
    """Explicit tool_allowlist should override tool definitions."""
    registry = FileAgentRegistry(configs_dir=str(tmp_path))
    data = registry._build_agent_yaml(
        agent_id="agent-3",
        name="Agent 3",
        description="Test agent",
        system_prompt="Prompt",
        tool_allowlist=["python"],
        mcp_servers=[],
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    data["tool_allowlist"] = ["file_read"]

    parsed = registry._parse_custom_agent_yaml(data, agent_id="agent-3")

    assert parsed.tool_allowlist == ["file_read"]
