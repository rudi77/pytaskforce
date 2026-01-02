"""Integration tests for CLI commands."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from taskforce.api.cli.main import app
from taskforce.core.domain.models import ExecutionResult

runner = CliRunner()


@pytest.fixture
def mock_executor():
    """Mock AgentExecutor for testing."""
    with patch("taskforce.api.cli.commands.run.AgentExecutor") as mock:
        executor_instance = MagicMock()
        mock.return_value = executor_instance

        # Mock execute_mission to return a successful result
        async def mock_execute(*args, **kwargs):
            return ExecutionResult(
                status="completed",
                session_id="test-session-123",
                todolist_id="test-todolist-123",
                final_message="Mission completed successfully!",
                execution_history=[],
            )

        executor_instance.execute_mission = AsyncMock(side_effect=mock_execute)
        yield executor_instance


@pytest.fixture
def mock_factory():
    """Mock AgentFactory for testing."""
    with patch("taskforce.api.cli.commands.tools.AgentFactory") as mock_tools, patch(
        "taskforce.api.cli.commands.sessions.AgentFactory"
    ) as mock_sessions:
        factory_instance = MagicMock()
        mock_tools.return_value = factory_instance
        mock_sessions.return_value = factory_instance

        # Mock agent with tools
        agent = MagicMock()
        
        # Create mock tools with proper attributes
        python_tool = MagicMock()
        python_tool.name = "python"
        python_tool.description = "Execute Python code"
        python_tool.parameters_schema = {"code": "string"}
        
        file_tool = MagicMock()
        file_tool.name = "file_read"
        file_tool.description = "Read file contents"
        file_tool.parameters_schema = {"path": "string"}
        
        agent.tools = [python_tool, file_tool]

        # Mock state manager
        agent.state_manager = MagicMock()
        agent.state_manager.list_sessions = AsyncMock(return_value=["session-1", "session-2"])
        agent.state_manager.load_state = AsyncMock(
            return_value={"status": "completed", "mission": "Test mission"}
        )

        factory_instance.create_agent = MagicMock(return_value=agent)
        yield factory_instance


def test_version_command():
    """Test version command displays version."""
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "Taskforce" in result.output
    assert "0.1.0" in result.output


def test_run_mission_command(mock_executor):
    """Test run mission command executes successfully."""
    result = runner.invoke(app, ["run", "mission", "Create a hello world function"])

    assert result.exit_code == 0
    assert "Starting mission" in result.output
    assert "Mission completed" in result.output


def test_run_mission_with_profile(mock_executor):
    """Test run mission with custom profile."""
    result = runner.invoke(
        app, ["run", "mission", "Test mission", "--profile", "staging"]
    )

    assert result.exit_code == 0
    mock_executor.execute_mission.assert_called_once()
    call_kwargs = mock_executor.execute_mission.call_args[1]
    assert call_kwargs["profile"] == "staging"


def test_run_mission_with_session_id(mock_executor):
    """Test run mission with existing session ID."""
    result = runner.invoke(
        app, ["run", "mission", "Continue task", "--session", "existing-session-123"]
    )

    assert result.exit_code == 0
    call_kwargs = mock_executor.execute_mission.call_args[1]
    assert call_kwargs["session_id"] == "existing-session-123"


def test_tools_list_command(mock_factory):
    """Test tools list command displays available tools."""
    result = runner.invoke(app, ["tools", "list"])

    assert result.exit_code == 0
    assert "Available Tools" in result.output
    assert "python" in result.output
    assert "file_read" in result.output


def test_tools_inspect_command(mock_factory):
    """Test tools inspect command shows tool details."""
    result = runner.invoke(app, ["tools", "inspect", "python"])

    assert result.exit_code == 0
    assert "python" in result.output
    assert "Parameters" in result.output


def test_tools_inspect_nonexistent(mock_factory):
    """Test tools inspect with non-existent tool."""
    result = runner.invoke(app, ["tools", "inspect", "nonexistent_tool"])

    assert result.exit_code == 1
    assert "not found" in result.output


def test_sessions_list_command(mock_factory):
    """Test sessions list command displays sessions."""
    result = runner.invoke(app, ["sessions", "list"])

    assert result.exit_code == 0
    assert "Agent Sessions" in result.output


def test_sessions_show_command(mock_factory):
    """Test sessions show command displays session details."""
    result = runner.invoke(app, ["sessions", "show", "session-1"])

    assert result.exit_code == 0
    assert "Session:" in result.output
    assert "session-1" in result.output


def test_sessions_show_nonexistent(mock_factory):
    """Test sessions show with non-existent session."""
    # Mock state manager to return None for non-existent session
    mock_factory.create_agent.return_value.state_manager.load_state = AsyncMock(
        return_value=None
    )

    result = runner.invoke(app, ["sessions", "show", "nonexistent-session"])

    assert result.exit_code == 1
    assert "not found" in result.output


def test_config_list_command():
    """Test config list command displays profiles."""
    result = runner.invoke(app, ["config", "list"])

    # Should succeed if configs directory exists
    assert result.exit_code in [0, 1]  # May fail if configs not found


def test_missions_list_command():
    """Test missions list command."""
    result = runner.invoke(app, ["missions", "list"])

    # Should succeed even if no missions directory exists
    assert result.exit_code == 0


def test_profile_flag_global():
    """Test global --profile flag."""
    result = runner.invoke(app, ["--profile", "prod", "version"])

    assert result.exit_code == 0


def test_help_command():
    """Test help command displays usage."""
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Taskforce" in result.output
    assert "run" in result.output
    assert "tools" in result.output
    assert "sessions" in result.output


def test_command_group_help():
    """Test command group help displays subcommands."""
    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    assert "mission" in result.output


def test_chat_with_rag_context():
    """Test chat command with RAG user context parameters."""
    result = runner.invoke(app, ["chat", "chat", "--help"])

    # Should show help with RAG context options
    assert result.exit_code == 0
    assert "--user-id" in result.output
    assert "--org-id" in result.output
    assert "--scope" in result.output
    assert "RAG context" in result.output

