"""Integration tests for long-term memory functionality via MCP Memory Server."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
def memory_config(temp_config_dir: Path, tmp_path: Path) -> Path:
    """Create test configuration with memory MCP server."""
    memory_work_dir = tmp_path / ".taskforce_test"
    memory_file = memory_work_dir / ".memory" / "knowledge_graph.jsonl"

    config = {
        "profile": "test_memory",
        "persistence": {"type": "file", "work_dir": str(memory_work_dir)},
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
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
                "env": {"MEMORY_FILE_PATH": str(memory_file)},
                "description": "Long-term memory for testing",
            }
        ],
    }

    config_path = temp_config_dir / "test_memory.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    return config_path


@pytest.fixture
def mock_memory_tools():
    """Mock memory tools that would be provided by MCP Memory Server."""
    return [
        {
            "name": "create_entities",
            "description": "Create new entities in the knowledge graph",
            "input_schema": {
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "entityType": {"type": "string"},
                                "observations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["name", "entityType", "observations"],
                        },
                    }
                },
                "required": ["entities"],
            },
        },
        {
            "name": "create_relations",
            "description": "Create relations between entities",
            "input_schema": {
                "type": "object",
                "properties": {
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "relationType": {"type": "string"},
                            },
                            "required": ["from", "to", "relationType"],
                        },
                    }
                },
                "required": ["relations"],
            },
        },
        {
            "name": "add_observations",
            "description": "Add observations to an entity",
            "input_schema": {
                "type": "object",
                "properties": {
                    "entityName": {"type": "string"},
                    "observations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["entityName", "observations"],
            },
        },
        {
            "name": "read_graph",
            "description": "Read the entire knowledge graph",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "search_nodes",
            "description": "Search for entities in the knowledge graph",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "name": "open_nodes",
            "description": "Open specific entities by name",
            "input_schema": {
                "type": "object",
                "properties": {
                    "names": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["names"],
            },
        },
        {
            "name": "delete_entities",
            "description": "Delete entities from the knowledge graph",
            "input_schema": {
                "type": "object",
                "properties": {
                    "entityNames": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["entityNames"],
            },
        },
        {
            "name": "delete_observations",
            "description": "Delete observations from an entity",
            "input_schema": {
                "type": "object",
                "properties": {
                    "entityName": {"type": "string"},
                    "observations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["entityName", "observations"],
            },
        },
        {
            "name": "delete_relations",
            "description": "Delete relations between entities",
            "input_schema": {
                "type": "object",
                "properties": {
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "relationType": {"type": "string"},
                            },
                            "required": ["from", "to", "relationType"],
                        },
                    }
                },
                "required": ["relations"],
            },
        },
    ]


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client for memory testing."""

    class MockMemoryClient:
        def __init__(self, tools):
            self._tools = tools
            self._storage = {"entities": [], "relations": []}

        async def list_tools(self):
            return self._tools

        async def call_tool(self, tool_name: str, arguments: dict):
            # Simulate memory operations
            if tool_name == "create_entities":
                entities = arguments.get("entities", [])
                self._storage["entities"].extend(entities)
                return {
                    "success": True,
                    "result": f"Created {len(entities)} entities",
                }

            elif tool_name == "read_graph":
                return {
                    "success": True,
                    "result": {
                        "entities": self._storage["entities"],
                        "relations": self._storage["relations"],
                    },
                }

            elif tool_name == "search_nodes":
                query = arguments.get("query", "")
                matching = [
                    e
                    for e in self._storage["entities"]
                    if query.lower() in e.get("name", "").lower()
                ]
                return {"success": True, "result": matching}

            else:
                return {"success": True, "result": f"Called {tool_name}"}

    return MockMemoryClient


@pytest.mark.asyncio
async def test_memory_directory_creation(
    temp_config_dir: Path, memory_config: Path, mock_memory_tools, mock_mcp_client, tmp_path: Path
):
    """Test that memory directory is automatically created."""
    memory_work_dir = tmp_path / ".taskforce_test"
    expected_memory_dir = memory_work_dir / ".memory"

    # Ensure directory doesn't exist before test
    assert not expected_memory_dir.exists()

    mock_client_instance = mock_mcp_client(mock_memory_tools)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "taskforce.infrastructure.tools.mcp.client.MCPClient.create_stdio",
        return_value=mock_ctx,
    ):
        factory = AgentFactory(config_dir=str(temp_config_dir))
        agent = await factory.create_agent(profile="test_memory")

        # Verify memory directory was created
        assert expected_memory_dir.exists()
        assert expected_memory_dir.is_dir()


