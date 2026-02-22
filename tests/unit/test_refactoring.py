"""
Tests for the refactoring: unified agent definition, registry, and factory.
"""


import pytest

from taskforce.application.tool_registry import ToolRegistry
from taskforce.core.domain.agent_definition import (
    AgentDefinition,
    AgentDefinitionInput,
    AgentDefinitionUpdate,
    AgentSource,
    MCPServerConfig,
)
from taskforce.core.domain.config_schema import (
    MCPServerConfigSchema,
    extract_tool_names,
    validate_agent_config,
)
from taskforce.infrastructure.tools.registry import (
    get_all_tool_names,
    is_registered,
    register_tool,
    unregister_tool,
)


class TestAgentDefinition:
    """Tests for unified AgentDefinition model."""

    def test_create_custom_agent(self):
        """Test creating a custom agent definition."""
        definition = AgentDefinition.from_custom(
            agent_id="test-agent",
            name="Test Agent",
            description="A test agent",
            system_prompt="You are a test agent.",
            tools=["python", "file_read"],
        )

        assert definition.agent_id == "test-agent"
        assert definition.name == "Test Agent"
        assert definition.source == AgentSource.CUSTOM
        assert definition.tools == ["python", "file_read"]
        assert definition.is_mutable is True
        assert definition.has_custom_prompt is True
        assert definition.created_at is not None

    def test_create_from_profile(self):
        """Test creating agent definition from profile config."""
        config = {
            "agent": {
                "name": "Dev Agent",
                "specialist": "coding",
            },
            "tools": ["python", "file_read", "file_write"],
            "mcp_servers": [],
        }

        definition = AgentDefinition.from_profile("dev", config)

        assert definition.agent_id == "dev"
        assert definition.source == AgentSource.PROFILE
        assert definition.specialist == "coding"
        assert "python" in definition.tools
        assert definition.is_mutable is False

    def test_create_from_profile_with_dict_tools(self):
        """Test that dict-format tools are converted to registry names."""
        config = {
            "agent": {
                "name": "Mixed Tool Agent",
            },
            "tools": [
                "python",  # String format
                {"type": "FileReadTool"},  # Dict format - should become "file_read"
                {"type": "WebSearchTool", "params": {}},  # Dict with params
            ],
            "mcp_servers": [],
        }

        definition = AgentDefinition.from_profile("mixed", config)

        assert definition.agent_id == "mixed"
        assert "python" in definition.tools
        assert "file_read" in definition.tools  # Converted from FileReadTool
        assert "web_search" in definition.tools  # Converted from WebSearchTool
        assert "FileReadTool" not in definition.tools  # Not the raw class name

    def test_create_from_command(self):
        """Test creating agent definition from slash command."""
        agent_config = {
            "tools": ["web_search", "python"],
            "profile": "dev",
        }

        definition = AgentDefinition.from_command(
            name="search",
            source_path="/path/to/search.md",
            agent_config=agent_config,
            prompt_template="Search for: $ARGUMENTS",
            description="Web search command",
        )

        assert definition.agent_id == "cmd:search"
        assert definition.source == AgentSource.COMMAND
        assert "web_search" in definition.tools
        assert definition.prompt_template == "Search for: $ARGUMENTS"

    def test_to_dict_and_from_dict(self):
        """Test round-trip serialization."""
        definition = AgentDefinition.from_custom(
            agent_id="test",
            name="Test",
            tools=["python"],
            mcp_servers=[{"type": "stdio", "command": "npx", "args": ["-y", "test"]}],
        )

        data = definition.to_dict()
        restored = AgentDefinition.from_dict(data)

        assert restored.agent_id == definition.agent_id
        assert restored.tools == definition.tools
        assert len(restored.mcp_servers) == 1
        assert restored.mcp_servers[0].type == "stdio"

    def test_copy_with_updates(self):
        """Test creating a copy with updates."""
        original = AgentDefinition.from_custom(
            agent_id="test",
            name="Original",
            tools=["python"],
        )

        updated = original.copy_with(name="Updated", tools=["python", "file_read"])

        assert original.name == "Original"
        assert updated.name == "Updated"
        assert updated.tools == ["python", "file_read"]


class TestMCPServerConfig:
    """Tests for MCP server configuration."""

    def test_from_dict_stdio(self):
        """Test creating stdio MCP config from dict."""
        data = {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
            "env": {"MEMORY_FILE_PATH": ".memory/graph.jsonl"},
        }

        config = MCPServerConfig.from_dict(data)

        assert config.type == "stdio"
        assert config.command == "npx"
        assert len(config.args) == 2
        assert config.env["MEMORY_FILE_PATH"] == ".memory/graph.jsonl"

    def test_from_dict_sse(self):
        """Test creating SSE MCP config from dict."""
        data = {
            "type": "sse",
            "url": "http://localhost:8000/sse",
        }

        config = MCPServerConfig.from_dict(data)

        assert config.type == "sse"
        assert config.url == "http://localhost:8000/sse"

    def test_to_dict(self):
        """Test serializing MCP config."""
        config = MCPServerConfig(
            type="stdio",
            command="npx",
            args=["-y", "test"],
            env={"KEY": "value"},
        )

        data = config.to_dict()

        assert data["type"] == "stdio"
        assert data["command"] == "npx"
        assert data["env"]["KEY"] == "value"


