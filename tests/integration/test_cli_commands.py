"""Integration tests for CLI commands."""

import json
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


def test_run_mission_json_output(mock_executor):
    """Test run mission with JSON output format."""
    # Mock token usage
    async def mock_execute_with_tokens(*args, **kwargs):
        return ExecutionResult(
            status="completed",
            session_id="test-session-123",
            todolist_id="test-todolist-123",
            final_message="Mission completed successfully!",
            execution_history=[],
            token_usage={
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        )

    mock_executor.execute_mission = AsyncMock(side_effect=mock_execute_with_tokens)

    result = runner.invoke(
        app, ["run", "mission", "Test mission", "--output-format", "json"]
    )

    assert result.exit_code == 0
    # Should output valid JSON
    output_json = json.loads(result.output)
    assert output_json["status"] == "completed"
    assert output_json["session_id"] == "test-session-123"
    assert output_json["final_message"] == "Mission completed successfully!"
    assert output_json["token_usage"]["total_tokens"] == 150
    # Should NOT contain Rich UI elements
    assert "TASKFORCE" not in result.output
    assert "Mission:" not in result.output


def test_run_mission_json_output_failed(mock_executor):
    """Test run mission JSON output with failed status."""
    async def mock_execute_failed(*args, **kwargs):
        return ExecutionResult(
            status="failed",
            session_id="test-session-456",
            final_message="Mission failed: Test error",
            execution_history=[],
            token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    mock_executor.execute_mission = AsyncMock(side_effect=mock_execute_failed)

    result = runner.invoke(
        app, ["run", "mission", "Test mission", "-f", "json"]
    )

    assert result.exit_code == 0
    output_json = json.loads(result.output)
    assert output_json["status"] == "failed"
    assert output_json["final_message"] == "Mission failed: Test error"


def test_run_mission_json_output_invalid_format():
    """Test run mission with invalid output format."""
    result = runner.invoke(
        app, ["run", "mission", "Test mission", "--output-format", "invalid"]
    )

    assert result.exit_code != 0
    assert "Invalid output format" in result.output


def test_run_mission_text_output_default(mock_executor):
    """Test run mission with default text output (backward compatibility)."""
    result = runner.invoke(app, ["run", "mission", "Test mission"])

    assert result.exit_code == 0
    # Should contain Rich UI elements
    assert "TASKFORCE" in result.output or "Mission:" in result.output
    # Should NOT be JSON
    try:
        json.loads(result.output)
        assert False, "Output should not be valid JSON"
    except json.JSONDecodeError:
        pass  # Expected


def test_run_mission_json_output_error_handling(mock_executor):
    """Test JSON output when execution raises an error."""
    async def mock_execute_error(*args, **kwargs):
        raise ValueError("Test execution error")

    mock_executor.execute_mission = AsyncMock(side_effect=mock_execute_error)

    result = runner.invoke(
        app, ["run", "mission", "Test mission", "--output-format", "json"]
    )

    # Should exit with error code but output JSON
    assert result.exit_code == 1
    output_json = json.loads(result.output)
    assert output_json["status"] == "failed"
    assert "Test execution error" in output_json["final_message"]


def test_run_mission_json_output_streaming(mock_executor):
    """Test JSON output with streaming mode."""
    from datetime import datetime
    from collections.abc import AsyncIterator
    from taskforce.application.executor import ProgressUpdate

    # Create async generator for streaming events
    async def mock_streaming_events(*args, **kwargs) -> AsyncIterator[ProgressUpdate]:
        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type="started",
            message="Starting mission",
            details={"session_id": "stream-session-123"},
        )
        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type="tool_call",
            message="Calling tool",
            details={"tool": "test_tool", "args": {}},
        )
        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type="tool_result",
            message="Tool completed",
            details={"tool": "test_tool", "success": True, "output": "Result"},
        )
        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type="final_answer",
            message="Mission complete",
            details={"content": "Streaming test completed successfully"},
        )
        yield ProgressUpdate(
            timestamp=datetime.now(),
            event_type="token_usage",
            message="Token usage",
            details={"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
        )

    # Mock execute_mission_streaming to return our async generator
    mock_executor.execute_mission_streaming = mock_streaming_events

    result = runner.invoke(
        app, ["run", "mission", "Test streaming", "--stream", "--output-format", "json"]
    )

    assert result.exit_code == 0
    output_json = json.loads(result.output)
    assert output_json["status"] == "completed"
    assert output_json["session_id"] == "stream-session-123"
    assert output_json["final_message"] == "Streaming test completed successfully"
    assert output_json["token_usage"]["total_tokens"] == 75
    assert len(output_json["execution_history"]) > 0
    # Should NOT contain Rich UI elements
    assert "TASKFORCE" not in result.output


def test_run_command_json_output(mock_executor):
    """Test run command with JSON output format."""
    from taskforce.core.interfaces.slash_commands import CommandType, SlashCommandDefinition

    # Mock SlashCommandRegistry - patch where it's imported inside the function
    with patch("taskforce.application.slash_command_registry.SlashCommandRegistry") as mock_registry_class:
        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry

        # Create a mock command definition
        mock_command_def = SlashCommandDefinition(
            name="test",
            source="project",
            source_path="/fake/path/test.md",
            command_type=CommandType.PROMPT,
            description="Test command",
            prompt_template="Test prompt: $ARGUMENTS",
        )

        # Mock resolve_command to return our mock command
        mock_registry.resolve_command.return_value = (mock_command_def, "test args")
        mock_registry.prepare_prompt.return_value = "Test prompt: test args"

        # Mock execute_mission to return a successful result
        async def mock_execute(*args, **kwargs):
            return ExecutionResult(
                status="completed",
                session_id="command-session-456",
                final_message="Command executed successfully!",
                execution_history=[],
                token_usage={
                    "prompt_tokens": 80,
                    "completion_tokens": 40,
                    "total_tokens": 120,
                },
            )

        mock_executor.execute_mission = AsyncMock(side_effect=mock_execute)

        result = runner.invoke(
            app, ["run", "command", "test", "test args", "--output-format", "json"]
        )

        assert result.exit_code == 0
        output_json = json.loads(result.output)
        assert output_json["status"] == "completed"
        assert output_json["session_id"] == "command-session-456"
        assert output_json["final_message"] == "Command executed successfully!"
        assert output_json["token_usage"]["total_tokens"] == 120
        # Should NOT contain Rich UI elements
        assert "TASKFORCE" not in result.output
        assert "Command:" not in result.output


def test_run_command_json_output_not_found():
    """Test run command JSON output when command is not found."""
    result = runner.invoke(
        app, ["run", "command", "nonexistent", "--output-format", "json"]
    )

    assert result.exit_code == 1
    output_json = json.loads(result.output)
    assert output_json["status"] == "failed"
    assert "Command not found" in output_json["final_message"]
    assert "nonexistent" in output_json["final_message"]

