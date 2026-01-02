"""Integration tests for MCP configuration and factory integration."""

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from taskforce.application.factory import AgentFactory


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create temporary config directory with test configurations."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def mock_mcp_config(temp_config_dir: Path) -> Path:
    """Create test configuration with MCP servers."""
    config = {
        "profile": "test",
        "persistence": {"type": "file", "work_dir": ".taskforce_test"},
        "llm": {"config_path": "configs/llm_config.yaml"},
        "tools": [
            {
                "type": "FileReadTool",
                "module": "taskforce.infrastructure.tools.native.file_tools",
                "params": {},
            }
        ],
        "mcp_servers": [
            {
                "type": "stdio",
                "command": "python",
                "args": ["test_server.py"],
                "env": {"TEST_KEY": "test_value"},
            },
            {"type": "sse", "url": "http://localhost:8000/sse"},
        ],
    }

    config_path = temp_config_dir / "test.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    return config_path


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client for testing."""

    class MockMCPClient:
        def __init__(self, tools: list[dict[str, Any]]):
            self._tools = tools

        async def list_tools(self):
            return self._tools

        async def call_tool(self, tool_name: str, arguments: dict):
            return {"success": True, "result": f"Called {tool_name}"}

    return MockMCPClient


@pytest.mark.asyncio
async def test_factory_loads_mcp_tools_from_config(
    temp_config_dir: Path, mock_mcp_config: Path, mock_mcp_client
):
    """Test that AgentFactory loads MCP tools from configuration."""
    # Mock MCP client creation
    mock_tools = [
        {
            "name": "test_tool_1",
            "description": "Test tool 1",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "test_tool_2",
            "description": "Test tool 2",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]

    mock_client_instance = mock_mcp_client(mock_tools)

    # Mock the context manager
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "taskforce.infrastructure.tools.mcp.client.MCPClient.create_stdio",
        return_value=mock_ctx,
    ):
        with patch(
            "taskforce.infrastructure.tools.mcp.client.MCPClient.create_sse",
            return_value=mock_ctx,
        ):
            factory = AgentFactory(config_dir=str(temp_config_dir))
            agent = await factory.create_agent(profile="test")

            # Verify agent has both native and MCP tools
            tool_names = list(agent.tools.keys())

            # Should have native tool
            assert "file_read" in tool_names

            # Should have MCP tools (2 servers × 2 tools each = 4 MCP tools)
            assert "test_tool_1" in tool_names
            assert "test_tool_2" in tool_names

            # Verify MCP contexts are stored on agent
            assert hasattr(agent, "_mcp_contexts")
            assert len(agent._mcp_contexts) == 2  # Two servers configured


@pytest.mark.asyncio
async def test_factory_handles_missing_mcp_config(temp_config_dir: Path):
    """Test that factory works when no MCP servers are configured."""
    config = {
        "profile": "test_no_mcp",
        "persistence": {"type": "file", "work_dir": ".taskforce_test"},
        "llm": {"config_path": "configs/llm_config.yaml"},
        "tools": [
            {
                "type": "FileReadTool",
                "module": "taskforce.infrastructure.tools.native.file_tools",
                "params": {},
            }
        ],
        # No mcp_servers key
    }

    config_path = temp_config_dir / "test_no_mcp.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    factory = AgentFactory(config_dir=str(temp_config_dir))
    agent = await factory.create_agent(profile="test_no_mcp")

    # Should have only native tools
    tool_names = list(agent.tools.keys())
    assert "file_read" in tool_names

    # Should have empty MCP contexts list
    assert hasattr(agent, "_mcp_contexts")
    assert len(agent._mcp_contexts) == 0


@pytest.mark.asyncio
async def test_factory_handles_mcp_connection_failure(
    temp_config_dir: Path, mock_mcp_config: Path
):
    """Test that factory gracefully handles MCP server connection failures."""

    # Mock connection failure
    async def mock_failing_context():
        raise ConnectionError("Failed to connect to MCP server")

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = mock_failing_context

    with patch(
        "taskforce.infrastructure.tools.mcp.client.MCPClient.create_stdio",
        return_value=mock_ctx,
    ):
        with patch(
            "taskforce.infrastructure.tools.mcp.client.MCPClient.create_sse",
            return_value=mock_ctx,
        ):
            factory = AgentFactory(config_dir=str(temp_config_dir))

            # Should not crash, but log warnings
            agent = await factory.create_agent(profile="test")

            # Should still have native tools
            tool_names = list(agent.tools.keys())
            assert "file_read" in tool_names

            # Should have no MCP tools due to connection failure
            # (only native tools loaded)
            assert len(agent.tools) == 1


@pytest.mark.asyncio
async def test_factory_handles_invalid_mcp_server_type(temp_config_dir: Path):
    """Test that factory handles invalid MCP server types gracefully."""
    config = {
        "profile": "test_invalid",
        "persistence": {"type": "file", "work_dir": ".taskforce_test"},
        "llm": {"config_path": "configs/llm_config.yaml"},
        "tools": [
            {
                "type": "FileReadTool",
                "module": "taskforce.infrastructure.tools.native.file_tools",
                "params": {},
            }
        ],
        "mcp_servers": [
            {
                "type": "invalid_type",  # Invalid server type
                "command": "python",
            }
        ],
    }

    config_path = temp_config_dir / "test_invalid.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    factory = AgentFactory(config_dir=str(temp_config_dir))

    # Should not crash, but log warnings
    agent = await factory.create_agent(profile="test_invalid")

    # Should only have native tools
    tool_names = list(agent.tools.keys())
    assert "file_read" in tool_names
    assert len(agent.tools) == 1


@pytest.mark.asyncio
async def test_factory_handles_missing_stdio_command(temp_config_dir: Path):
    """Test that factory handles stdio config missing command field."""
    config = {
        "profile": "test_missing_cmd",
        "persistence": {"type": "file", "work_dir": ".taskforce_test"},
        "llm": {"config_path": "configs/llm_config.yaml"},
        "tools": [
            {
                "type": "FileReadTool",
                "module": "taskforce.infrastructure.tools.native.file_tools",
                "params": {},
            }
        ],
        "mcp_servers": [
            {
                "type": "stdio",
                "args": ["test_server.py"],
                # Missing 'command' field
            }
        ],
    }

    config_path = temp_config_dir / "test_missing_cmd.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    factory = AgentFactory(config_dir=str(temp_config_dir))

    # Should not crash, but log warnings
    agent = await factory.create_agent(profile="test_missing_cmd")

    # Should only have native tools
    tool_names = list(agent.tools.keys())
    assert "file_read" in tool_names
    assert len(agent.tools) == 1


@pytest.mark.asyncio
async def test_factory_handles_missing_sse_url(temp_config_dir: Path):
    """Test that factory handles SSE config missing url field."""
    config = {
        "profile": "test_missing_url",
        "persistence": {"type": "file", "work_dir": ".taskforce_test"},
        "llm": {"config_path": "configs/llm_config.yaml"},
        "tools": [
            {
                "type": "FileReadTool",
                "module": "taskforce.infrastructure.tools.native.file_tools",
                "params": {},
            }
        ],
        "mcp_servers": [
            {
                "type": "sse",
                # Missing 'url' field
            }
        ],
    }

    config_path = temp_config_dir / "test_missing_url.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    factory = AgentFactory(config_dir=str(temp_config_dir))

    # Should not crash, but log warnings
    agent = await factory.create_agent(profile="test_missing_url")

    # Should only have native tools
    tool_names = list(agent.tools.keys())
    assert "file_read" in tool_names
    assert len(agent.tools) == 1


@pytest.mark.asyncio
async def test_mcp_tools_are_callable(
    temp_config_dir: Path, mock_mcp_config: Path, mock_mcp_client
):
    """Test that MCP tools can be executed through the wrapper."""
    mock_tools = [
        {
            "name": "echo_tool",
            "description": "Echoes input",
            "input_schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        }
    ]

    mock_client_instance = mock_mcp_client(mock_tools)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "taskforce.infrastructure.tools.mcp.client.MCPClient.create_stdio",
        return_value=mock_ctx,
    ):
        with patch(
            "taskforce.infrastructure.tools.mcp.client.MCPClient.create_sse",
            return_value=mock_ctx,
        ):
            factory = AgentFactory(config_dir=str(temp_config_dir))
            agent = await factory.create_agent(profile="test")

            # Find the MCP tool
            echo_tool = agent.tools.get("echo_tool")

            assert echo_tool is not None

            # Execute the tool
            result = await echo_tool.execute(message="Hello MCP!")

            assert result["success"] is True
            assert "echo_tool" in result["output"]

