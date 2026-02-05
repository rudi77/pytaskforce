"""
Skill Workflow Models and Executor

Defines data structures for skill-driven workflows that execute
tool sequences without LLM intervention for each step.

This enables efficient, deterministic execution of multi-step tasks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class WorkflowStep:
    """
    A single step in a skill workflow.

    Attributes:
        tool: Name of the tool to execute
        params: Parameters to pass to the tool (supports variable substitution)
        output: Variable name to store the result
        optional: If True, step can be skipped on error
        abort_on_error: If True, abort workflow on error
        condition: Optional condition to check before executing
    """

    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    output: str | None = None
    optional: bool = False
    abort_on_error: bool = False
    condition: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        """Create from dictionary."""
        return cls(
            tool=data["tool"],
            params=data.get("params", {}),
            output=data.get("output"),
            optional=data.get("optional", False),
            abort_on_error=data.get("abort_on_error", False),
            condition=data.get("condition"),
        )


@dataclass
class WorkflowSwitch:
    """
    A conditional switch point in a workflow.

    Attributes:
        on: Variable path to check (e.g., "confidence_result.recommendation")
        cases: Mapping of values to actions
        default: Default action if no case matches
    """

    on: str
    cases: dict[str, dict[str, Any]] = field(default_factory=dict)
    default: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowSwitch:
        """Create from dictionary."""
        # Handle YAML quirk where 'on' is parsed as boolean True
        on_value = data.get("on") or data.get(True)
        if on_value is None:
            raise ValueError(
                f"WorkflowSwitch missing 'on' key. Got keys: {list(data.keys())}, data: {data}"
            )
        return cls(
            on=on_value,
            cases=data.get("cases", {}),
            default=data.get("default"),
        )


@dataclass
class SkillWorkflow:
    """
    A complete workflow definition for a skill.

    Attributes:
        steps: Ordered list of workflow steps
        on_complete: Action to take on successful completion
        on_error: Action to take on error
    """

    steps: list[WorkflowStep | WorkflowSwitch] = field(default_factory=list)
    on_complete: str | None = None
    on_error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillWorkflow:
        """Create from dictionary."""
        steps = []
        for step_data in data.get("steps", []):
            if "switch" in step_data:
                steps.append(WorkflowSwitch.from_dict(step_data["switch"]))
            elif "tool" in step_data:
                steps.append(WorkflowStep.from_dict(step_data))
        return cls(
            steps=steps,
            on_complete=data.get("on_complete"),
            on_error=data.get("on_error"),
        )

    @property
    def has_steps(self) -> bool:
        """Check if workflow has any steps."""
        return len(self.steps) > 0


@dataclass
class WorkflowContext:
    """
    Runtime context for workflow execution.

    Stores input variables, step outputs, and execution state.
    """

    input: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    current_step: int = 0
    aborted: bool = False
    error: str | None = None
    switch_to_skill: str | None = None

    def get_variable(self, path: str) -> Any:
        """
        Get a variable value by path.

        Supports:
        - input.xxx: Input variables
        - xxx: Output from previous step
        - xxx.yyy: Nested access into output dict

        Args:
            path: Variable path (e.g., "invoice_data" or "input.file_path")

        Returns:
            Variable value or None if not found
        """
        if path.startswith("input."):
            key = path[6:]  # Remove "input." prefix
            return self._get_nested(self.input, key)
        return self._get_nested(self.outputs, path)

    def _get_nested(self, data: dict[str, Any], path: str) -> Any:
        """Get a nested value from a dict using dot notation and array indices."""
        parts = path.split(".")
        current = data

        for part in parts:
            if current is None:
                return None

            # Check for array index syntax: key[0], key[1], etc.
            if "[" in part and part.endswith("]"):
                # Split into key and index: "rule_matches[0]" -> "rule_matches", "0"
                bracket_pos = part.index("[")
                key = part[:bracket_pos]
                index_str = part[bracket_pos + 1:-1]

                # Get the array first
                if isinstance(current, dict):
                    current = current.get(key)
                else:
                    return None

                # Then get the index
                if current is None:
                    return None
                if isinstance(current, (list, tuple)):
                    try:
                        index = int(index_str)
                        if 0 <= index < len(current):
                            current = current[index]
                        else:
                            return None  # Index out of range
                    except ValueError:
                        return None  # Invalid index
                else:
                    return None  # Not a list
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return None

        return current

    def set_output(self, name: str, value: Any) -> None:
        """Store an output value."""
        self.outputs[name] = value


class WorkflowVariableResolver:
    """Resolves variable references in workflow parameters."""

    # Pattern for ${variable.path} references
    VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

    def __init__(self, context: WorkflowContext):
        self.context = context

    def resolve(self, value: Any) -> Any:
        """
        Resolve variable references in a value.

        Handles:
        - Strings with ${var} references
        - Nested dicts
        - Lists

        Args:
            value: Value to resolve

        Returns:
            Resolved value
        """
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        return value

    def _resolve_string(self, value: str) -> Any:
        """Resolve a string value."""
        # Check if entire string is a variable reference
        match = self.VAR_PATTERN.fullmatch(value)
        if match:
            # Return the actual value (preserves type)
            return self.context.get_variable(match.group(1))

        # Replace embedded references
        def replace_var(m: re.Match) -> str:
            var_value = self.context.get_variable(m.group(1))
            return str(var_value) if var_value is not None else ""

        return self.VAR_PATTERN.sub(replace_var, value)


class SkillWorkflowExecutor:
    """
    Executes skill workflows directly without LLM intervention.

    This enables efficient, deterministic execution of multi-step tasks
    by calling tools directly in sequence.
    """

    def __init__(
        self,
        tool_executor: Callable[[str, dict[str, Any]], Any],
        on_step_complete: Callable[[str, Any], None] | None = None,
        on_switch_skill: Callable[[str, WorkflowContext], None] | None = None,
    ):
        """
        Initialize the workflow executor.

        Args:
            tool_executor: Async function to execute a tool (tool_name, params) -> result
            on_step_complete: Optional callback when a step completes
            on_switch_skill: Optional callback when workflow switches to another skill
        """
        self.tool_executor = tool_executor
        self.on_step_complete = on_step_complete
        self.on_switch_skill = on_switch_skill

    async def execute(
        self,
        workflow: SkillWorkflow,
        input_vars: dict[str, Any],
    ) -> WorkflowContext:
        """
        Execute a complete workflow.

        Args:
            workflow: The workflow definition to execute
            input_vars: Input variables (e.g., file_path, existing data)

        Returns:
            WorkflowContext with execution results
        """
        context = WorkflowContext(input=input_vars)
        resolver = WorkflowVariableResolver(context)

        for i, step in enumerate(workflow.steps):
            context.current_step = i

            if isinstance(step, WorkflowSwitch):
                # Handle conditional switch
                action = self._evaluate_switch(step, context, resolver)
                if action:
                    if "skill" in action:
                        context.switch_to_skill = action["skill"]
                        if self.on_switch_skill:
                            self.on_switch_skill(action["skill"], context)
                        return context
                    if action.get("abort"):
                        context.aborted = True
                        context.error = action.get("reason", "Workflow aborted by switch")
                        return context
                continue

            if isinstance(step, WorkflowStep):
                # Check condition if present
                if step.condition:
                    condition_result = self._evaluate_condition(step.condition, context)
                    if not condition_result:
                        continue  # Skip this step

                # Resolve parameters
                resolved_params = resolver.resolve(step.params)

                # Execute tool
                try:
                    result = await self.tool_executor(step.tool, resolved_params)

                    # Store output if specified
                    if step.output:
                        context.set_output(step.output, result)

                    # Callback
                    if self.on_step_complete:
                        self.on_step_complete(step.tool, result)

                except Exception as e:
                    if step.abort_on_error:
                        context.aborted = True
                        context.error = f"Step '{step.tool}' failed: {e}"
                        return context
                    if not step.optional:
                        # Store error but continue
                        if step.output:
                            context.set_output(step.output, {"error": str(e)})

        return context

    def _evaluate_switch(
        self,
        switch: WorkflowSwitch,
        context: WorkflowContext,
        resolver: WorkflowVariableResolver,
    ) -> dict[str, Any] | None:
        """Evaluate a switch statement."""
        value = context.get_variable(switch.on)

        if value is not None and str(value) in switch.cases:
            return switch.cases[str(value)]

        return switch.default

    def _evaluate_condition(self, condition: str, context: WorkflowContext) -> bool:
        """
        Evaluate a simple condition.

        Supports:
        - "variable == value"
        - "variable != value"
        - "variable" (truthy check)

        Args:
            condition: Condition string
            context: Workflow context

        Returns:
            True if condition is met
        """
        condition = condition.strip()

        # Check for equality
        if "==" in condition:
            parts = condition.split("==", 1)
            var_path = parts[0].strip()
            expected = parts[1].strip().strip("'\"")
            actual = context.get_variable(var_path)
            return str(actual) == expected

        # Check for inequality
        if "!=" in condition:
            parts = condition.split("!=", 1)
            var_path = parts[0].strip()
            expected = parts[1].strip().strip("'\"")
            actual = context.get_variable(var_path)
            return str(actual) != expected

        # Truthy check
        value = context.get_variable(condition)
        return bool(value)
