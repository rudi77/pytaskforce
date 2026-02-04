"""
Integration tests for multi-agent orchestration.

Tests the full orchestration flow: orchestrator agent delegates
missions to specialist sub-agents with isolated sessions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.application.factory import AgentFactory
from taskforce.core.domain.models import ExecutionResult


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for testing."""
    provider = MagicMock()

    # Mock successful LLM response
    async def mock_complete(*args, **kwargs):
        return {
            "success": True,
            "content": "Mission completed successfully",
            "usage": {"total_tokens": 100},
        }

    provider.complete = AsyncMock(side_effect=mock_complete)
    return provider


@pytest.fixture
def orchestrator_config():
    """Configuration for orchestrator agent."""
    return {
        "agent": {
            "type": "generic",
            "specialist": None,
            "planning_strategy": "native_react",
            "max_steps": 50,
        },
        "orchestration": {
            "enabled": True,  # Enable orchestration
            "sub_agent_profile": "dev",
            "sub_agent_max_steps": 30,
        },
        "tools": [
            "web_search",
            "file_read",
            "file_write",
        ],
        "llm": {
            "config_path": "configs/llm_config.yaml",
            "default_model": "main",
        },
        "persistence": {
            "type": "file",
            "work_dir": ".taskforce",
        },
        "logging": {
            "level": "INFO",
        },
    }


@pytest.mark.asyncio
async def test_orchestrator_has_agent_tool(orchestrator_config, tmp_path):
    """Test that orchestrator agent has call_agent tool when enabled."""
    # Setup
    orchestrator_config["persistence"]["work_dir"] = str(tmp_path)

    factory = AgentFactory()

    # Mock _load_profile to return our test config
    with patch.object(factory, "_load_profile", return_value=orchestrator_config):
        agent = await factory.create_agent(profile="orchestrator")

    # Verify
    tool_names = [tool.name for tool in agent.tools.values()]
    assert "call_agent" in tool_names, "AgentTool should be added when orchestration.enabled=true"

    # Verify AgentTool properties
    agent_tool = agent.tools["call_agent"]
    assert agent_tool.name == "call_agent"
    assert "specialist sub-agent" in agent_tool.description.lower()
    assert agent_tool.supports_parallelism is True
    assert agent_tool.requires_approval is True

    # Cleanup
    


@pytest.mark.asyncio
async def test_orchestrator_without_flag_has_no_agent_tool(tmp_path):
    """Test that agent does NOT have call_agent tool when orchestration disabled."""
    # Setup - config WITHOUT orchestration.enabled
    config = {
        "agent": {
            "type": "generic",
            "specialist": None,
        },
        "tools": ["web_search", "file_read"],
        "llm": {"config_path": "configs/llm_config.yaml", "default_model": "main"},
        "persistence": {"type": "file", "work_dir": str(tmp_path)},
        "logging": {"level": "INFO"},
    }

    factory = AgentFactory()

    with patch.object(factory, "_load_profile", return_value=config):
        agent = await factory.create_agent(profile="dev")

    # Verify
    tool_names = [tool.name for tool in agent.tools.values()]
    assert "call_agent" not in tool_names, "AgentTool should NOT be added when orchestration.enabled is missing/false"

    # Cleanup
    


@pytest.mark.asyncio
async def test_agent_tool_generates_hierarchical_session_ids(orchestrator_config, tmp_path):
    """Test that AgentTool creates hierarchical session IDs for sub-agents."""
    # Setup
    orchestrator_config["persistence"]["work_dir"] = str(tmp_path)

    factory = AgentFactory()

    with patch.object(factory, "_load_profile", return_value=orchestrator_config):
        # Create orchestrator
        orchestrator = await factory.create_agent(profile="orchestrator")

        # Get AgentTool
        agent_tool = orchestrator.tools["call_agent"]

        # Mock sub-agent execution
        mock_sub_agent = MagicMock()
        mock_sub_agent.max_steps = 30
        mock_sub_agent.execute = AsyncMock(
            return_value=ExecutionResult(
                status="completed",
                session_id="parent-123:sub_coding_abc123",
                final_message="Code analysis complete",
                execution_history=[],
            )
        )
        mock_sub_agent.cleanup = AsyncMock()

        # Mock factory.create_agent to return our mock
        with patch.object(factory, "create_agent", return_value=mock_sub_agent) as mock_create:
            # Execute AgentTool
            result = await agent_tool.execute(
                mission="Analyze code quality",
                specialist="coding",
                _parent_session_id="parent-123",
            )

            # Verify sub-agent was created with correct specialist
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["specialist"] == "coding"

        # Verify
        assert result["success"] is True
        assert "parent-123:sub_coding_" in result["session_id"]

    # Cleanup
    


