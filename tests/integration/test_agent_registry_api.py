"""
Integration Tests for Agent Registry API
=========================================

Tests all CRUD endpoints for custom agent management.

Story: 8.1 - Custom Agent Registry (CRUD + YAML Persistence)
"""

import json
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

    # Create a sample profile config
    profile_data = {
        "profile": "test-profile",
        "specialist": "generic",
        "tools": [
            {
                "type": "PythonTool",
                "module": "taskforce.infrastructure.tools.native.python_tool",
                "params": {},
            }
        ],
        "mcp_servers": [],
        "llm": {"config_path": "configs/llm_config.yaml", "default_model": "main"},
        "persistence": {"type": "file", "work_dir": ".taskforce"},
    }
    with open(configs_dir / "test-profile.yaml", "w") as f:
        yaml.safe_dump(profile_data, f)

    return configs_dir


@pytest.fixture
def registry(temp_configs_dir):
    """Create FileAgentRegistry with temp directory."""
    return FileAgentRegistry(configs_dir=str(temp_configs_dir))


@pytest.fixture
def client(temp_configs_dir, monkeypatch):
    """Create test client with mocked registry."""
    # Patch the registry to use temp directory
    from taskforce.api.routes import agents

    monkeypatch.setattr(
        agents,
        "_registry",
        FileAgentRegistry(configs_dir=str(temp_configs_dir)),
    )

    app = create_app()
    return TestClient(app)