class TestToolRegistry:
    """Tests for tool registry."""

    def test_get_available_tools(self):
        """Test listing available tools."""
        registry = ToolRegistry()
        tools = registry.get_available_tools()

        assert "python" in tools
        assert "file_read" in tools
        assert "web_search" in tools

    def test_is_valid_tool(self):
        """Test tool validation."""
        registry = ToolRegistry()

        assert registry.is_valid_tool("python") is True
        assert registry.is_valid_tool("file_read") is True
        assert registry.is_valid_tool("nonexistent_tool") is False

    def test_validate_tools(self):
        """Test validating a list of tools."""
        registry = ToolRegistry()

        valid, invalid = registry.validate_tools(
            ["python", "file_read", "nonexistent", "web_search"]
        )

        assert "python" in valid
        assert "file_read" in valid
        assert "web_search" in valid
        assert "nonexistent" in invalid

    def test_resolve_tools(self):
        """Test resolving tool names to instances."""
        registry = ToolRegistry()

        tools = registry.resolve(["file_read", "file_write"])

        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "file_read" in tool_names
        assert "file_write" in tool_names


class TestToolRegistryInfra:
    """Tests for tool registry extensions."""

    def test_get_all_tool_names(self):
        """Test getting all tool names."""
        names = get_all_tool_names()

        assert isinstance(names, list)
        assert "python" in names
        assert "web_search" in names
        assert "shell" in names  # Newly added

    def test_is_registered(self):
        """Test checking if tool is registered."""
        assert is_registered("python") is True
        assert is_registered("nonexistent") is False

    def test_register_and_unregister(self):
        """Test dynamic tool registration."""
        # Register a test tool
        register_tool(
            name="test_tool",
            tool_type="TestTool",
            module="test.module",
            params={"key": "value"},
        )

        assert is_registered("test_tool") is True

        # Unregister it
        result = unregister_tool("test_tool")
        assert result is True
        assert is_registered("test_tool") is False

        # Unregister non-existent
        result = unregister_tool("nonexistent")
        assert result is False

    def test_register_duplicate_raises(self):
        """Test that registering duplicate raises error."""
        with pytest.raises(ValueError, match="already registered"):
            register_tool(
                name="python",  # Already exists
                tool_type="PythonTool",
                module="test.module",
            )


class TestConfigSchema:
    """Tests for config schema validation."""

    def test_valid_agent_config(self):
        """Test validating a valid agent config."""
        data = {
            "agent_id": "test-agent",
            "name": "Test Agent",
            "tools": ["python", "file_read"],
        }

        schema = validate_agent_config(data)

        assert schema.agent_id == "test-agent"
        assert schema.tools == ["python", "file_read"]

    def test_tools_must_be_strings(self):
        """Test that tools must be strings, not dicts."""
        data = {
            "agent_id": "test-agent",
            "name": "Test Agent",
            "tools": [
                {"type": "PythonTool"},  # Invalid - should be string
            ],
        }

        with pytest.raises(Exception, match="string"):
            validate_agent_config(data)

    def test_mcp_server_validation(self):
        """Test MCP server schema validation."""
        schema = MCPServerConfigSchema(
            type="stdio",
            command="npx",
            args=["-y", "test"],
        )

        assert schema.type == "stdio"
        assert schema.command == "npx"

    def test_mcp_server_stdio_requires_command(self):
        """Test that stdio server requires command."""
        with pytest.raises(ValueError, match="requires 'command'"):
            MCPServerConfigSchema(type="stdio")

    def test_mcp_server_sse_requires_url(self):
        """Test that sse server requires url."""
        with pytest.raises(ValueError, match="requires 'url'"):
            MCPServerConfigSchema(type="sse")

    def test_extract_tool_names_from_mixed(self):
        """Test extracting tool names from mixed list."""
        tools = [
            "python",
            {"type": "FileReadTool"},
            "web_search",
            {"type": "FileWriteTool", "params": {}},
        ]

        names = extract_tool_names(tools)

        assert "python" in names
        assert "file_read" in names
        assert "web_search" in names
        assert "file_write" in names


class TestAgentDefinitionInput:
    """Tests for agent definition input model."""

    def test_to_definition(self):
        """Test converting input to definition."""
        input_def = AgentDefinitionInput(
            agent_id="new-agent",
            name="New Agent",
            description="A new agent",
            tools=["python"],
        )

        definition = input_def.to_definition()

        assert definition.agent_id == "new-agent"
        assert definition.source == AgentSource.CUSTOM
        assert definition.created_at is not None


class TestAgentDefinitionUpdate:
    """Tests for agent definition update model."""

    def test_partial_update(self):
        """Test that update only has specified fields."""
        update = AgentDefinitionUpdate(
            name="Updated Name",
            tools=["python", "file_read"],
        )

        assert update.name == "Updated Name"
        assert update.tools == ["python", "file_read"]
        assert update.description is None
        assert update.system_prompt is None