@pytest.mark.asyncio
async def test_agent_tool_loads_custom_agent_definition(tmp_path):
    """Test that AgentTool loads custom agent definitions from configs/custom/."""
    # Setup - create custom agent config
    custom_config_dir = tmp_path / "configs" / "custom"
    custom_config_dir.mkdir(parents=True)

    custom_agent_path = custom_config_dir / "test_specialist.yaml"
    custom_agent_path.write_text("""
agent:
  type: custom
  planning_strategy: native_react
  max_steps: 25

system_prompt: |
  You are a test specialist.

tool_allowlist:
  - file_read
  - python

persistence:
  type: file
  work_dir: .taskforce
""")

    # Create orchestrator config
    orchestrator_config = {
        "agent": {"type": "generic", "specialist": None},
        "orchestration": {"enabled": True, "sub_agent_profile": "dev"},
        "tools": ["web_search"],
        "llm": {"config_path": "configs/llm_config.yaml", "default_model": "main"},
        "persistence": {"type": "file", "work_dir": str(tmp_path)},
        "logging": {"level": "INFO"},
    }

    factory = AgentFactory(config_dir=str(tmp_path / "configs"))

    with patch.object(factory, "_load_profile", return_value=orchestrator_config):
        orchestrator = await factory.create_agent(profile="orchestrator")

        # Get AgentTool
        agent_tool = orchestrator.tools["call_agent"]

        # Mock sub-agent execution
        mock_custom_agent = MagicMock()
        mock_custom_agent.max_steps = 25
        mock_custom_agent.execute = AsyncMock(
            return_value=ExecutionResult(
                status="completed",
                session_id="parent-456:sub_test_specialist_def456",
                final_message="Custom agent completed",
                execution_history=[],
            )
        )
        mock_custom_agent.cleanup = AsyncMock()

        # Mock factory.create_agent
        with patch.object(
            factory, "create_agent", AsyncMock(return_value=mock_custom_agent)
        ) as mock_create_agent:
            # Execute AgentTool with custom specialist
            result = await agent_tool.execute(
                mission="Test mission",
                specialist="test_specialist",
                _parent_session_id="parent-456",
            )

            # Verify custom agent was created from definition
            mock_create_agent.assert_called_once()

        # Verify
        assert result["success"] is True
        assert result["result"] == "Custom agent completed"

    # Cleanup
    


@pytest.mark.asyncio
async def test_agent_tool_validates_parameters():
    """Test that AgentTool validates parameters correctly."""
    from taskforce.infrastructure.tools.orchestration import AgentTool

    factory = MagicMock()
    agent_tool = AgentTool(agent_factory=factory)

    # Test valid parameters
    valid, error = agent_tool.validate_params(
        mission="Test mission",
        specialist="coding",
    )
    assert valid is True
    assert error is None

    # Test missing mission
    valid, error = agent_tool.validate_params(specialist="coding")
    assert valid is False
    assert "mission" in error.lower()

    # Test empty mission
    valid, error = agent_tool.validate_params(mission="   ", specialist="coding")
    assert valid is False
    assert "mission" in error.lower()

    # Test invalid planning_strategy
    valid, error = agent_tool.validate_params(
        mission="Test", planning_strategy="invalid_strategy"
    )
    assert valid is False
    assert "planning_strategy" in error.lower()


@pytest.mark.asyncio
async def test_agent_tool_handles_sub_agent_failure(orchestrator_config, tmp_path):
    """Test that AgentTool handles sub-agent execution failures gracefully."""
    orchestrator_config["persistence"]["work_dir"] = str(tmp_path)

    factory = AgentFactory()

    with patch.object(factory, "_load_profile", return_value=orchestrator_config):
        orchestrator = await factory.create_agent(profile="orchestrator")
        agent_tool = orchestrator.tools["call_agent"]

        # Mock sub-agent that fails
        mock_failed_agent = MagicMock()
        mock_failed_agent.max_steps = 30
        mock_failed_agent.execute = AsyncMock(
            return_value=ExecutionResult(
                status="failed",
                session_id="parent-789:sub_coding_ghi789",
                final_message="Sub-agent execution failed: tool not found",
                execution_history=[],
            )
        )
        mock_failed_agent.cleanup = AsyncMock()

        with patch.object(factory, "create_agent", return_value=mock_failed_agent):
            result = await agent_tool.execute(
                mission="This will fail",
                specialist="coding",
                _parent_session_id="parent-789",
            )

        # Verify error handling
        assert result["success"] is False
        assert "error" in result or "result" in result

    # Cleanup
    
