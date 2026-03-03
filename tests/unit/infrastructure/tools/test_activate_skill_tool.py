"""
Unit tests for ActivateSkillTool

Tests skill activation and workflow execution functionality.
"""

from unittest.mock import AsyncMock, MagicMock

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

    def test_validate_params_with_skill_name(self, tool):
        """Test parameter validation with valid skill name and input."""
        valid, err = tool.validate_params(
            skill_name="smart-booking-auto",
            input={"file_path": "test.pdf"},
        )
        assert valid is True
        assert err is None

    def test_validate_params_missing_skill_name(self, tool):
        """Test parameter validation without required skill_name."""
        valid, err = tool.validate_params(input={"file_path": "test.pdf"})
        assert valid is False
        assert err is not None

    def test_validate_params_missing_input(self, tool):
        """Test parameter validation without required input."""
        valid, err = tool.validate_params(skill_name="smart-booking-auto")
        assert valid is False
        assert err is not None

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
        result = await tool.execute(
            skill_name="smart-booking-auto", input={"file_path": "test.pdf"}
        )

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
        result = await tool.execute(
            skill_name="smart-booking-auto", input={"file_path": "test.pdf"}
        )

        assert result["success"] is True
        assert result["switch_to_skill"] == "smart-booking-hitl"
        assert result["workflow_completed"] is False

    @pytest.mark.asyncio
    async def test_execute_skill_with_external_workflow_callable(self, tool, tmp_path):
        """Test execution of a workflow loaded from external callable path."""
        workflow_file = tmp_path / "workflow_impl.py"
        workflow_file.write_text(
            """
async def run_workflow(*, tool_executor, input_vars, workflow):
    result = await tool_executor("test_tool", {"value": input_vars.get("x", 0)})
    return {
        "outputs": {"confidence_result": {"recommendation": "auto_book", "overall_confidence": 0.98}, "rule_result": {"rules_applied": 1, "booking_proposals": [{"konto": "4930"}]}, "tool": result},
        "steps_executed": [{"tool": "test_tool", "success": True, "result_summary": "Success"}],
        "aborted": False,
        "error": None,
        "switch_to_skill": None,
    }
""".strip()
        )

        mock_skill = MagicMock()
        mock_skill.name = "smart-booking-auto"
        mock_skill.has_workflow = True
        mock_skill.source_path = str(tmp_path)
        mock_skill.workflow = {
            "engine": "langgraph",
            "callable_path": "workflow_impl.py:run_workflow",
        }

        mock_skill_manager = MagicMock()
        mock_skill_manager.active_skill = mock_skill

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.execute = AsyncMock(return_value={"success": True, "ok": True})

        mock_agent = MagicMock()
        mock_agent.skill_manager = mock_skill_manager
        mock_agent.activate_skill.return_value = True
        mock_agent.tools = {"test_tool": mock_tool}

        tool.set_agent_ref(mock_agent)
        result = await tool.execute(skill_name="smart-booking-auto", input={"x": 1})

        assert result["success"] is True
        assert result["workflow_completed"] is True
        assert result["recommendation"] == "auto_book"
        assert result["rules_applied"] == 1

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

    @pytest.mark.asyncio
    async def test_external_workflow_creates_wait_checkpoint(self, tool, tmp_path, monkeypatch):
        """Waiting workflow state should be persisted as checkpoint."""
        monkeypatch.setenv("TASKFORCE_WORK_DIR", str(tmp_path))

        workflow_file = tmp_path / "workflow_wait.py"
        workflow_file.write_text(
            """
async def run_workflow(*, tool_executor, input_vars, workflow):
    return {
        "outputs": {"invoice_data": {"invoice_number": "INV-1"}},
        "steps_executed": [],
        "aborted": False,
        "error": None,
        "switch_to_skill": None,
        "waiting_for_input": {
            "node_id": "missing_fields",
            "blocking_reason": "missing_supplier_data",
            "required_inputs": {"required": ["supplier_reply"]},
            "question": "Bitte fehlende Daten senden",
            "run_id": "run-wait-1",
        },
    }
""".strip()
        )

        mock_skill = MagicMock()
        mock_skill.name = "smart-booking-auto"
        mock_skill.has_workflow = True
        mock_skill.source_path = str(tmp_path)
        mock_skill.workflow = {
            "engine": "langgraph",
            "callable_path": "workflow_wait.py:run_workflow",
        }

        mock_skill_manager = MagicMock()
        mock_skill_manager.active_skill = mock_skill

        mock_agent = MagicMock()
        mock_agent.skill_manager = mock_skill_manager
        mock_agent.activate_skill.return_value = True
        mock_agent.tools = {}

        tool.set_agent_ref(mock_agent)
        result = await tool.execute(skill_name="smart-booking-auto", input={"session_id": "sess-1"})

        assert result["success"] is True
        assert result["status"] == "waiting_external"
        assert result["run_id"] == "run-wait-1"
        assert result["workflow_completed"] is False

    @pytest.mark.asyncio
    async def test_external_workflow_rejects_non_dict_result(self, tool, tmp_path):
        """External workflow must return dict payload."""
        workflow_file = tmp_path / "workflow_invalid.py"
        workflow_file.write_text(
            """
async def run_workflow(*, tool_executor, input_vars, workflow):
    return ["not", "a", "dict"]
""".strip()
        )

        mock_skill = MagicMock()
        mock_skill.name = "smart-booking-auto"
        mock_skill.has_workflow = True
        mock_skill.source_path = str(tmp_path)
        mock_skill.workflow = {
            "engine": "langgraph",
            "callable_path": "workflow_invalid.py:run_workflow",
        }

        mock_skill_manager = MagicMock()
        mock_skill_manager.active_skill = mock_skill

        mock_agent = MagicMock()
        mock_agent.skill_manager = mock_skill_manager
        mock_agent.activate_skill.return_value = True
        mock_agent.tools = {}

        tool.set_agent_ref(mock_agent)
        result = await tool.execute(skill_name="smart-booking-auto", input={"x": 1})

        assert result["success"] is False
        assert "dictionary" in result["error"]

    @pytest.mark.asyncio
    async def test_external_workflow_rejects_path_traversal(self, tool, tmp_path):
        """Callable path must remain inside skill directory."""
        outside = tmp_path.parent / "outside_workflow.py"
        outside.write_text(
            """
async def run_workflow(*, tool_executor, input_vars, workflow):
    return {"outputs": {}, "steps_executed": [], "aborted": False, "error": None, "switch_to_skill": None}
""".strip()
        )

        mock_skill = MagicMock()
        mock_skill.name = "smart-booking-auto"
        mock_skill.has_workflow = True
        mock_skill.source_path = str(tmp_path)
        mock_skill.workflow = {
            "engine": "langgraph",
            "callable_path": "../outside_workflow.py:run_workflow",
        }

        mock_skill_manager = MagicMock()
        mock_skill_manager.active_skill = mock_skill

        mock_agent = MagicMock()
        mock_agent.skill_manager = mock_skill_manager
        mock_agent.activate_skill.return_value = True
        mock_agent.tools = {}

        tool.set_agent_ref(mock_agent)
        result = await tool.execute(skill_name="smart-booking-auto", input={"x": 1})

        assert result["success"] is False
        assert "skill directory" in result["error"]

    @pytest.mark.asyncio
    async def test_external_workflow_resume_run_uses_checkpoint(self, tool, tmp_path, monkeypatch):
        """Resume execution should load checkpoint and continue with resume payload."""
        monkeypatch.setenv("TASKFORCE_WORK_DIR", str(tmp_path))

        workflow_file = tmp_path / "workflow_resume.py"
        workflow_file.write_text(
            """
async def run_workflow(*, tool_executor, input_vars, workflow):
    assert input_vars.get("resume_payload", {}).get("supplier_reply") == "ok"
    assert input_vars.get("checkpoint_outputs", {}).get("invoice_data", {}).get("invoice_number") == "INV-2"
    return {
        "outputs": {"confidence_result": {"recommendation": "auto_book", "overall_confidence": 0.99}, "rule_result": {"rules_applied": 1, "booking_proposals": [{"konto": "4930"}]}, "invoice_data": input_vars.get("checkpoint_outputs", {}).get("invoice_data", {})},
        "steps_executed": [],
        "aborted": False,
        "error": None,
        "switch_to_skill": None,
    }
""".strip()
        )

        mock_skill = MagicMock()
        mock_skill.name = "smart-booking-auto"
        mock_skill.has_workflow = True
        mock_skill.source_path = str(tmp_path)
        mock_skill.workflow = {
            "engine": "langgraph",
            "callable_path": "workflow_resume.py:run_workflow",
        }

        mock_skill_manager = MagicMock()
        mock_skill_manager.active_skill = mock_skill

        mock_agent = MagicMock()
        mock_agent.skill_manager = mock_skill_manager
        mock_agent.activate_skill.return_value = True
        mock_agent.tools = {}

        tool.set_agent_ref(mock_agent)

        first = await tool.execute(
            skill_name="smart-booking-auto",
            input={
                "session_id": "sess-2",
                "resume_run_id": "run-missing",  # will fail before checkpoint exists
                "resume_payload": {"supplier_reply": "ok"},
            },
        )
        assert first["success"] is False

        # Create waiting checkpoint via dedicated test workflow output
        waiting_file = tmp_path / "workflow_wait_for_resume.py"
        waiting_file.write_text(
            """
async def run_workflow(*, tool_executor, input_vars, workflow):
    return {
        "outputs": {"invoice_data": {"invoice_number": "INV-2"}},
        "steps_executed": [],
        "aborted": False,
        "error": None,
        "switch_to_skill": None,
        "waiting_for_input": {
            "node_id": "missing_fields",
            "blocking_reason": "missing_supplier_data",
            "required_inputs": {"required": ["supplier_reply"]},
            "question": "Bitte Daten",
            "run_id": "run-resume-2",
        },
    }
""".strip()
        )
        mock_skill.workflow = {
            "engine": "langgraph",
            "callable_path": "workflow_wait_for_resume.py:run_workflow",
        }
        wait_result = await tool.execute(
            skill_name="smart-booking-auto", input={"session_id": "sess-2"}
        )
        assert wait_result["status"] == "waiting_external"

        mock_skill.workflow = {
            "engine": "langgraph",
            "callable_path": "workflow_resume.py:run_workflow",
        }
        resumed = await tool.execute(
            skill_name="smart-booking-auto",
            input={
                "session_id": "sess-2",
                "resume_run_id": "run-resume-2",
                "resume_payload": {"supplier_reply": "ok"},
            },
        )

        assert resumed["success"] is True
        assert resumed["workflow_completed"] is True
        assert resumed["resumed_from_run_id"] == "run-resume-2"

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
