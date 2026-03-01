"""Tool for activating skills and executing workflows during agent execution.

This tool allows the LLM to activate a skill by name. If the skill has a
workflow defined, it executes the entire workflow directly without LLM
intervention for each step - saving tokens and ensuring deterministic execution.
"""

import os
from collections.abc import Awaitable, Callable
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

import structlog

from taskforce.application.workflow_runtime_service import WorkflowRuntimeService
from taskforce.core.domain.skill_workflow import (
    SkillWorkflow,
    SkillWorkflowExecutor,
    WorkflowContext,
)
from taskforce.core.domain.workflow_checkpoint import ResumeEvent
from taskforce.infrastructure.runtime.workflow_checkpoint_store import FileWorkflowCheckpointStore
from taskforce.infrastructure.tools.base_tool import BaseTool

ExternalWorkflowCallable = Callable[..., Awaitable[dict[str, Any]]]

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
                f"Skill '{skill.name}' aktiviert. " "Folge den Skill-Anweisungen im System-Prompt."
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
        workflow_data: dict[str, Any] = skill.workflow or {}
        workflow_engine = workflow_data.get("engine")

        if workflow_engine == "langgraph":
            return await self._execute_external_workflow(skill, input_vars)

        # Parse workflow definition
        workflow = SkillWorkflow.from_dict(workflow_data)

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

    async def _execute_external_workflow(
        self,
        skill: Any,
        input_vars: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute external workflow callable (e.g. LangGraph)."""
        workflow_data: dict[str, Any] = skill.workflow or {}
        callable_path = workflow_data.get("callable_path")
        if not isinstance(callable_path, str) or ":" not in callable_path:
            return {
                "success": False,
                "skill_name": skill.name,
                "has_workflow": True,
                "error": "Invalid workflow callable_path. Expected '<file>:<function>'",
            }

        logger.info(
            "workflow.external.started",
            skill=skill.name,
            engine=workflow_data.get("engine"),
            callable_path=callable_path,
        )

        resumed_checkpoint: dict[str, Any] | None = None
        try:
            resolved_input, resumed_checkpoint = self._resolve_resume_input(
                skill_name=skill.name,
                input_vars=input_vars,
            )
            workflow_callable = self._load_workflow_callable(skill.source_path, callable_path)
            external_result = await workflow_callable(
                tool_executor=self._execute_tool,
                input_vars=resolved_input,
                workflow=workflow_data,
            )
        except (TypeError, ValueError) as exc:
            return {
                "success": False,
                "skill_name": skill.name,
                "has_workflow": True,
                "error": str(exc),
            }

        if not isinstance(external_result, dict):
            return {
                "success": False,
                "skill_name": skill.name,
                "has_workflow": True,
                "error": "External workflow must return a dictionary result",
            }

        outputs = external_result.get("outputs", {})
        steps_executed = external_result.get("steps_executed", [])
        aborted = bool(external_result.get("aborted", False))
        switch_to_skill = external_result.get("switch_to_skill")
        waiting_for_input = external_result.get("waiting_for_input")

        result: dict[str, Any] = {
            "success": not aborted,
            "skill_name": skill.name,
            "has_workflow": True,
            "workflow_completed": not aborted and not switch_to_skill,
            "steps_executed": steps_executed,
            "outputs": outputs,
        }

        confidence_result = outputs.get("confidence_result", {})
        if confidence_result:
            result["recommendation"] = confidence_result.get("recommendation", "unknown")
            result["overall_confidence"] = confidence_result.get("overall_confidence", 0)
            result["force_auto_book"] = confidence_result.get("force_auto_book", False)

        rule_result = outputs.get("rule_result", {})
        if rule_result:
            result["rules_applied"] = rule_result.get("rules_applied", 0)
            result["booking_proposals"] = rule_result.get("booking_proposals", [])

        if aborted:
            result["error"] = external_result.get("error", "Workflow aborted")

        if switch_to_skill:
            result["switch_to_skill"] = switch_to_skill
            result["message"] = f"Workflow wechselt zu Skill: {switch_to_skill}"

        if resumed_checkpoint is not None:
            result["resumed_from_run_id"] = resumed_checkpoint.get("run_id")
            result["resume_status"] = resumed_checkpoint.get("status")

        if isinstance(waiting_for_input, dict):
            checkpoint = self._create_wait_checkpoint(
                skill_name=skill.name,
                input_vars=input_vars,
                waiting_for_input=waiting_for_input,
                outputs=outputs,
            )
            result["status"] = "waiting_external"
            result["workflow_completed"] = False
            result["run_id"] = checkpoint.run_id
            result["required_inputs"] = checkpoint.required_inputs
            result["blocking_reason"] = checkpoint.blocking_reason
            result["message"] = checkpoint.question or "Workflow wartet auf externe Eingabe"

        if result.get("recommendation") == "auto_book" and result.get("workflow_completed"):
            result["message"] = (
                "AUTO_BOOK: Buchung kann automatisch durchgeführt werden "
                "(bekannte Regel mit hoher Confidence)"
            )

        logger.info(
            "workflow.external.completed",
            skill=skill.name,
            aborted=aborted,
            switch_to=switch_to_skill,
            outputs=list(outputs.keys()),
        )
        return result

    def _resolve_resume_input(
        self,
        *,
        skill_name: str,
        input_vars: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Resolve merged input for resumed workflow executions."""
        resume_run_id = input_vars.get("resume_run_id")
        if not isinstance(resume_run_id, str) or not resume_run_id:
            return input_vars, None

        work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
        service = WorkflowRuntimeService(FileWorkflowCheckpointStore(work_dir=work_dir))
        checkpoint = service.get(resume_run_id)
        if checkpoint is None:
            raise ValueError(f"Workflow run not found: {resume_run_id}")
        if checkpoint.workflow_name != skill_name:
            raise ValueError(
                f"Workflow run '{resume_run_id}' belongs to '{checkpoint.workflow_name}', not '{skill_name}'"
            )

        resume_payload = input_vars.get("resume_payload")
        if not isinstance(resume_payload, dict):
            raise ValueError("resume_payload must be provided as an object for resumed workflows")

        resumed = service.resume(
            ResumeEvent(
                run_id=resume_run_id,
                input_type=str(input_vars.get("resume_input_type", "human_reply")),
                payload=resume_payload,
                sender_metadata=input_vars.get("resume_sender_metadata", {}),
            )
        )

        checkpoint_state = resumed.state if isinstance(resumed.state, dict) else {}
        restored_input = checkpoint_state.get("input_vars", {})
        if not isinstance(restored_input, dict):
            restored_input = {}
        restored_outputs = checkpoint_state.get("outputs", {})
        if not isinstance(restored_outputs, dict):
            restored_outputs = {}

        merged_input = {
            **restored_input,
            **input_vars,
            "resume_run_id": resume_run_id,
            "resume_payload": resume_payload,
            "checkpoint_outputs": restored_outputs,
        }
        return merged_input, resumed.to_dict()

    def _create_wait_checkpoint(
        self,
        *,
        skill_name: str,
        input_vars: dict[str, Any],
        waiting_for_input: dict[str, Any],
        outputs: dict[str, Any],
    ):
        """Persist a waiting checkpoint for later resume."""
        work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
        service = WorkflowRuntimeService(FileWorkflowCheckpointStore(work_dir=work_dir))
        return service.create_wait_checkpoint(
            session_id=str(input_vars.get("session_id", "")),
            workflow_name=skill_name,
            node_id=str(waiting_for_input.get("node_id", "unknown_node")),
            blocking_reason=str(waiting_for_input.get("blocking_reason", "unknown")),
            required_inputs=dict(waiting_for_input.get("required_inputs", {})),
            state={
                "input_vars": input_vars,
                "outputs": outputs,
            },
            question=waiting_for_input.get("question"),
            run_id=(
                waiting_for_input.get("run_id")
                if isinstance(waiting_for_input.get("run_id"), str)
                else None
            ),
        )

    def _load_workflow_callable(
        self,
        skill_source_path: str,
        callable_path: str,
    ) -> ExternalWorkflowCallable:
        """Load a workflow callable from '<file>:<function>' path."""
        file_part, function_name = callable_path.split(":", maxsplit=1)
        skill_root = Path(skill_source_path).resolve()
        module_path = (skill_root / file_part).resolve()
        if skill_root not in module_path.parents:
            raise ValueError("Workflow callable_path must stay within the skill directory")
        if not module_path.exists() or not module_path.is_file():
            raise ValueError(f"Workflow module not found: {module_path}")

        spec = spec_from_file_location(f"workflow_{module_path.stem}", module_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Unable to load workflow module: {module_path}")

        module = module_from_spec(spec)
        spec.loader.exec_module(module)

        workflow_callable = getattr(module, function_name, None)
        if workflow_callable is None:
            raise ValueError(f"Workflow callable '{function_name}' not found in {module_path}")
        if not callable(workflow_callable):
            raise ValueError(
                f"Workflow callable '{function_name}' in {module_path} is not callable"
            )
        return workflow_callable

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
