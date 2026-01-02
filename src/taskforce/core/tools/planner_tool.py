"""
Planner Tool

Allows the LLM to manage its own execution plan dynamically.
Replaces rigid TodoListManager with flexible, tool-based planning.
State is serializable for persistence via StateManager.
"""

from typing import Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class PlannerTool(ToolProtocol):
    """
    Tool for LLM-controlled plan management.

    Supports creating, reading, updating, and marking tasks complete.
    State is serializable for persistence via StateManager.

    The tool uses an action-based interface where the 'action' parameter
    determines which operation to perform. This design is LLM-friendly
    and allows for flexible plan management.
    """

    def __init__(self, initial_state: dict[str, Any] | None = None):
        """
        Initialize PlannerTool with optional restored state.

        Args:
            initial_state: Previously saved state dict to restore from.
                Format: {"tasks": [{"description": str,
                "status": "PENDING"|"DONE"}]}
        """
        self._state: dict[str, Any] = initial_state or {"tasks": []}

    @property
    def name(self) -> str:
        """Unique identifier for the tool."""
        return "planner"

    @property
    def description(self) -> str:
        """Human-readable description of tool's purpose."""
        return (
            "Manage your execution plan. "
            "Use 'action' to select operation.\n\n"
            "ACTIONS:\n"
            "1. create_plan - Create new plan (overwrites existing)\n"
            "   Required: tasks (list of strings)\n"
            "   Example: {action: create_plan, tasks: [Step 1, Step 2]}\n\n"
            "2. mark_done - Mark a step as completed\n"
            "   Required: step_index (integer, 1-based)\n"
            "   Example: {action: mark_done, step_index: 1}\n\n"
            "3. read_plan - View current plan status\n"
            "   No additional parameters needed\n"
            "   Example: {action: read_plan}\n\n"
            "4. update_plan - Add or remove steps\n"
            "   Optional: add_steps (list), remove_indices (list)\n"
            "   Example: {action: update_plan, add_steps: [New task]}\n\n"
            "OUTPUT: Markdown checklist like:\n"
            "[x] 1. Done step\n"
            "[ ] 2. Pending step"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Required. The operation to perform.",
                    "enum": [
                        "create_plan",
                        "mark_done",
                        "read_plan",
                        "update_plan",
                    ],
                },
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "For create_plan only. "
                        "List of task descriptions to create the plan."
                    ),
                },
                "step_index": {
                    "type": "integer",
                    "description": (
                        "For mark_done only. "
                        "Which step to mark complete (1 = first step)."
                    ),
                },
                "add_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "For update_plan only. "
                        "New tasks to append to the plan."
                    ),
                },
                "remove_indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "For update_plan only. "
                        "Step numbers to remove (1 = first step)."
                    ),
                },
            },
            "required": ["action"],
        }

    @property
    def requires_approval(self) -> bool:
        """Planner tool does not require approval (internal state only)."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Planner tool has low risk (internal state only)."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate preview for approval prompt."""
        action = kwargs.get("action", "unknown")
        if action == "create_plan":
            tasks = kwargs.get("tasks", [])
            return (
                f"Tool: {self.name}\nOperation: Create plan\n"
                f"Tasks: {len(tasks)} tasks"
            )
        elif action == "mark_done":
            step_index = kwargs.get("step_index", "?")
            return (
                f"Tool: {self.name}\nOperation: Mark step {step_index} "
                "as done"
            )
        elif action == "read_plan":
            return f"Tool: {self.name}\nOperation: Read current plan"
        elif action == "update_plan":
            add_count = len(kwargs.get("add_steps", []))
            remove_count = len(kwargs.get("remove_indices", []))
            return (
                f"Tool: {self.name}\nOperation: Update plan "
                f"(add: {add_count}, remove: {remove_count})"
            )
        return f"Tool: {self.name}\nOperation: {action}"

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        """
        Execute a planner action.

        Args:
            action: One of 'create_plan', 'mark_done', 'read_plan',
                'update_plan'
            **kwargs: Action-specific parameters

        Returns:
            Dict with success status and result/error message.
        """
        action_map = {
            "create_plan": self._create_plan,
            "mark_done": self._mark_done,
            "read_plan": self._read_plan,
            "update_plan": self._update_plan,
        }

        handler = action_map.get(action)
        if not handler:
            return {
                "success": False,
                "error": (
                    f"Unknown action: {action}. "
                    f"Valid: {list(action_map.keys())}"
                ),
            }

        try:
            return handler(**kwargs)
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution error: {str(e)}",
                "error_type": type(e).__name__,
            }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """
        Validate parameters before execution.

        Args:
            **kwargs: Parameters to validate

        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        if "action" not in kwargs:
            return False, "Missing required parameter: action"

        action = kwargs.get("action")
        valid_actions = [
            "create_plan",
            "mark_done",
            "read_plan",
            "update_plan",
        ]
        if action not in valid_actions:
            return (
                False,
                f"Invalid action: {action}. Valid: {valid_actions}",
            )

        # Action-specific validation
        if action == "create_plan":
            if "tasks" not in kwargs:
                return False, "Missing required parameter: tasks"
            if not isinstance(kwargs["tasks"], list):
                return False, "Parameter 'tasks' must be a list"
            if len(kwargs["tasks"]) == 0:
                return False, "Parameter 'tasks' must be a non-empty list"

        elif action == "mark_done":
            if "step_index" not in kwargs:
                return False, "Missing required parameter: step_index"
            if not isinstance(kwargs["step_index"], int):
                return False, "Parameter 'step_index' must be an integer"
            if kwargs["step_index"] < 1:
                return (
                    False,
                    "Parameter 'step_index' must be >= 1 "
                    "(1-based indexing)",
                )

        return True, None

    def get_state(self) -> dict[str, Any]:
        """
        Export current state for serialization.

        Returns:
            Dict containing current tasks state.
        """
        return dict(self._state)

    def set_state(self, state: dict[str, Any] | None) -> None:
        """
        Restore state from serialized data.

        Args:
            state: Previously saved state dict.
        """
        self._state = dict(state) if state else {"tasks": []}

    def _create_plan(
        self, tasks: list[str] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """
        Create a new plan from a list of task descriptions.

        Args:
            tasks: List of task description strings.

        Returns:
            Success dict with confirmation or error.
        """
        if not tasks or not isinstance(tasks, list) or len(tasks) == 0:
            return {
                "success": False,
                "error": "tasks must be a non-empty list of strings",
            }

        self._state["tasks"] = [
            {"description": task, "status": "PENDING"} for task in tasks
        ]

        return {
            "success": True,
            "message": f"Plan created with {len(tasks)} tasks.",
            "output": self._format_plan(),
        }

    def _mark_done(
        self, step_index: int | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """
        Mark a specific step as completed.

        Args:
            step_index: One-based index of the step to mark done.

        Returns:
            Success dict with updated status or error.
        """
        if step_index is None:
            return {"success": False, "error": "step_index is required"}

        tasks = self._state.get("tasks", [])

        if not tasks:
            return {"success": False, "error": "No active plan."}

        # Convert 1-based to 0-based index
        zero_based_index = step_index - 1

        if zero_based_index < 0 or zero_based_index >= len(tasks):
            return {
                "success": False,
                "error": (
                    f"step_index {step_index} out of bounds "
                    f"(1-{len(tasks)})"
                ),
            }

        tasks[zero_based_index]["status"] = "DONE"

        return {
            "success": True,
            "message": f"Step {step_index} marked done.",
            "output": self._format_plan(),
        }

    def _read_plan(self, **kwargs: Any) -> dict[str, Any]:
        """
        Return the current plan as formatted Markdown.

        Returns:
            Success dict with plan string or 'No active plan.'.
        """
        tasks = self._state.get("tasks", [])

        if not tasks:
            return {"success": True, "output": "No active plan."}

        return {"success": True, "output": self._format_plan()}

    def _update_plan(
        self,
        add_steps: list[str] | None = None,
        remove_indices: list[int] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Dynamically modify the plan by adding or removing steps.

        Args:
            add_steps: List of new task descriptions to append.
            remove_indices: List of 1-based indices to remove
                (processed in descending order).

        Returns:
            Success dict with updated plan or error.
        """
        tasks = self._state.get("tasks", [])

        # Remove steps first (in descending order to preserve indices)
        if remove_indices:
            # Convert 1-based to 0-based and sort descending
            zero_based_indices = sorted(
                [idx - 1 for idx in remove_indices], reverse=True
            )
            for idx in zero_based_indices:
                if 0 <= idx < len(tasks):
                    tasks.pop(idx)

        # Add new steps
        if add_steps:
            for step in add_steps:
                tasks.append({"description": step, "status": "PENDING"})

        self._state["tasks"] = tasks

        return {
            "success": True,
            "message": "Plan updated.",
            "output": self._format_plan(),
        }

    def _format_plan(self) -> str:
        """
        Format current plan as Markdown task list.

        Returns:
            Formatted string with checkbox syntax (1-based numbering).
        """
        tasks = self._state.get("tasks", [])
        if not tasks:
            return "No active plan."

        lines = []
        for i, task in enumerate(tasks, start=1):
            checkbox = "[x]" if task["status"] == "DONE" else "[ ]"
            lines.append(f"{checkbox} {i}. {task['description']}")

        return "\n".join(lines)
