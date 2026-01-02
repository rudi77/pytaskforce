"""
Core Domain - TodoList Planning

This module contains the domain logic for TodoList planning and task management.
It defines the core data structures (TodoItem, TodoList, TaskStatus) and the
PlanGenerator class that creates executable plans from mission descriptions.

Key Responsibilities:
- Define TodoItem and TodoList domain models
- Generate plans using LLM-based reasoning
- Validate task dependencies (no circular dependencies)
- Provide plan manipulation methods (insert, modify, get by position)

This is pure domain logic with NO persistence concerns. All file I/O and
serialization is delegated to the infrastructure layer.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.todolist import TaskStatus


def parse_task_status(value: Any) -> TaskStatus:
    """
    Parse arbitrary status strings to TaskStatus with safe fallbacks.

    Accepts common aliases like "open" -> PENDING, "inprogress" -> IN_PROGRESS, etc.

    Args:
        value: Status value (string, enum, or other)

    Returns:
        TaskStatus enum value (defaults to PENDING if invalid)
    """
    text = str(value or "").strip().replace("-", "_").replace(" ", "_").upper()
    if not text:
        return TaskStatus.PENDING

    alias = {
        "OPEN": "PENDING",
        "TODO": "PENDING",
        "INPROGRESS": "IN_PROGRESS",
        "DONE": "COMPLETED",
        "COMPLETE": "COMPLETED",
        "FAIL": "FAILED",
        "ERROR": "FAILED",
        "SKIP": "SKIPPED",
        "SKIPPED": "SKIPPED",
    }
    normalized = alias.get(text, text)
    try:
        return TaskStatus[normalized]
    except KeyError:
        return TaskStatus.PENDING


@dataclass
class TodoItem:
    """
    Single task in a TodoList.

    Represents an atomic unit of work with clear acceptance criteria,
    dependencies, and execution tracking.

    Attributes:
        position: Numeric position in the plan (1-based)
        description: What needs to be accomplished (outcome-oriented)
        acceptance_criteria: Observable condition to verify completion
        dependencies: List of positions that must complete first
        status: Current execution status
        chosen_tool: Tool selected for execution (runtime)
        tool_input: Parameters passed to tool (runtime)
        execution_result: Result from tool execution (runtime)
        attempts: Number of execution attempts
        max_attempts: Maximum allowed attempts before failure
        replan_count: Number of times this task was replanned
        execution_history: History of all execution attempts
    """

    position: int
    description: str
    acceptance_criteria: str
    dependencies: list[int] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING

    # Runtime fields (filled during execution)
    chosen_tool: str | None = None
    tool_input: dict[str, Any] | None = None
    execution_result: dict[str, Any] | None = None
    attempts: int = 0
    max_attempts: int = 3
    replan_count: int = 0
    execution_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the TodoItem to a serializable dict.

        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "position": self.position,
            "description": self.description,
            "acceptance_criteria": self.acceptance_criteria,
            "dependencies": self.dependencies,
            "status": (
                self.status.value if isinstance(self.status, TaskStatus) else str(self.status)
            ),
            "chosen_tool": self.chosen_tool,
            "tool_input": self.tool_input,
            "execution_result": self.execution_result,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "replan_count": self.replan_count,
        }


@dataclass
class TodoList:
    """
    Complete plan for a mission.

    Represents a structured, dependency-aware plan with multiple tasks.
    Provides methods for task lookup, insertion, and validation.

    Attributes:
        mission: Original mission description
        items: List of TodoItem tasks
        todolist_id: Unique identifier for this plan
        created_at: Timestamp when plan was created
        updated_at: Timestamp when plan was last modified
        open_questions: List of unresolved questions (should be empty after clarification)
        notes: Additional planning notes or context
    """

    mission: str
    items: list[TodoItem]
    todolist_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    open_questions: list[str] = field(default_factory=list)
    notes: str = ""

    @staticmethod
    def from_json(json_text: Any) -> TodoList:
        """
        Create a TodoList from an LLM JSON string/object.

        Accepts either a JSON string or a pre-parsed dict and returns
        a populated TodoList instance with sane fallbacks.

        Args:
            json_text: JSON string or dict containing plan data

        Returns:
            TodoList instance with parsed data
        """
        try:
            data = json.loads(json_text) if isinstance(json_text, str) else (json_text or {})
        except Exception:
            data = {}

        raw_items = data.get("items", []) or []
        items: list[TodoItem] = []
        for index, raw in enumerate(raw_items, start=1):
            try:
                position = int(raw.get("position", index))
            except Exception:
                position = index

            item = TodoItem(
                position=position,
                description=str(raw.get("description", "")).strip(),
                acceptance_criteria=str(raw.get("acceptance_criteria", "")).strip(),
                dependencies=raw.get("dependencies") or [],
                status=parse_task_status(raw.get("status")),
                chosen_tool=raw.get("chosen_tool"),
                tool_input=raw.get("tool_input"),
                execution_result=raw.get("execution_result"),
                attempts=int(raw.get("attempts", 0)),
                max_attempts=int(raw.get("max_attempts", 3)),
                replan_count=int(raw.get("replan_count", 0)),
            )
            items.append(item)

        open_questions = [str(q) for q in (data.get("open_questions", []) or [])]
        notes = str(data.get("notes", ""))
        todolist_id = str(data.get("todolist_id") or str(uuid.uuid4()))
        mission = str(data.get("mission", ""))

        return TodoList(
            todolist_id=todolist_id,
            mission=mission,
            items=items,
            open_questions=open_questions,
            notes=notes,
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the TodoList to a serializable dict.

        Returns:
            Dictionary representation suitable for JSON serialization
        """

        def serialize_item(item: TodoItem) -> dict[str, Any]:
            return {
                "position": item.position,
                "description": item.description,
                "acceptance_criteria": item.acceptance_criteria,
                "dependencies": item.dependencies,
                "status": (
                    item.status.value if isinstance(item.status, TaskStatus) else str(item.status)
                ),
                "chosen_tool": item.chosen_tool,
                "tool_input": item.tool_input,
                "execution_result": item.execution_result,
                "attempts": item.attempts,
                "max_attempts": item.max_attempts,
                "replan_count": item.replan_count,
            }

        return {
            "todolist_id": self.todolist_id,
            "mission": self.mission,
            "items": [serialize_item(i) for i in self.items],
            "open_questions": list(self.open_questions or []),
            "notes": self.notes or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_step_by_position(self, position: int) -> TodoItem | None:
        """
        Get TodoItem by position.

        Args:
            position: Position number to look up

        Returns:
            TodoItem at that position, or None if not found
        """
        for item in self.items:
            if item.position == position:
                return item
        return None

    def insert_step(self, step: TodoItem, at_position: int | None = None) -> None:
        """
        Insert a step at specified position, renumbering subsequent steps.

        Args:
            step: TodoItem to insert
            at_position: Position to insert at (defaults to step.position)
        """
        if at_position is None:
            at_position = step.position

        # Renumber existing steps at or after insert position
        for item in self.items:
            if item.position >= at_position:
                item.position += 1

        # Set correct position and add
        step.position = at_position
        self.items.append(step)

        # Sort by position to maintain order
        self.items.sort(key=lambda x: x.position)


class PlanGenerator:
    """
    Generates TodoLists from mission descriptions using LLM.

    Uses LLM-based reasoning to create structured, executable plans with:
    - Outcome-oriented task descriptions
    - Observable acceptance criteria
    - Dependency management
    - Clarification question extraction

    The generator uses two different model strategies:
    - "main" model for complex reasoning (clarification questions)
    - "fast" model for structured generation (todo lists)
    """

    def __init__(self, llm_provider: LLMProviderProtocol):
        """
        Initialize PlanGenerator with LLM provider.

        Args:
            llm_provider: LLM service for generation operations
        """
        self.llm_provider = llm_provider
        self.logger = structlog.get_logger()

    async def extract_clarification_questions(
        self, mission: str, tools_desc: str, model: str = "main"
    ) -> list[dict[str, Any]]:
        """
        Extract clarification questions from the mission and tools_desc using LLM.

        Uses "main" model by default for complex reasoning.

        Args:
            mission: The mission to create the todolist for
            tools_desc: The description of the tools available
            model: Model alias to use (default: "main")

        Returns:
            A list of clarification questions

        Raises:
            RuntimeError: If LLM generation fails
            ValueError: If JSON parsing fails
        """
        user_prompt, system_prompt = self._create_clarification_questions_prompts(
            mission, tools_desc
        )

        self.logger.info(
            "extracting_clarification_questions", mission_length=len(mission), model=model
        )

        result = await self.llm_provider.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            temperature=0,
        )

        if not result.get("success"):
            self.logger.error("clarification_questions_failed", error=result.get("error"))
            raise RuntimeError(f"Failed to extract questions: {result.get('error')}")

        raw = result["content"]
        try:
            data = json.loads(raw)

            self.logger.info(
                "clarification_questions_extracted",
                question_count=len(data) if isinstance(data, list) else 0,
                tokens=result.get("usage", {}).get("total_tokens", 0),
            )

            return data
        except json.JSONDecodeError as e:
            self.logger.error(
                "clarification_questions_parse_failed", error=str(e), response=raw[:200]
            )
            raise ValueError(f"Invalid JSON from model: {e}\nRaw: {raw[:500]}") from e

    async def generate_plan(
        self,
        mission: str,
        tools_desc: str,
        answers: dict[str, Any] | None = None,
        model: str = "fast",
    ) -> TodoList:
        """
        Generate TodoList from mission description.

        Uses "fast" model by default for efficient structured generation.

        Args:
            mission: The mission to create the todolist for
            tools_desc: The description of the tools available
            answers: Optional dict of question-answer pairs from clarification
            model: Model alias to use (default: "fast")

        Returns:
            A new TodoList based on the mission and tools_desc

        Raises:
            RuntimeError: If LLM generation fails
            ValueError: If JSON parsing fails
        """
        user_prompt, system_prompt = self._create_final_todolist_prompts(
            mission, tools_desc, answers or {}
        )

        self.logger.info(
            "creating_todolist",
            mission_length=len(mission),
            answer_count=len(answers) if isinstance(answers, dict) else 0,
            model=model,
        )

        result = await self.llm_provider.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            response_format={"type": "json_object"},
            temperature=0,
        )

        if not result.get("success"):
            self.logger.error("todolist_creation_failed", error=result.get("error"))
            raise RuntimeError(f"Failed to create todolist: {result.get('error')}")

        raw = result["content"]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            self.logger.error("todolist_parse_failed", error=str(e), response=raw[:200])
            raise ValueError(f"Invalid JSON from model: {e}\nRaw: {raw[:500]}") from e

        todolist = TodoList.from_json(data)
        todolist.mission = mission

        self.logger.info(
            "todolist_created",
            todolist_id=todolist.todolist_id,
            item_count=len(todolist.items),
            tokens=result.get("usage", {}).get("total_tokens", 0),
        )

        return todolist

    async def create_todolist(
        self,
        mission: str,
        tools_desc: str,
        answers: dict[str, Any] | None = None,
        model: str = "fast",
        memory_manager: Any | None = None,
    ) -> TodoList:
        """
        Create a new TodoList from mission description using LLM.

        This is an alias for generate_plan() to satisfy the
        TodoListManagerProtocol. The memory_manager parameter is
        accepted but not used in this implementation.

        Args:
            mission: User's mission description
            tools_desc: Formatted description of available tools
            answers: Dict of question keys -> user answers
            model: Model alias to use (default: "fast")
            memory_manager: Optional memory manager (not used)

        Returns:
            TodoList with generated items, empty open_questions, notes

        Raises:
            RuntimeError: If LLM generation fails
            ValueError: If JSON parsing fails
        """
        return await self.generate_plan(
            mission, tools_desc, answers, model
        )

    async def load_todolist(self, todolist_id: str) -> TodoList:
        """
        Load a TodoList from storage by ID.

        Note: PlanGenerator is pure domain logic without persistence.
        This method raises NotImplementedError. Use a proper
        TodoListManager implementation with persistence support.

        Args:
            todolist_id: Unique identifier for the TodoList

        Raises:
            NotImplementedError: PlanGenerator lacks persistence
        """
        raise NotImplementedError(
            "PlanGenerator is pure domain logic without persistence. "
            "Use TodoListManager from infrastructure layer for "
            "load/save operations."
        )

    async def update_todolist(self, todolist: TodoList) -> TodoList:
        """
        Persist TodoList changes to storage.

        Note: PlanGenerator is pure domain logic without persistence.
        This method is a no-op and returns the todolist unchanged.
        Use a proper TodoListManager implementation with persistence.

        Args:
            todolist: TodoList object with modifications

        Returns:
            The same TodoList object unchanged
        """
        self.logger.warning(
            "update_todolist_noop",
            hint="PlanGenerator doesn't persist. Use TodoListManager.",
        )
        return todolist

    async def get_todolist(self, todolist_id: str) -> TodoList:
        """
        Get a TodoList by ID (alias for load_todolist).

        Args:
            todolist_id: Unique identifier for the TodoList

        Raises:
            NotImplementedError: PlanGenerator lacks persistence
        """
        return await self.load_todolist(todolist_id)

    async def delete_todolist(self, todolist_id: str) -> bool:
        """
        Delete a TodoList from storage.

        Note: PlanGenerator is pure domain logic without persistence.
        This method raises NotImplementedError.

        Args:
            todolist_id: Unique identifier for the TodoList

        Raises:
            NotImplementedError: PlanGenerator lacks persistence
        """
        raise NotImplementedError(
            "PlanGenerator is pure domain logic without persistence. "
            "Use TodoListManager from infrastructure layer for "
            "delete operations."
        )

    async def modify_step(
        self,
        todolist_id: str,
        step_position: int,
        modifications: dict[str, Any],
    ) -> tuple[bool, str | None]:
        """
        Modify existing TodoItem parameters (replanning).

        Note: PlanGenerator is pure domain logic without persistence.
        This method raises NotImplementedError.

        Args:
            todolist_id: ID of the TodoList to modify
            step_position: Position of the step to modify
            modifications: Dict of field names -> new values

        Raises:
            NotImplementedError: PlanGenerator lacks persistence
        """
        raise NotImplementedError(
            "PlanGenerator is pure domain logic without persistence. "
            "Use TodoListManager from infrastructure layer for "
            "modify operations."
        )

    async def decompose_step(
        self,
        todolist_id: str,
        step_position: int,
        subtasks: list[dict[str, Any]],
    ) -> tuple[bool, list[int]]:
        """
        Split a TodoItem into multiple subtasks (replanning).

        Note: PlanGenerator is pure domain logic without persistence.
        This method raises NotImplementedError.

        Args:
            todolist_id: ID of the TodoList to modify
            step_position: Position of the step to decompose
            subtasks: List of dicts with "description" and
                     "acceptance_criteria"

        Raises:
            NotImplementedError: PlanGenerator lacks persistence
        """
        raise NotImplementedError(
            "PlanGenerator is pure domain logic without persistence. "
            "Use TodoListManager from infrastructure layer for "
            "decompose operations."
        )

    async def replace_step(
        self,
        todolist_id: str,
        step_position: int,
        new_step_data: dict[str, Any],
    ) -> tuple[bool, int | None]:
        """
        Replace a TodoItem with an alternative approach (replanning).

        Note: PlanGenerator is pure domain logic without persistence.
        This method raises NotImplementedError.

        Args:
            todolist_id: ID of the TodoList to modify
            step_position: Position of the step to replace
            new_step_data: Dict with "description" and
                          "acceptance_criteria"

        Raises:
            NotImplementedError: PlanGenerator lacks persistence
        """
        raise NotImplementedError(
            "PlanGenerator is pure domain logic without persistence. "
            "Use TodoListManager from infrastructure layer for "
            "replace operations."
        )

    def validate_dependencies(self, plan: TodoList) -> bool:
        """
        Validate that all dependencies are valid (no cycles, all positions exist).

        Skipped items are excluded from validation since they are not actively executed.

        Args:
            plan: The todolist to validate

        Returns:
            True if dependencies are valid, False otherwise
        """
        # Only validate active items (not SKIPPED)
        active_items = [item for item in plan.items if item.status != TaskStatus.SKIPPED]
        positions = {item.position for item in plan.items}

        # Check all dependencies reference valid positions
        for item in active_items:
            for dep in item.dependencies:
                if dep not in positions:
                    self.logger.warning(
                        "invalid_dependency", position=item.position, invalid_dep=dep
                    )
                    return False

        # Check for circular dependencies using DFS (only among active items)
        def has_cycle(position: int, visited: set, rec_stack: set) -> bool:
            visited.add(position)
            rec_stack.add(position)

            item = plan.get_step_by_position(position)
            if item and item.status != TaskStatus.SKIPPED:
                for dep in item.dependencies:
                    # Find the item at dep position
                    dep_item = plan.get_step_by_position(dep)
                    # Skip if dependency is SKIPPED
                    if dep_item and dep_item.status == TaskStatus.SKIPPED:
                        continue

                    if dep not in visited:
                        if has_cycle(dep, visited, rec_stack):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(position)
            return False

        visited: set = set()
        for item in active_items:
            if item.position not in visited:
                if has_cycle(item.position, visited, set()):
                    self.logger.warning("circular_dependency_detected", position=item.position)
                    return False

        return True

    def _create_clarification_questions_prompts(
        self, mission: str, tools_desc: str
    ) -> tuple[str, str]:
        """
        Create prompts for clarification questions (Pre-Clarification).

        Args:
            mission: Mission description
            tools_desc: Available tools description

        Returns:
            Tuple of (user_prompt, system_prompt)
        """
        system_prompt = f"""
You are a Clarification-Mining Agent.

## Objective
Find **all** missing required inputs needed to produce an **executable** plan for the mission using the available tools.

## Context
- Mission (user intent and constraints):
{mission}

- Available tools (names, descriptions, **parameter schemas including required/optional/default/enums/types**):
{tools_desc}

## Output
- Return **only** a valid JSON array (no code fences, no commentary).
- Each element must be:
  - "key": stable, machine-readable snake_case identifier. Prefer **"<tool>.<parameter>"** (e.g., "file_writer.filename"); if tool-agnostic use a clear domain key (e.g., "project_name").
  - "question": **one** short, closed, unambiguous question (one datum per question).

## Algorithm (mandatory)
1) **Parse the mission** to understand the intended outcome and likely steps.
2) **Enumerate candidate tool invocations** required to achieve the mission (internally; do not output them).
3) For **each candidate tool**, inspect its **parameter schema**:
   - For every **required** parameter (or optional-without-safe-default) check if its value is **explicitly present** in the mission (exact literal or clearly specified constraint).
   - If not explicitly present, **create a question** for that parameter.
4) **Respect schema constraints**:
   - Types (string/number/boolean/path/url/email), formats (e.g., kebab-case, ISO-8601), units, min/max.
   - If an enum is specified, ask as a **closed choice** ("Which of: A, B, or C?").
   - **Do not infer** values unless a **default** is explicitly provided in the schema.
5) **Merge & deduplicate** questions across tools.
6) **Confidence gate**:
   - If you are **not 100% certain** every required value is specified, you **must** ask a question for it.
   - If truly nothing is missing, return **[]**.

## Strict Rules
- **Only required info**: Ask only for parameters that are required (or effectively required because no safe default exists).
- **No tasks, no explanations**: Output questions only.
- **Closed & precise**:
  - Ask for a single value per question; include necessary format/units/constraints in the question.
  - Avoid ambiguity, multi-part questions, or small talk.
- **Minimal & deduplicated**: No duplicates; no "nice-to-have" questions.

## Examples (illustrative only; do not force)
[
  {{"key":"file_writer.filename","question":"What should the output file be called (include extension, e.g., report.txt)?"}},
  {{"key":"file_writer.directory","question":"In which directory should the file be created (absolute or project-relative path)?"}},
  {{"key":"git.create_repo.visibility","question":"Should the repository be public or private (choose one: public/private)?"}}
]
""".strip()

        user_prompt = (
            "Provide the missing required information as a JSON array in the form "
            '[{"key":"<tool.parameter|domain_key>", "question":"<closed, precise question>"}]. '
            "If nothing is missing, return []."
        )

        return user_prompt, system_prompt

    def _create_final_todolist_prompts(
        self, mission: str, tools_desc: str, answers: dict[str, Any]
    ) -> tuple[str, str]:
        """
        Create prompts for outcome-oriented TodoList planning.

        Args:
            mission: The mission text
            tools_desc: Description of available tools
            answers: User-provided answers to clarification questions

        Returns:
            Tuple of (user_prompt, system_prompt)
        """
        structure = """
{
  "items": [
    {
      "position": 1,
      "description": "What needs to be done (outcome-oriented)",
      "acceptance_criteria": "How to verify it's done (observable condition)",
      "dependencies": [],
      "status": "PENDING"
    }
  ],
  "open_questions": [],
  "notes": ""
}
"""

        system_prompt = f"""You are a planning agent. Create a minimal, goal-oriented plan.

Mission:
{mission}

User Answers:
{json.dumps(answers, indent=2)}

Available Tools (for reference, DO NOT specify in plan):
{tools_desc}

RULES:
1. Each item describes WHAT to achieve, NOT HOW (no tool names, no parameters)
2. acceptance_criteria: Observable condition (e.g., "File X exists with content Y")
3. dependencies: List of step positions that must complete first
4. **MINIMAL STEPS (CRITICAL):**
   - Simple queries (list, find, show, get) → **1 step only**
   - Simple tasks (read file, search) → **1-2 steps**
   - Complex tasks (create, modify, deploy) → **3-5 steps max**
   - NEVER split "find and present" into separate steps. One step: "Find and present X"
5. open_questions MUST be empty (all clarifications resolved)
6. description: Clear, actionable outcome (1-2 sentences)
7. acceptance_criteria: Specific, verifiable condition
8. DYNAMIC REPLANNING (CRITICAL): If you just received a User Answer from a previous step, do NOT mark the mission as complete. You MUST generate NEW steps to fulfill the user's intent expressed in that answer.

EXAMPLES:

Good (Simple query = 1 step):
- Mission: "List all documents"
  Plan: 1 step - "Find and present all available documents with their names and IDs"

Good (Complex task = multiple steps):
- Mission: "Create a Python script that reads CSV and generates a report"
  Plan: 3 steps - (1) Understand CSV structure, (2) Create script, (3) Verify output

Bad (Over-engineered):
- Mission: "List all documents"
  Plan: 3 steps - (1) Find documents, (2) Extract names, (3) Present to user
  → This should be 1 step!

Return JSON matching:
{structure}
"""

        user_prompt = "Generate the plan"

        return user_prompt, system_prompt
