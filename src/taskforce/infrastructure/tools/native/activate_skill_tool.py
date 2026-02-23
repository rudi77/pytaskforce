"""Tool for activating skills and executing workflows during agent execution.

This tool allows the LLM to activate a skill by name. If the skill has a
workflow defined, it executes the entire workflow directly without LLM
intervention for each step - saving tokens and ensuring deterministic execution.
"""

from typing import Any

import structlog

from taskforce.core.domain.skill_workflow import (
    SkillWorkflow,
    SkillWorkflowExecutor,
    WorkflowContext,
)
from taskforce.infrastructure.tools.base_tool import BaseTool

logger = structlog.get_logger(__name__)


class ActivateSkillTool(BaseTool):
    """Tool that activates a skill and optionally executes its workflow.

    Inherits from ``BaseTool`` to get default implementations for
    ``requires_approval``, ``approval_risk_level``, ``supports_parallelism``,
    ``get_approval_preview``, and ``validate_params``.

    When a skill with a workflow is activated:
    - The workflow is executed directly (no LLM calls per step)
    - All tools are called in sequence
    - Results are collected and returned

    When a skill without a workflow is activated:
    - The skill instructions are injected into the system prompt
    - The LLM continues with the next steps
    """

    tool_name = "activate_skill"
    tool_description = (
        "Activate a skill by name to execute its COMPLETE workflow automatically. "
        "IMPORTANT: The workflow runs ALL steps without further LLM interaction. "
        "For invoice processing, use skill_name='smart-booking-auto' with "
        "input={'file_path': '<path to PDF>'}. The workflow handles extraction, "
        "compliance check, accounting rules, and confidence evaluation automatically."
    )
    tool_parameters_schema = {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": (
                    "Name of the skill to activate. "
                    "Use 'smart-booking-auto' for invoice processing."
                ),
            },
            "input": {
                "type": "object",
                "description": (
                    "Input variables for the workflow. "
                    "For invoices: {'file_path': '<path to PDF>'}"
                ),
                "additionalProperties": True,
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the invoice file (PDF or image)",
                    }
                },
            },
        },
        "required": ["skill_name", "input"],
    }
    tool_requires_approval = False
    tool_supports_parallelism = False

    def __init__(self, agent_ref: Any = None):
        """Initialize with optional agent reference.

        Args:
            agent_ref: Reference to the agent instance.
        """
        self._agent_ref = agent_ref
        self._workflow_results: list[dict[str, Any]] = []

    def set_agent_ref(self, agent: Any) -> None:
        """Set agent reference after initialization.

        Args:
            agent: The agent instance to reference for skill activation.
        """
        self._agent_ref = agent

    async def _execute(self, **params: Any) -> dict[str, Any]:
        """Execute skill activation and workflow.

        Args:
            **params: Parameters including 'skill_name' and 'input'.

        Returns:
            Result dict with workflow execution results or activation confirmation.
        """
        skill_name = params.get("skill_name", "")
        input_vars = params.get("input", {})

        # Validate required parameters
        if not skill_name:
            return {
                "success": False,
                "error": "Missing required parameter 'skill_name'. "
                "Example: activate_skill(skill_name='smart-booking-auto', "
                "input={'file_path': '/path/to/invoice.pdf'})",
            }

        if not input_vars:
            return {
                "success": False,
                "error": f"Missing required parameter 'input' for skill '{skill_name}'. "
                "For invoice processing, provide: input={'file_path': '<path to PDF>'}",
            }

        if not self._agent_ref:
            return {"success": False, "error": "No agent reference configured"}

        if not hasattr(self._agent_ref, "skill_manager") or not self._agent_ref.skill_manager:
            return {"success": False, "error": "No skill manager configured"}

        # Activate the skill
        activated = self._agent_ref.activate_skill(skill_name)

        if not activated:
            available = self._agent_ref.skill_manager.list_skills()
            return {
                "success": False,
                "error": f"Skill '{skill_name}' nicht gefunden",
                "available_skills": available,
            }

        skill = self._agent_ref.skill_manager.active_skill

        # Check if skill has a workflow
        if skill.has_workflow:
            return await self._execute_workflow(skill, input_vars)

        # No workflow - just activate and return
        return {
            "success": True,
            "skill_name": skill.name,
            "has_workflow": False,
            "message": (
                f"Skill '{skill.name}' aktiviert. "
                "Folge den Skill-Anweisungen im System-Prompt."
            ),
        }

    async def _execute_workflow(
        self,
        skill: Any,
        input_vars: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a skill's workflow directly.

        Args:
            skill: The activated skill
            input_vars: Input variables for the workflow

        Returns:
            Workflow execution results
        """
        self._workflow_results = []

        # Parse workflow definition
        workflow = SkillWorkflow.from_dict(skill.workflow)

        logger.info(
            "workflow.started",
            skill=skill.name,
            steps=len(workflow.steps),
            input_keys=list(input_vars.keys()),
        )

        # Create executor with tool execution callback
        executor = SkillWorkflowExecutor(
            tool_executor=self._execute_tool,
            on_step_complete=self._on_step_complete,
            on_switch_skill=self._on_switch_skill,
        )

        # Execute workflow
        context = await executor.execute(workflow, input_vars)

        logger.info(
            "workflow.completed",
            skill=skill.name,
            aborted=context.aborted,
            switch_to=context.switch_to_skill,
            outputs=list(context.outputs.keys()),
        )

        # Build result
        result: dict[str, Any] = {
            "success": not context.aborted,
            "skill_name": skill.name,
            "has_workflow": True,
            "workflow_completed": not context.aborted and not context.switch_to_skill,
            "steps_executed": self._workflow_results,
            "outputs": context.outputs,
        }

        # Extract key decision info for LLM
        confidence_result = context.outputs.get("confidence_result", {})
        if confidence_result:
            result["recommendation"] = confidence_result.get("recommendation", "unknown")
            result["overall_confidence"] = confidence_result.get("overall_confidence", 0)
            result["force_auto_book"] = confidence_result.get("force_auto_book", False)

        # Add booking info if available
        rule_result = context.outputs.get("rule_result", {})
        if rule_result:
            result["rules_applied"] = rule_result.get("rules_applied", 0)
            result["booking_proposals"] = rule_result.get("booking_proposals", [])

        if context.aborted:
            result["error"] = context.error

        if context.switch_to_skill:
            result["switch_to_skill"] = context.switch_to_skill
            result["message"] = f"Workflow wechselt zu Skill: {context.switch_to_skill}"

        # Add clear message for auto-book case
        if result.get("recommendation") == "auto_book" and result.get("workflow_completed"):
            result["message"] = (
                "AUTO_BOOK: Buchung kann automatisch durchgeführt werden "
                "(bekannte Regel mit hoher Confidence)"
            )

        return result

    async def _execute_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
    ) -> Any:
        """Execute a tool through the agent.

        Args:
            tool_name: Name of the tool to execute
            params: Parameters for the tool

        Returns:
            Tool execution result
        """
        if not self._agent_ref:
            raise RuntimeError("No agent reference")

        # Find the tool - agent.tools is a dict[str, ToolProtocol]
        tool = self._agent_ref.tools.get(tool_name)

        if not tool:
            available = list(self._agent_ref.tools.keys())
            raise ValueError(f"Tool not found: {tool_name}. Available: {available}")

        logger.debug(
            "workflow.tool_execute",
            tool=tool_name,
            params_keys=list(params.keys()),
        )

        # Execute the tool
        result = await tool.execute(**params)

        logger.debug(
            "workflow.tool_complete",
            tool=tool_name,
            success=result.get("success", True) if isinstance(result, dict) else True,
        )

        return result

    def _on_step_complete(self, tool_name: str, result: Any) -> None:
        """Callback when a workflow step completes."""
        self._workflow_results.append(
            {
                "tool": tool_name,
                "success": result.get("success", True) if isinstance(result, dict) else True,
                "result_summary": self._summarize_result(result),
            }
        )

    def _on_switch_skill(self, skill_name: str, context: WorkflowContext) -> None:
        """Callback when workflow switches to another skill."""
        logger.info(
            "workflow.switch_skill",
            to_skill=skill_name,
            outputs=list(context.outputs.keys()),
        )

    def _summarize_result(self, result: Any) -> str:
        """Create a short summary of a tool result."""
        if isinstance(result, dict):
            if "error" in result:
                return f"Error: {result['error'][:100]}"
            if "success" in result:
                return "Success" if result["success"] else "Failed"
            return f"Keys: {', '.join(list(result.keys())[:5])}"
        return str(result)[:100]
