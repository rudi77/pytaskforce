"""
Integration Tests for Tool Catalog API
=======================================

Tests tool catalog endpoint and allowlist validation.

Story: 8.2 - Tool Catalog + Allowlist Validation
"""

import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from taskforce.api.server import create_app
from taskforce.infrastructure.persistence.file_agent_registry import (
    FileAgentRegistry,
)


@pytest.fixture
def temp_configs_dir(tmp_path):
    """Create temporary configs directory for testing."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    custom_dir = configs_dir / "custom"
    custom_dir.mkdir()
    return configs_dir


@pytest.fixture
def client(temp_configs_dir, monkeypatch):
    """Create test client with mocked registry."""
    from taskforce.api.routes import agents

    monkeypatch.setattr(
        agents,
        "_registry",
        FileAgentRegistry(configs_dir=str(temp_configs_dir)),
    )

    app = create_app()
    return TestClient(app)


def test_get_tools_catalog_success(client):
    """Test GET /api/v1/tools returns tool catalog."""
    response = client.get("/api/v1/tools")

    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert isinstance(data["tools"], list)
    assert len(data["tools"]) > 0

    # Check required native tools are present
    tool_names = {tool["name"] for tool in data["tools"]}
    required_tools = {
        "web_search",
        "web_fetch",
        "file_read",
        "file_write",
        "python",
        "git",
        "github",
        "powershell",
        "ask_user",
    }
    assert required_tools.issubset(tool_names)


def test_tool_catalog_structure(client):
    """Test tool catalog entries have required fields."""
    response = client.get("/api/v1/tools")

    assert response.status_code == 200
    data = response.json()

    for tool in data["tools"]:
        assert "name" in tool
        assert "description" in tool
        assert "parameters_schema" in tool
        assert "requires_approval" in tool
        assert "approval_risk_level" in tool
        assert "origin" in tool
        assert tool["origin"] == "native"


def test_create_agent_with_valid_tools(client):
    """Test creating agent with valid tool allowlist."""
    payload = {
        "agent_id": "test-agent",
        "name": "Test Agent",
        "description": "Test agent with valid tools",
        "system_prompt": "You are a test agent",
        "tool_allowlist": ["web_search", "file_read", "python"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }

    response = client.post("/api/v1/agents", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["tool_allowlist"] == ["web_search", "file_read", "python"]


def test_create_agent_with_invalid_tools(client):
    """Test creating agent with invalid tool names returns 400."""
    payload = {
        "agent_id": "test-agent",
        "name": "Test Agent",
        "description": "Test agent with invalid tools",
        "system_prompt": "You are a test agent",
        "tool_allowlist": ["web_search", "invalid_tool", "another_bad_tool"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }

    response = client.post("/api/v1/agents", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    detail = data["detail"]
    assert detail["error"] == "invalid_tools"
    assert "invalid_tool" in detail["invalid_tools"]
    assert "another_bad_tool" in detail["invalid_tools"]
    assert "available_tools" in detail
    assert isinstance(detail["available_tools"], list)


def test_create_agent_with_empty_allowlist(client):
    """Test creating agent with empty tool allowlist is allowed."""
    payload = {
        "agent_id": "test-agent",
        "name": "Test Agent",
        "description": "Test agent with no tools",
        "system_prompt": "You are a test agent",
        "tool_allowlist": [],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }

    response = client.post("/api/v1/agents", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["tool_allowlist"] == []


def test_update_agent_with_valid_tools(client):
    """Test updating agent with valid tool allowlist."""
    # First create an agent
    create_payload = {
        "agent_id": "test-agent",
        "name": "Test Agent",
        "description": "Test agent",
        "system_prompt": "You are a test agent",
        "tool_allowlist": ["web_search"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }
    client.post("/api/v1/agents", json=create_payload)

    # Update with different valid tools
    update_payload = {
        "name": "Updated Agent",
        "description": "Updated description",
        "system_prompt": "You are an updated agent",
        "tool_allowlist": ["file_read", "file_write", "python"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }

    response = client.put("/api/v1/agents/test-agent", json=update_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["tool_allowlist"] == ["file_read", "file_write", "python"]


def test_update_agent_with_invalid_tools(client):
    """Test updating agent with invalid tool names returns 400."""
    # First create an agent
    create_payload = {
        "agent_id": "test-agent",
        "name": "Test Agent",
        "description": "Test agent",
        "system_prompt": "You are a test agent",
        "tool_allowlist": ["web_search"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }
    client.post("/api/v1/agents", json=create_payload)

    # Try to update with invalid tools
    update_payload = {
        "name": "Updated Agent",
        "description": "Updated description",
        "system_prompt": "You are an updated agent",
        "tool_allowlist": ["web_search", "fake_tool"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }

    response = client.put("/api/v1/agents/test-agent", json=update_payload)

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    detail = data["detail"]
    assert detail["error"] == "invalid_tools"
    assert "fake_tool" in detail["invalid_tools"]


def test_tool_names_are_case_sensitive(client):
    """Test that tool names are case-sensitive."""
    payload = {
        "agent_id": "test-agent",
        "name": "Test Agent",
        "description": "Test agent with wrong case",
        "system_prompt": "You are a test agent",
        "tool_allowlist": ["Web_Search", "FILE_READ"],  # Wrong case
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }

    response = client.post("/api/v1/agents", json=payload)

    assert response.status_code == 400
    data = response.json()
    detail = data["detail"]
    assert detail["error"] == "invalid_tools"
    assert "Web_Search" in detail["invalid_tools"]
    assert "FILE_READ" in detail["invalid_tools"]


def test_all_native_tools_in_catalog(client):
    """Test that all required native tools are in catalog."""
    response = client.get("/api/v1/tools")

    assert response.status_code == 200
    data = response.json()
    tool_names = {tool["name"] for tool in data["tools"]}

    # All required tools from story acceptance criteria
    required_tools = {
        "web_search",
        "web_fetch",
        "file_read",
        "file_write",
        "python",
        "git",
        "github",
        "powershell",
        "ask_user",
    }

    assert required_tools == tool_names, (
        f"Missing tools: {required_tools - tool_names}, "
        f"Extra tools: {tool_names - required_tools}"
    )

