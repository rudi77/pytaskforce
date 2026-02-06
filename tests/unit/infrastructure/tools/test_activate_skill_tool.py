"""
Unit tests for ActivateSkillTool

Tests skill activation and workflow execution functionality.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.infrastructure.tools.native.activate_skill_tool import ActivateSkillTool


class TestActivateSkillTool:
    """Test suite for ActivateSkillTool."""

    @pytest.fixture
    def tool(self):
        """Create an ActivateSkillTool instance."""
        return ActivateSkillTool()

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "activate_skill"
        assert "Activate a skill" in tool.description

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "skill_name" in schema["properties"]
        assert "input" in schema["properties"]
        assert "skill_name" in schema["required"]

    def test_validate_parameters_with_skill_name(self, tool):
        """Test parameter validation with valid skill name."""
        assert tool.validate_parameters({"skill_name": "smart-booking-auto"}) is True

    def test_validate_parameters_empty_skill_name(self, tool):
        """Test parameter validation with empty skill name."""
        assert tool.validate_parameters({"skill_name": ""}) is False

    def test_validate_parameters_missing_skill_name(self, tool):
        """Test parameter validation without skill name."""
        assert tool.validate_parameters({}) is False

    @pytest.mark.asyncio
    async def test_execute_no_agent_ref(self, tool):
        """Test execution without agent reference."""
        result = await tool.execute(skill_name="test-skill", input={"file_path": "test.pdf"})

        assert result["success"] is False
        assert "No agent reference" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_missing_skill_name(self, tool):
        """Test execution without skill_name parameter."""
        result = await tool.execute()

        assert result["success"] is False
        assert "Missing required parameter 'skill_name'" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_missing_input(self, tool):
        """Test execution without input parameter."""
        result = await tool.execute(skill_name="test-skill")

        assert result["success"] is False
        assert "Missing required parameter 'input'" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_no_skill_manager(self, tool):
        """Test execution with agent but no skill manager."""
        mock_agent = MagicMock()
        mock_agent.skill_manager = None

        tool.set_agent_ref(mock_agent)
        result = await tool.execute(skill_name="test-skill", input={"file_path": "test.pdf"})

        assert result["success"] is False
        assert "No skill manager" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_skill_not_found(self, tool):
        """Test execution when skill is not found."""
        mock_agent = MagicMock()
        mock_skill_manager = MagicMock()
        mock_skill_manager.list_skills.return_value = ["skill-a", "skill-b"]
        mock_agent.skill_manager = mock_skill_manager
        mock_agent.activate_skill.return_value = False

        tool.set_agent_ref(mock_agent)
        result = await tool.execute(skill_name="nonexistent-skill", input={"file_path": "test.pdf"})

        assert result["success"] is False
        assert "nicht gefunden" in result["error"]
        assert result["available_skills"] == ["skill-a", "skill-b"]

    @pytest.mark.asyncio
    async def test_execute_skill_without_workflow(self, tool):
        """Test activation of skill without workflow."""
        mock_skill = MagicMock()
        mock_skill.name = "simple-skill"
        mock_skill.has_workflow = False

        mock_skill_manager = MagicMock()
        mock_skill_manager.active_skill = mock_skill

        mock_agent = MagicMock()
        mock_agent.skill_manager = mock_skill_manager
        mock_agent.activate_skill.return_value = True

        tool.set_agent_ref(mock_agent)
        result = await tool.execute(skill_name="simple-skill", input={"data": "test"})

        assert result["success"] is True
        assert result["skill_name"] == "simple-skill"
        assert result["has_workflow"] is False
        assert "aktiviert" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_skill_with_workflow(self, tool):
        """Test execution of skill with workflow."""
        mock_skill = MagicMock()
        mock_skill.name = "smart-booking-auto"
        mock_skill.has_workflow = True
        mock_skill.workflow = {
            "steps": [
                {
                    "tool": "test_tool",
                    "params": {"key": "value"},
                    "output": "result",
                }
            ]
        }

        mock_skill_manager = MagicMock()
        mock_skill_manager.active_skill = mock_skill

        # Mock tool
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.execute = AsyncMock(return_value={"success": True, "data": "test"})

        mock_agent = MagicMock()
        mock_agent.skill_manager = mock_skill_manager
        mock_agent.activate_skill.return_value = True
        mock_agent.tools = {"test_tool": mock_tool}

        tool.set_agent_ref(mock_agent)
        result = await tool.execute(skill_name="smart-booking-auto", input={"file_path": "test.pdf"})

        assert result["success"] is True
        assert result["skill_name"] == "smart-booking-auto"
        assert result["has_workflow"] is True
        assert result["workflow_completed"] is True
        assert len(result["steps_executed"]) == 1
        assert result["steps_executed"][0]["tool"] == "test_tool"

    @pytest.mark.asyncio
    async def test_workflow_with_switch_to_skill(self, tool):
        """Test workflow that switches to another skill."""
        mock_skill = MagicMock()
        mock_skill.name = "smart-booking-auto"
        mock_skill.has_workflow = True
        mock_skill.workflow = {
            "steps": [
                {
                    "tool": "confidence_evaluator",
                    "params": {},
                    "output": "confidence_result",
                },
                {
                    "switch": {
                        "on": "confidence_result.recommendation",
                        "cases": {
                            "hitl_review": {"skill": "smart-booking-hitl"},
                        },
                    }
                },
            ]
        }

        mock_skill_manager = MagicMock()
        mock_skill_manager.active_skill = mock_skill

        # Mock tool that returns hitl_review recommendation
        mock_tool = MagicMock()
        mock_tool.name = "confidence_evaluator"
        mock_tool.execute = AsyncMock(
            return_value={"success": True, "recommendation": "hitl_review"}
        )

        mock_agent = MagicMock()
        mock_agent.skill_manager = mock_skill_manager
        mock_agent.activate_skill.return_value = True
        mock_agent.tools = {"confidence_evaluator": mock_tool}

        tool.set_agent_ref(mock_agent)
        result = await tool.execute(skill_name="smart-booking-auto", input={"file_path": "test.pdf"})

        assert result["success"] is True
        assert result["switch_to_skill"] == "smart-booking-hitl"
        assert result["workflow_completed"] is False

    @pytest.mark.asyncio
    async def test_workflow_abort_on_error(self, tool):
        """Test workflow abort when tool fails with abort_on_error."""
        mock_skill = MagicMock()
        mock_skill.name = "test-skill"
        mock_skill.has_workflow = True
        mock_skill.workflow = {
            "steps": [
                {
                    "tool": "failing_tool",
                    "params": {},
                    "abort_on_error": True,
                }
            ]
        }

        mock_skill_manager = MagicMock()
        mock_skill_manager.active_skill = mock_skill

        # Mock tool that fails
        mock_tool = MagicMock()
        mock_tool.name = "failing_tool"
        mock_tool.execute = AsyncMock(side_effect=ValueError("Tool failed"))

        mock_agent = MagicMock()
        mock_agent.skill_manager = mock_skill_manager
        mock_agent.activate_skill.return_value = True
        mock_agent.tools = {"failing_tool": mock_tool}

        tool.set_agent_ref(mock_agent)
        result = await tool.execute(skill_name="test-skill", input={"file_path": "test.pdf"})

        assert result["success"] is False
        assert "error" in result
        assert "failing_tool" in result["error"]

    def test_set_agent_ref(self, tool):
        """Test setting agent reference."""
        mock_agent = MagicMock()
        assert tool._agent_ref is None

        tool.set_agent_ref(mock_agent)

        assert tool._agent_ref is mock_agent

    def test_init_with_agent_ref(self):
        """Test initialization with agent reference."""
        mock_agent = MagicMock()
        tool = ActivateSkillTool(agent_ref=mock_agent)

        assert tool._agent_ref is mock_agent