def test_create_agent_success(client):
    """Test successful agent creation."""
    payload = {
        "agent_id": "invoice-extractor",
        "name": "Invoice Extractor",
        "description": "Extracts structured fields from invoice text.",
        "system_prompt": "You are a LeanAgent specialized in invoice extraction.",
        "tool_allowlist": ["file_read", "python"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }

    response = client.post("/api/v1/agents", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["agent_id"] == "invoice-extractor"
    assert data["name"] == "Invoice Extractor"
    assert data["description"] == "Extracts structured fields from invoice text."
    assert data["system_prompt"] == "You are a LeanAgent specialized in invoice extraction."
    assert data["tool_allowlist"] == ["file_read", "python"]
    assert "created_at" in data
    assert "updated_at" in data
    assert data["source"] == "custom"


def test_create_agent_conflict(client):
    """Test creating agent with duplicate agent_id returns 409."""
    payload = {
        "agent_id": "test-agent",
        "name": "Test Agent",
        "description": "Test",
        "system_prompt": "Test prompt",
        "tool_allowlist": [],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }

    # Create first time
    response1 = client.post("/api/v1/agents", json=payload)
    assert response1.status_code == 201

    # Create second time (conflict)
    response2 = client.post("/api/v1/agents", json=payload)
    assert response2.status_code == 409
    assert "already exists" in response2.json()["detail"]


def test_create_agent_invalid_id(client):
    """Test creating agent with invalid agent_id returns 400."""
    payload = {
        "agent_id": "INVALID_ID",  # Uppercase not allowed
        "name": "Test Agent",
        "description": "Test",
        "system_prompt": "Test prompt",
        "tool_allowlist": [],
    }

    response = client.post("/api/v1/agents", json=payload)
    assert response.status_code == 422  # Pydantic validation error


def test_get_agent_success(client):
    """Test retrieving an existing agent."""
    # Create agent first
    payload = {
        "agent_id": "test-get",
        "name": "Test Get",
        "description": "Test",
        "system_prompt": "Test prompt",
        "tool_allowlist": ["python"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }
    client.post("/api/v1/agents", json=payload)

    # Get agent
    response = client.get("/api/v1/agents/test-get")
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "test-get"
    assert data["name"] == "Test Get"
    assert data["source"] == "custom"


def test_get_agent_not_found(client):
    """Test retrieving non-existent agent returns 404."""
    response = client.get("/api/v1/agents/nonexistent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_profile_agent(client):
    """Test retrieving a profile agent."""
    response = client.get("/api/v1/agents/test-profile")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "profile"
    assert data["profile"] == "test-profile"
    assert data["specialist"] == "generic"
    assert "tools" in data
    assert "llm" in data
    assert "persistence" in data


def test_list_agents_empty(client):
    """Test listing agents when only profile exists."""
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    # Should have at least the test-profile
    assert len(data["agents"]) >= 1
    profile_agents = [a for a in data["agents"] if a["source"] == "profile"]
    assert len(profile_agents) >= 1


def test_list_agents_with_custom(client):
    """Test listing agents includes both custom and profile."""
    # Create custom agent
    payload = {
        "agent_id": "custom-1",
        "name": "Custom 1",
        "description": "Test",
        "system_prompt": "Test prompt",
        "tool_allowlist": [],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }
    client.post("/api/v1/agents", json=payload)

    # List all
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    data = response.json()

    custom_agents = [a for a in data["agents"] if a["source"] == "custom"]
    profile_agents = [a for a in data["agents"] if a["source"] == "profile"]

    assert len(custom_agents) >= 1
    assert len(profile_agents) >= 1

    # Verify custom agent structure
    custom = next(a for a in custom_agents if a["agent_id"] == "custom-1")
    assert custom["name"] == "Custom 1"
    assert "created_at" in custom
    assert "updated_at" in custom


def test_update_agent_success(client):
    """Test updating an existing agent."""
    # Create agent
    create_payload = {
        "agent_id": "test-update",
        "name": "Original Name",
        "description": "Original description",
        "system_prompt": "Original prompt",
        "tool_allowlist": ["python"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }
    create_response = client.post("/api/v1/agents", json=create_payload)
    created_at = create_response.json()["created_at"]

    # Update agent
    update_payload = {
        "name": "Updated Name",
        "description": "Updated description",
        "system_prompt": "Updated prompt",
        "tool_allowlist": ["python", "file_read"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }
    response = client.put("/api/v1/agents/test-update", json=update_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "test-update"
    assert data["name"] == "Updated Name"
    assert data["description"] == "Updated description"
    assert data["system_prompt"] == "Updated prompt"
    assert data["tool_allowlist"] == ["python", "file_read"]
    assert data["created_at"] == created_at  # Preserved
    assert data["updated_at"] != created_at  # Changed


def test_update_agent_not_found(client):
    """Test updating non-existent agent returns 404."""
    payload = {
        "name": "Updated Name",
        "description": "Updated description",
        "system_prompt": "Updated prompt",
        "tool_allowlist": [],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }
    response = client.put("/api/v1/agents/nonexistent", json=payload)
    assert response.status_code == 404


def test_delete_agent_success(client):
    """Test deleting an existing agent."""
    # Create agent
    payload = {
        "agent_id": "test-delete",
        "name": "Test Delete",
        "description": "Test",
        "system_prompt": "Test prompt",
        "tool_allowlist": [],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }
    client.post("/api/v1/agents", json=payload)

    # Delete agent
    response = client.delete("/api/v1/agents/test-delete")
    assert response.status_code == 204

    # Verify deleted
    get_response = client.get("/api/v1/agents/test-delete")
    assert get_response.status_code == 404


def test_delete_agent_not_found(client):
    """Test deleting non-existent agent returns 404."""
    response = client.delete("/api/v1/agents/nonexistent")
    assert response.status_code == 404


def test_crud_workflow(client):
    """Test complete CRUD workflow: Create → Get → List → Update → Get → Delete → Get(404)."""
    agent_id = "workflow-test"

    # 1. Create
    create_payload = {
        "agent_id": agent_id,
        "name": "Workflow Test",
        "description": "Testing CRUD workflow",
        "system_prompt": "Test prompt",
        "tool_allowlist": ["python"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }
    create_resp = client.post("/api/v1/agents", json=create_payload)
    assert create_resp.status_code == 201

    # 2. Get
    get_resp = client.get(f"/api/v1/agents/{agent_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Workflow Test"

    # 3. List
    list_resp = client.get("/api/v1/agents")
    assert list_resp.status_code == 200
    agent_ids = [a["agent_id"] for a in list_resp.json()["agents"] if a["source"] == "custom"]
    assert agent_id in agent_ids

    # 4. Update
    update_payload = {
        "name": "Updated Workflow Test",
        "description": "Updated description",
        "system_prompt": "Updated prompt",
        "tool_allowlist": ["python", "file_read"],
        "mcp_servers": [],
        "mcp_tool_allowlist": [],
    }
    update_resp = client.put(f"/api/v1/agents/{agent_id}", json=update_payload)
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Updated Workflow Test"

    # 5. Get (verify update)
    get_resp2 = client.get(f"/api/v1/agents/{agent_id}")
    assert get_resp2.status_code == 200
    assert get_resp2.json()["name"] == "Updated Workflow Test"

    # 6. Delete
    delete_resp = client.delete(f"/api/v1/agents/{agent_id}")
    assert delete_resp.status_code == 204

    # 7. Get (404)
    get_resp3 = client.get(f"/api/v1/agents/{agent_id}")
    assert get_resp3.status_code == 404


def test_list_with_corrupt_yaml(registry, temp_configs_dir):
    """Test that corrupt YAML files are skipped during list."""
    # Create a valid agent
    from taskforce.api.schemas.agent_schemas import CustomAgentCreate

    valid_agent = CustomAgentCreate(
        agent_id="valid-agent",
        name="Valid Agent",
        description="Valid",
        system_prompt="Valid prompt",
        tool_allowlist=[],
    )
    registry.create_agent(valid_agent)

    # Create a corrupt YAML file
    corrupt_path = temp_configs_dir / "custom" / "corrupt-agent.yaml"
    with open(corrupt_path, "w") as f:
        f.write("invalid: yaml: content: [[[")

    # List should not crash
    agents = registry.list_agents()

    # Should only include valid agents
    custom_ids = [a.agent_id for a in agents if a.source == "custom"]
    assert "valid-agent" in custom_ids
    assert "corrupt-agent" not in custom_ids


def test_atomic_write_windows_safe(registry):
    """Test that YAML writes are atomic and Windows-safe."""
    from taskforce.api.schemas.agent_schemas import (
        CustomAgentCreate,
        CustomAgentUpdate,
    )

    # Create agent
    agent = CustomAgentCreate(
        agent_id="atomic-test",
        name="Atomic Test",
        description="Test atomic writes",
        system_prompt="Test prompt",
        tool_allowlist=["python"],
    )
    created = registry.create_agent(agent)
    assert created.agent_id == "atomic-test"

    # Update agent (tests overwrite scenario)
    update = CustomAgentUpdate(
        name="Updated Atomic Test",
        description="Updated",
        system_prompt="Updated prompt",
        tool_allowlist=["python", "file_read"],
    )
    updated = registry.update_agent("atomic-test", update)
    assert updated.name == "Updated Atomic Test"
    assert updated.created_at == created.created_at  # Preserved

    # Verify file exists and is valid YAML
    agent_path = registry._get_agent_path("atomic-test")
    assert agent_path.exists()

    with open(agent_path, "r") as f:
        data = yaml.safe_load(f)
    assert data["name"] == "Updated Atomic Test"
    assert data["created_at"] == created.created_at


def test_agent_id_validation(client):
    """Test agent_id validation rules."""
    # Too short
    response = client.post(
        "/api/v1/agents",
        json={
            "agent_id": "ab",
            "name": "Test",
            "description": "Test",
            "system_prompt": "Test",
            "tool_allowlist": [],
        },
    )
    assert response.status_code == 422

    # Too long
    response = client.post(
        "/api/v1/agents",
        json={
            "agent_id": "a" * 65,
            "name": "Test",
            "description": "Test",
            "system_prompt": "Test",
            "tool_allowlist": [],
        },
    )
    assert response.status_code == 422

    # Invalid characters (uppercase)
    response = client.post(
        "/api/v1/agents",
        json={
            "agent_id": "TestAgent",
            "name": "Test",
            "description": "Test",
            "system_prompt": "Test",
            "tool_allowlist": [],
        },
    )
    assert response.status_code == 422

    # Valid with hyphens and underscores
    response = client.post(
        "/api/v1/agents",
        json={
            "agent_id": "test-agent_123",
            "name": "Test",
            "description": "Test",
            "system_prompt": "Test",
            "tool_allowlist": [],
        },
    )
    assert response.status_code == 201

