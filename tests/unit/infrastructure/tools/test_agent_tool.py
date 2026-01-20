"""
Unit tests for AgentTool.

Tests the multi-agent orchestration tool in isolation with mocked dependencies.
"""

from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

import pytest

from taskforce.infrastructure.tools.orchestration.agent_tool import AgentTool
from taskforce.core.domain.models import ExecutionResult
from taskforce.core.interfaces.tools import ApprovalRiskLevel


class TestAgentTool:
    """Test suite for AgentTool."""

    @pytest.fixture
    def mock_factory(self):
        """Create a mock AgentFactory."""
        factory = MagicMock()
        factory.config_dir = Path("/tmp/configs")
        return factory

    @pytest.fixture
    def tool(self, mock_factory):
        """Create an AgentTool instance with mocked factory."""
        return AgentTool(
            agent_factory=mock_factory,
            profile="dev",
            work_dir="/tmp/workspace",
            max_steps=30,
        )

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "call_agent"
        assert "specialist sub-agent" in tool.description
        assert "coding" in tool.description
        assert "rag" in tool.description
        assert "wiki" in tool.description

    def test_tool_protocol_compliance(self, tool):
        """Test that AgentTool implements ToolProtocol correctly."""
        assert hasattr(tool, "name")
        assert hasattr(tool, "description")
        assert hasattr(tool, "parameters_schema")
        assert hasattr(tool, "requires_approval")
        assert hasattr(tool, "approval_risk_level")
        assert hasattr(tool, "supports_parallelism")
        assert hasattr(tool, "get_approval_preview")
        assert hasattr(tool, "execute")
        assert hasattr(tool, "validate_params")

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "mission" in schema["properties"]
        assert "specialist" in schema["properties"]
        assert "planning_strategy" in schema["properties"]
        assert "mission" in schema["required"]

        # Verify mission parameter
        assert schema["properties"]["mission"]["type"] == "string"
        assert "description" in schema["properties"]["mission"]

        # Verify planning_strategy has enum
        assert "enum" in schema["properties"]["planning_strategy"]
        strategies = schema["properties"]["planning_strategy"]["enum"]
        assert "native_react" in strategies
        assert "plan_and_execute" in strategies
        assert "plan_and_react" in strategies

    def test_requires_approval(self, tool):
        """Test that AgentTool requires approval."""
        assert tool.requires_approval is True

    def test_approval_risk_level(self, tool):
        """Test approval risk level."""
        assert tool.approval_risk_level == ApprovalRiskLevel.MEDIUM

    def test_supports_parallelism(self, tool):
        """Test that AgentTool supports parallel execution."""
        assert tool.supports_parallelism is True

    def test_get_approval_preview(self, tool):
        """Test approval preview generation."""
        preview = tool.get_approval_preview(
            specialist="coding",
            mission="This is a long mission description that should be truncated if it exceeds 150 characters because we want to keep the preview concise and readable for the user",
        )

        assert "SUB-AGENT EXECUTION" in preview
        assert "call_agent" in preview
        assert "coding" in preview
        assert "..." in preview  # Mission should be truncated

    def test_validate_params_success(self, tool):
        """Test successful parameter validation."""
        valid, error = tool.validate_params(
            mission="Analyze code quality",
            specialist="coding",
        )
        assert valid is True
        assert error is None

    def test_validate_params_missing_mission(self, tool):
        """Test validation fails when mission is missing."""
        valid, error = tool.validate_params(specialist="coding")
        assert valid is False
        assert "mission" in error.lower()

    def test_validate_params_empty_mission(self, tool):
        """Test validation fails when mission is empty."""
        valid, error = tool.validate_params(mission="   ", specialist="coding")
        assert valid is False
        assert "mission" in error.lower()

    def test_validate_params_invalid_planning_strategy(self, tool):
        """Test validation fails with invalid planning_strategy."""
        valid, error = tool.validate_params(
            mission="Test", planning_strategy="invalid_strategy"
        )
        assert valid is False
        assert "planning_strategy" in error.lower()

    def test_validate_params_valid_planning_strategies(self, tool):
        """Test validation succeeds with valid planning strategies."""
        strategies = ["native_react", "plan_and_execute", "plan_and_react"]

        for strategy in strategies:
            valid, error = tool.validate_params(
                mission="Test mission", planning_strategy=strategy
            )
            assert valid is True, f"Strategy {strategy} should be valid"
            assert error is None

    @pytest.mark.asyncio
    async def test_execute_with_standard_specialist(self, tool, mock_factory):
        """Test executing mission with standard specialist (coding/rag/wiki)."""
        # Setup mock sub-agent
        mock_agent = MagicMock()
        mock_agent.max_steps = 30
        mock_agent.execute = AsyncMock(
            return_value=ExecutionResult(
                status="completed",
                session_id="parent-123:sub_coding_abc123",
                final_message="Code analysis completed successfully",
                execution_history=[],
            )
        )
        mock_agent.cleanup = AsyncMock()

        mock_factory.create_agent = AsyncMock(return_value=mock_agent)

        # Execute
        result = await tool.execute(
            mission="Analyze code quality in src/",
            specialist="coding",
            _parent_session_id="parent-123",
        )

        # Verify
        assert result["success"] is True
        assert result["result"] == "Code analysis completed successfully"
        assert "parent-123:sub_coding_" in result["session_id"]
        assert result["status"] == "completed"

        # Verify factory was called correctly
        mock_factory.create_agent.assert_called_once()
        call_kwargs = mock_factory.create_agent.call_args[1]
        assert call_kwargs["specialist"] == "coding"
        assert call_kwargs["profile"] == "dev"
        assert call_kwargs["work_dir"] == "/tmp/workspace"

        # Verify cleanup was called
        mock_agent.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_handles_sub_agent_failure(self, tool, mock_factory):
        """Test that AgentTool handles sub-agent execution failures."""
        mock_agent = MagicMock()
        mock_agent.max_steps = 30
        mock_agent.execute = AsyncMock(
            return_value=ExecutionResult(
                status="error",
                session_id="parent-333:sub_coding_ccc333",
                final_message="Sub-agent failed: tool not found",
                execution_history=[],
            )
        )
        mock_agent.cleanup = AsyncMock()

        mock_factory.create_agent = AsyncMock(return_value=mock_agent)

        # Execute
        result = await tool.execute(
            mission="This will fail",
            specialist="coding",
            _parent_session_id="parent-333",
        )

        # Verify error handling
        assert result["success"] is False
        assert result["error"] == "Sub-agent failed: tool not found"
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self, tool, mock_factory):
        """Test that AgentTool handles exceptions during execution."""
        mock_factory.create_agent = AsyncMock(
            side_effect=Exception("Factory error")
        )

        # Execute
        result = await tool.execute(
            mission="This will raise exception",
            specialist="coding",
            _parent_session_id="parent-444",
        )

        # Verify exception handling
        assert result["success"] is False
        assert "error" in result
        assert "Factory error" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_generates_unique_session_ids(self, tool, mock_factory):
        """Test that each sub-agent gets a unique session ID."""
        session_ids = []

        for i in range(3):
            mock_agent = MagicMock()
            mock_agent.max_steps = 30
            mock_agent.execute = AsyncMock(
                return_value=ExecutionResult(
                    status="completed",
                    session_id=f"captured-{i}",
                    final_message=f"Result {i}",
                    execution_history=[],
                )
            )
            mock_agent.cleanup = AsyncMock()

            mock_factory.create_agent = AsyncMock(return_value=mock_agent)

            result = await tool.execute(
                mission=f"Mission {i}",
                specialist="coding",
                _parent_session_id="parent-555",
            )

            session_ids.append(result["session_id"])

        # Verify all session IDs are unique
        assert len(session_ids) == len(set(session_ids))
        # Verify all have correct prefix
        assert all(sid.startswith("parent-555:sub_coding_") for sid in session_ids)

    @pytest.mark.asyncio
    async def test_result_summarization_when_enabled(self, mock_factory):
        """Test that long results are summarized when enabled."""
        # Create tool with summarization enabled
        tool_with_summary = AgentTool(
            agent_factory=mock_factory,
            profile="dev",
            summarize_results=True,
            summary_max_length=100,
        )

        long_result = "x" * 500  # 500 chars

        mock_agent = MagicMock()
        mock_agent.max_steps = 30
        mock_agent.execute = AsyncMock(
            return_value=ExecutionResult(
                status="completed",
                session_id="parent-777:sub_coding_eee777",
                final_message=long_result,
                execution_history=[],
            )
        )
        mock_agent.cleanup = AsyncMock()

        mock_factory.create_agent = AsyncMock(return_value=mock_agent)

        # Execute
        result = await tool_with_summary.execute(
            mission="Test", specialist="coding", _parent_session_id="parent-777"
        )

        # Verify result was truncated
        assert len(result["result"]) <= 200  # Truncated + message
        assert "Result truncated" in result["result"]

    def test_find_agent_config_in_custom_file(self, tmp_path):
        """Test _find_agent_config finds agent in configs/custom/{specialist}.yaml."""
        # Setup directory structure
        configs_dir = tmp_path / "configs"
        custom_dir = configs_dir / "custom"
        custom_dir.mkdir(parents=True)

        # Create custom agent config
        (custom_dir / "my_agent.yaml").write_text("agent:\n  type: custom")

        mock_factory = MagicMock()
        mock_factory.config_dir = configs_dir

        tool = AgentTool(agent_factory=mock_factory)

        config_path = tool._find_agent_config("my_agent")

        assert config_path is not None
        assert config_path.name == "my_agent.yaml"
        assert "custom" in str(config_path)

    def test_find_agent_config_in_custom_directory(self, tmp_path):
        """Test _find_agent_config finds agent in configs/custom/{specialist}/ directory."""
        # Setup directory structure
        configs_dir = tmp_path / "configs"
        custom_agent_dir = configs_dir / "custom" / "my_agent_dir"
        custom_agent_dir.mkdir(parents=True)

        # Create custom agent config in subdirectory
        (custom_agent_dir / "my_agent_dir.yaml").write_text("agent:\n  type: custom")

        mock_factory = MagicMock()
        mock_factory.config_dir = configs_dir

        tool = AgentTool(agent_factory=mock_factory)

        config_path = tool._find_agent_config("my_agent_dir")

        assert config_path is not None
        assert config_path.name == "my_agent_dir.yaml"

    def test_find_agent_config_in_plugin_directory(self, tmp_path):
        """Test _find_agent_config finds agent in plugins/*/configs/agents/."""
        # Setup directory structure
        configs_dir = tmp_path / "configs"
        (configs_dir / "custom").mkdir(parents=True)

        # Setup plugin directory
        plugin_dir = tmp_path / "plugins" / "test_plugin" / "configs" / "agents"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin_agent.yaml").write_text("agent:\n  type: custom")

        mock_factory = MagicMock()
        mock_factory.config_dir = configs_dir

        tool = AgentTool(agent_factory=mock_factory)

        config_path = tool._find_agent_config("plugin_agent")

        assert config_path is not None
        assert config_path.name == "plugin_agent.yaml"
        assert "test_plugin" in str(config_path)
        assert "plugins" in str(config_path)

    def test_find_agent_config_priority_custom_over_plugin(self, tmp_path):
        """Test that configs/custom/ has priority over plugins/."""
        # Setup directory structure
        configs_dir = tmp_path / "configs"
        custom_dir = configs_dir / "custom"
        custom_dir.mkdir(parents=True)

        # Create agent in custom dir
        (custom_dir / "same_agent.yaml").write_text("source: custom")

        # Also create same agent in plugin dir
        plugin_dir = tmp_path / "plugins" / "test_plugin" / "configs" / "agents"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "same_agent.yaml").write_text("source: plugin")

        mock_factory = MagicMock()
        mock_factory.config_dir = configs_dir

        tool = AgentTool(agent_factory=mock_factory)

        config_path = tool._find_agent_config("same_agent")

        assert config_path is not None
        # Should find the custom one (has priority)
        assert "custom" in str(config_path)
        assert "plugins" not in str(config_path)

    def test_find_agent_config_not_found(self, tmp_path):
        """Test _find_agent_config returns None when agent not found."""
        # Setup empty directory structure
        configs_dir = tmp_path / "configs"
        (configs_dir / "custom").mkdir(parents=True)

        mock_factory = MagicMock()
        mock_factory.config_dir = configs_dir

        tool = AgentTool(agent_factory=mock_factory)

        config_path = tool._find_agent_config("nonexistent_agent")

        assert config_path is None