@pytest.mark.asyncio
async def test_memory_tools_loaded(
    temp_config_dir: Path, memory_config: Path, mock_memory_tools, mock_mcp_client
):
    """Test that all memory tools are loaded from MCP server."""
    mock_client_instance = mock_mcp_client(mock_memory_tools)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "taskforce.infrastructure.tools.mcp.client.MCPClient.create_stdio",
        return_value=mock_ctx,
    ):
        factory = AgentFactory(config_dir=str(temp_config_dir))
        agent = await factory.create_agent(profile="test_memory")

        tool_names = list(agent.tools.keys())

        # Verify all memory tools are present
        expected_memory_tools = [
            "create_entities",
            "create_relations",
            "add_observations",
            "read_graph",
            "search_nodes",
            "open_nodes",
            "delete_entities",
            "delete_observations",
            "delete_relations",
        ]

        for tool_name in expected_memory_tools:
            assert tool_name in tool_names, f"Memory tool {tool_name} not loaded"


@pytest.mark.asyncio
async def test_memory_tool_execution(
    temp_config_dir: Path, memory_config: Path, mock_memory_tools, mock_mcp_client
):
    """Test that memory tools can be executed successfully."""
    mock_client_instance = mock_mcp_client(mock_memory_tools)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "taskforce.infrastructure.tools.mcp.client.MCPClient.create_stdio",
        return_value=mock_ctx,
    ):
        factory = AgentFactory(config_dir=str(temp_config_dir))
        agent = await factory.create_agent(profile="test_memory")

        # Test create_entities tool
        create_entities_tool = agent.tools.get("create_entities")
        assert create_entities_tool is not None

        result = await create_entities_tool.execute(
            entities=[
                {
                    "name": "TestUser",
                    "entityType": "User",
                    "observations": ["Prefers Python", "Works on backend"],
                }
            ]
        )

        assert result["success"] is True
        assert "Created 1 entities" in result["output"]

        # Test read_graph tool
        read_graph_tool = agent.tools.get("read_graph")
        assert read_graph_tool is not None

        result = await read_graph_tool.execute()

        assert result["success"] is True
        graph = result["result"]
        assert "entities" in graph
        assert len(graph["entities"]) == 1
        assert graph["entities"][0]["name"] == "TestUser"


@pytest.mark.asyncio
async def test_multiple_profiles_separate_memory(
    temp_config_dir: Path, tmp_path: Path, mock_memory_tools, mock_mcp_client
):
    """Test that different profiles have separate memory storage."""
    # Create two profiles with different memory paths
    profile1_work_dir = tmp_path / ".taskforce_profile1"
    profile2_work_dir = tmp_path / ".taskforce_profile2"

    config1 = {
        "profile": "profile1",
        "persistence": {"type": "file", "work_dir": str(profile1_work_dir)},
        "llm": {"config_path": "configs/llm_config.yaml"},
        "mcp_servers": [
            {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
                "env": {
                    "MEMORY_FILE_PATH": str(profile1_work_dir / ".memory" / "kg.jsonl")
                },
            }
        ],
    }

    config2 = {
        "profile": "profile2",
        "persistence": {"type": "file", "work_dir": str(profile2_work_dir)},
        "llm": {"config_path": "configs/llm_config.yaml"},
        "mcp_servers": [
            {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
                "env": {
                    "MEMORY_FILE_PATH": str(profile2_work_dir / ".memory" / "kg.jsonl")
                },
            }
        ],
    }

    # Write configs
    with open(temp_config_dir / "profile1.yaml", "w") as f:
        yaml.dump(config1, f)
    with open(temp_config_dir / "profile2.yaml", "w") as f:
        yaml.dump(config2, f)

    mock_client_instance = mock_mcp_client(mock_memory_tools)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "taskforce.infrastructure.tools.mcp.client.MCPClient.create_stdio",
        return_value=mock_ctx,
    ):
        factory = AgentFactory(config_dir=str(temp_config_dir))

        # Create agents with different profiles
        await factory.create_agent(profile="profile1")
        await factory.create_agent(profile="profile2")

        # Verify separate memory directories exist
        assert (profile1_work_dir / ".memory").exists()
        assert (profile2_work_dir / ".memory").exists()

        # Verify they are different directories
        assert profile1_work_dir / ".memory" != profile2_work_dir / ".memory"


@pytest.mark.asyncio
async def test_memory_config_without_env_var(
    temp_config_dir: Path, tmp_path: Path, mock_memory_tools, mock_mcp_client
):
    """Test that memory server works without explicit MEMORY_FILE_PATH."""
    config = {
        "profile": "test_no_env",
        "persistence": {"type": "file", "work_dir": str(tmp_path / ".taskforce")},
        "llm": {"config_path": "configs/llm_config.yaml"},
        "mcp_servers": [
            {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
                # No env dict - server should use default path
            }
        ],
    }

    with open(temp_config_dir / "test_no_env.yaml", "w") as f:
        yaml.dump(config, f)

    mock_client_instance = mock_mcp_client(mock_memory_tools)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "taskforce.infrastructure.tools.mcp.client.MCPClient.create_stdio",
        return_value=mock_ctx,
    ):
        factory = AgentFactory(config_dir=str(temp_config_dir))
        agent = await factory.create_agent(profile="test_no_env")

        # Should load memory tools successfully
        assert "create_entities" in agent.tools
        assert "read_graph" in agent.tools
