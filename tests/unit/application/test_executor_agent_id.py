"""
Unit Tests for AgentExecutor with agent_id parameter (Story 8.3)

Tests the agent_id execution path that loads custom agents from registry
and creates LeanAgent instances.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.api.schemas.agent_schemas import CustomAgentResponse
from taskforce.application.executor import AgentExecutor
from taskforce.application.factory import AgentFactory
from taskforce.core.domain.models import ExecutionResult


@pytest.mark.asyncio
async def test_execute_mission_with_agent_id_success():
    """Test mission execution using agent_id loads custom agent."""
    # Mock factory
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123",
        status="completed",
        final_message="Success with custom agent",
        execution_history=[],
        todolist_id="todo-456",
    )
    mock_factory.create_lean_agent_from_definition = AsyncMock(return_value=mock_agent)

    # Mock registry
    mock_registry_response = CustomAgentResponse(
        source="custom",
        agent_id="test-agent",
        name="Test Agent",
        description="Test description",
        system_prompt="You are a test agent",
        tool_allowlist=["web_search", "python"],
        mcp_servers=[],
        mcp_tool_allowlist=[],
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    with patch(
        "taskforce.infrastructure.persistence.file_agent_registry.FileAgentRegistry"
    ) as mock_registry_class:
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = mock_registry_response
        mock_registry_class.return_value = mock_registry

        # Execute mission with agent_id
        executor = AgentExecutor(factory=mock_factory)
        result = await executor.execute_mission(
            mission="Test mission",
            profile="dev",
            agent_id="test-agent",
        )

        # Verify result
        assert result.status == "completed"
        assert result.final_message == "Success with custom agent"

        # Verify registry was called
        mock_registry.get_agent.assert_called_once_with("test-agent")

        # Verify factory method was called with agent definition
        mock_factory.create_lean_agent_from_definition.assert_called_once()
        call_args = mock_factory.create_lean_agent_from_definition.call_args
        agent_def = call_args.kwargs["agent_definition"]
        assert agent_def["system_prompt"] == "You are a test agent"
        assert agent_def["tool_allowlist"] == ["web_search", "python"]
        assert call_args.kwargs["profile"] == "dev"

        # Verify agent was executed
        mock_agent.execute.assert_called_once()


@pytest.mark.asyncio
async def test_execute_mission_agent_id_not_found():
    """Test mission execution with non-existent agent_id raises 404."""
    mock_factory = MagicMock(spec=AgentFactory)

    with patch(
        "taskforce.infrastructure.persistence.file_agent_registry.FileAgentRegistry"
    ) as mock_registry_class:
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = None  # Agent not found
        mock_registry_class.return_value = mock_registry

        executor = AgentExecutor(factory=mock_factory)

        # Should raise FileNotFoundError (404)
        with pytest.raises(FileNotFoundError, match="Agent 'nonexistent' not found"):
            await executor.execute_mission(
                mission="Test mission",
                profile="dev",
                agent_id="nonexistent",
            )


@pytest.mark.asyncio
async def test_execute_mission_agent_id_profile_agent_rejected():
    """Test that profile agents cannot be used via agent_id parameter."""
    from taskforce.api.schemas.agent_schemas import ProfileAgentResponse

    mock_factory = MagicMock(spec=AgentFactory)

    # Mock registry returning a profile agent (not custom)
    mock_profile_response = ProfileAgentResponse(
        source="profile",
        profile="dev",
        specialist=None,
        tools=[],
        mcp_servers=[],
        llm={},
        persistence={},
    )

    with patch(
        "taskforce.infrastructure.persistence.file_agent_registry.FileAgentRegistry"
    ) as mock_registry_class:
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = mock_profile_response
        mock_registry_class.return_value = mock_registry

        executor = AgentExecutor(factory=mock_factory)

        # Should raise ValueError (400)
        with pytest.raises(
            ValueError, match="is a profile agent, not a custom agent"
        ):
            await executor.execute_mission(
                mission="Test mission",
                profile="dev",
                agent_id="dev",  # Trying to use profile as agent_id
            )


@pytest.mark.asyncio
async def test_execute_mission_agent_id_takes_priority_over_lean_flag():
    """Test that agent_id takes priority over use_lean_agent flag."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123",
        status="completed",
        final_message="Success",
    )
    mock_factory.create_lean_agent_from_definition = AsyncMock(return_value=mock_agent)
    mock_factory.create_lean_agent = AsyncMock()  # Should NOT be called

    mock_registry_response = CustomAgentResponse(
        source="custom",
        agent_id="test-agent",
        name="Test Agent",
        description="Test",
        system_prompt="Test prompt",
        tool_allowlist=["python"],
        mcp_servers=[],
        mcp_tool_allowlist=[],
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    with patch(
        "taskforce.infrastructure.persistence.file_agent_registry.FileAgentRegistry"
    ) as mock_registry_class:
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = mock_registry_response
        mock_registry_class.return_value = mock_registry

        executor = AgentExecutor(factory=mock_factory)
        await executor.execute_mission(
            mission="Test",
            profile="dev",
            agent_id="test-agent",
            use_lean_agent=False,  # Should be ignored
        )

        # Verify agent_id path was used (not lean flag)
        mock_factory.create_lean_agent_from_definition.assert_called_once()
        mock_factory.create_lean_agent.assert_not_called()


@pytest.mark.asyncio
async def test_execute_mission_streaming_with_agent_id():
    """Test streaming execution with agent_id."""
    from taskforce.core.domain.models import StreamEvent

    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()

    # Mock streaming execution
    async def mock_stream(mission, session_id):
        yield StreamEvent(
            timestamp=datetime.now(),
            event_type="started",
            data={"message": "Starting"},
        )
        yield StreamEvent(
            timestamp=datetime.now(),
            event_type="complete",
            data={"message": "Done"},
        )

    from datetime import datetime

    mock_agent.execute_stream = mock_stream
    mock_factory.create_lean_agent_from_definition = AsyncMock(return_value=mock_agent)

    mock_registry_response = CustomAgentResponse(
        source="custom",
        agent_id="test-agent",
        name="Test Agent",
        description="Test",
        system_prompt="Test prompt",
        tool_allowlist=["python"],
        mcp_servers=[],
        mcp_tool_allowlist=[],
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    with patch(
        "taskforce.infrastructure.persistence.file_agent_registry.FileAgentRegistry"
    ) as mock_registry_class:
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = mock_registry_response
        mock_registry_class.return_value = mock_registry

        executor = AgentExecutor(factory=mock_factory)
        events = []
        async for update in executor.execute_mission_streaming(
            mission="Test",
            profile="dev",
            agent_id="test-agent",
        ):
            events.append(update)

        # Verify we got events
        assert len(events) >= 2  # At least started + complete
        assert events[0].event_type == "started"
        assert events[0].details["agent_id"] == "test-agent"


@pytest.mark.asyncio
async def test_execute_mission_backward_compatibility_without_agent_id():
    """Test that existing behavior works when agent_id is not provided."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123",
        status="completed",
        final_message="Success",
    )
    mock_factory.create_agent = AsyncMock(return_value=mock_agent)

    executor = AgentExecutor(factory=mock_factory)
    result = await executor.execute_mission(
        mission="Test mission",
        profile="dev",
        # No agent_id provided
    )

    # Verify legacy path was used
    mock_factory.create_agent.assert_called_once_with(profile="dev")
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_execute_mission_with_agent_id_and_mcp_tools():
    """Test agent_id with MCP tools in definition."""
    mock_factory = MagicMock(spec=AgentFactory)
    mock_agent = AsyncMock()
    mock_agent.execute.return_value = ExecutionResult(
        session_id="test-123",
        status="completed",
        final_message="Success",
    )
    mock_factory.create_lean_agent_from_definition = AsyncMock(return_value=mock_agent)

    # Agent with MCP servers configured
    mock_registry_response = CustomAgentResponse(
        source="custom",
        agent_id="mcp-agent",
        name="MCP Agent",
        description="Agent with MCP tools",
        system_prompt="You have MCP tools",
        tool_allowlist=["python"],
        mcp_servers=[
            {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
            }
        ],
        mcp_tool_allowlist=["read_file", "write_file"],
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    with patch(
        "taskforce.infrastructure.persistence.file_agent_registry.FileAgentRegistry"
    ) as mock_registry_class:
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = mock_registry_response
        mock_registry_class.return_value = mock_registry

        executor = AgentExecutor(factory=mock_factory)
        result = await executor.execute_mission(
            mission="Test",
            profile="dev",
            agent_id="mcp-agent",
        )

        # Verify agent definition included MCP config
        call_args = mock_factory.create_lean_agent_from_definition.call_args
        agent_def = call_args.kwargs["agent_definition"]
        assert len(agent_def["mcp_servers"]) == 1
        assert agent_def["mcp_tool_allowlist"] == ["read_file", "write_file"]
        assert result.status == "completed"

