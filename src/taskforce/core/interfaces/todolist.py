"""
TodoList Management Protocol

This module defines the protocol interface for TodoList planning and management.
TodoList managers are responsible for:
- Generating structured plans from mission descriptions using LLMs
- Managing TodoItem lifecycle (create, update, status changes)
- Validating dependencies and preventing circular references
- Persisting TodoLists to storage

Protocol implementations coordinate with LLM providers to generate plans
and with storage to persist TodoList state.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class TaskStatus(str, Enum):
    """Status of a TodoItem during execution."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class TodoItem:
    """
    A single task in a TodoList.

    Attributes:
        position: Step number in the plan (1-indexed)
        description: What needs to be done (outcome-oriented, not tool-specific)
        acceptance_criteria: Observable condition to verify completion
        dependencies: List of position numbers that must complete first
        status: Current execution status (TaskStatus enum)
        chosen_tool: Tool selected during execution (optional)
        tool_input: Parameters passed to tool (optional)
        execution_result: Result dict from tool execution (optional)
        attempts: Number of execution attempts (for retry logic)
        max_attempts: Maximum retry attempts before marking as failed
        replan_count: Number of times this step has been replanned
        execution_history: List of all execution attempts with results
    """

    position: int
    description: str
    acceptance_criteria: str
    dependencies: list[int]
    status: TaskStatus
    chosen_tool: str | None = None
    tool_input: dict[str, Any] | None = None
    execution_result: dict[str, Any] | None = None
    attempts: int = 0
    max_attempts: int = 3
    replan_count: int = 0
    execution_history: list[dict[str, Any]] | None = None


@dataclass
class TodoList:
    """
    A structured plan with dependencies and metadata.

    Attributes:
        todolist_id: Unique identifier for this plan
        items: List of TodoItem objects
        open_questions: Unresolved clarification questions
        notes: Additional context or planning notes
    """

    todolist_id: str
    items: list[TodoItem]
    open_questions: list[str]
    notes: str


class TodoListManagerProtocol(Protocol):
    """
    Protocol defining the contract for TodoList planning and management.

    TodoList managers coordinate LLM-based plan generation with persistent
    storage. They handle:
    - Pre-planning clarification (extracting missing requirements)
    - Plan generation from mission descriptions
    - Plan validation (dependency checking, cycle detection)
    - Plan modifications (replanning, decomposition, replacement)
    - Plan persistence and retrieval

    Workflow:
        1. Agent calls extract_clarification_questions() to identify missing info
        2. User provides answers to questions
        3. Agent calls create_todolist() with mission + answers
        4. Manager generates plan using LLM
        5. Manager validates dependencies
        6. Manager persists plan to storage
        7. Agent executes steps, updating status via update_todolist()
        8. Agent may call modify_step/decompose_step/replace_step for replanning

    LLM Integration:
        Managers use LLM providers for:
        - Clarification question extraction (complex reasoning -> "main" model)
        - TodoList generation (structured output -> "fast" model)

    Storage:
        Plans are persisted as JSON files in base_dir:
        - {base_dir}/todolist_{todolist_id}.json
    """

    async def extract_clarification_questions(
        self, mission: str, tools_desc: str, model: str = "main"
    ) -> list[dict[str, Any]]:
        """
        Extract clarification questions from mission using LLM.

        Analyzes the mission description and available tools to identify
        missing required information. Returns questions that must be answered
        before generating an executable plan.

        The LLM is prompted to:
        1. Parse the mission to understand intended outcome
        2. Enumerate candidate tool invocations needed
        3. Check each tool's parameter schema for required parameters
        4. Generate questions for missing required values
        5. Return minimal, deduplicated question list

        Args:
            mission: User's mission description (intent and constraints)
            tools_desc: Formatted description of available tools with parameter schemas
            model: Model alias to use (default: "main" for complex reasoning)

        Returns:
            List of question dicts:
            [
                {
                    "key": "tool.parameter" or "domain_key",
                    "question": "Closed, precise question"
                }
            ]
            Empty list if no clarifications needed.

        Raises:
            RuntimeError: If LLM generation fails or service not configured
            ValueError: If LLM returns invalid JSON

        Example:
            >>> questions = await manager.extract_clarification_questions(
            ...     mission="Create a Python project",
            ...     tools_desc="git_tool: create_repo(name, visibility)..."
            ... )
            >>> for q in questions:
            ...     print(f"{q['key']}: {q['question']}")
            git_tool.name: What should the repository be named?
            git_tool.visibility: Should the repository be public or private?
        """
        ...

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

        Generates a structured, outcome-oriented plan with:
        - Minimal steps (prefer 3-7 over 20)
        - Clear descriptions (WHAT to achieve, not HOW)
        - Observable acceptance criteria
        - Valid dependency chains (no cycles)
        - Empty open_questions (all clarifications resolved)

        The LLM is prompted to:
        1. Understand mission intent and constraints
        2. Consider user-provided answers
        3. Optionally retrieve relevant past lessons (if memory_manager provided)
        4. Generate minimal step sequence
        5. Define acceptance criteria for each step
        6. Establish dependency relationships

        Args:
            mission: User's mission description
            tools_desc: Formatted description of available tools (for reference)
            answers: Dict of question keys -> user answers (from clarification)
            model: Model alias to use (default: "fast" for structured generation)
            memory_manager: Optional memory manager for retrieving past lessons

        Returns:
            TodoList with generated items, empty open_questions, and notes

        Raises:
            RuntimeError: If LLM generation fails or service not configured
            ValueError: If LLM returns invalid JSON or plan fails validation

        Example:
            >>> todolist = await manager.create_todolist(
            ...     mission="Analyze CSV and create report",
            ...     tools_desc=tools_description,
            ...     answers={"filename": "data.csv", "output": "report.md"}
            ... )
            >>> print(f"Generated {len(todolist.items)} steps")
            >>> for item in todolist.items:
            ...     print(f"{item.position}. {item.description}")
        """
        ...

    async def load_todolist(self, todolist_id: str) -> TodoList:
        """
        Load a TodoList from storage by ID.

        Args:
            todolist_id: Unique identifier for the TodoList

        Returns:
            TodoList object with all items and metadata

        Raises:
            FileNotFoundError: If TodoList file not found in storage

        Example:
            >>> todolist = await manager.load_todolist("abc-123")
            >>> print(f"Loaded plan with {len(todolist.items)} steps")
        """
        ...

    async def update_todolist(self, todolist: TodoList) -> TodoList:
        """
        Persist TodoList changes to storage.

        Called after modifying TodoList state (status changes, execution results).
        Overwrites existing file with updated TodoList.

        Args:
            todolist: TodoList object with modifications

        Returns:
            The same TodoList object (for chaining)

        Example:
            >>> item = todolist.items[0]
            >>> item.status = TaskStatus.COMPLETED
            >>> item.execution_result = {"success": True, "output": "Done"}
            >>> await manager.update_todolist(todolist)
        """
        ...

    async def get_todolist(self, todolist_id: str) -> TodoList:
        """
        Get a TodoList by ID (alias for load_todolist).

        Args:
            todolist_id: Unique identifier for the TodoList

        Returns:
            TodoList object

        Raises:
            FileNotFoundError: If TodoList not found
        """
        ...

    async def delete_todolist(self, todolist_id: str) -> bool:
        """
        Delete a TodoList from storage.

        Args:
            todolist_id: Unique identifier for the TodoList

        Returns:
            True if deleted successfully

        Raises:
            FileNotFoundError: If TodoList not found

        Example:
            >>> await manager.delete_todolist("abc-123")
        """
        ...

    async def modify_step(
        self, todolist_id: str, step_position: int, modifications: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """
        Modify existing TodoItem parameters (replanning).

        Allows changing step description, acceptance criteria, or dependencies.
        Increments replan_count and resets status to PENDING.

        Constraints:
        - Maximum 2 replan attempts per step (replan_count < 2)
        - Modifications must not create circular dependencies
        - Modifications must not create invalid dependency references

        Args:
            todolist_id: ID of the TodoList to modify
            step_position: Position of the step to modify (1-indexed)
            modifications: Dict of field names -> new values
                          (e.g., {"description": "New description"})

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
            - (True, None) if modification succeeded
            - (False, "error message") if failed

        Example:
            >>> success, error = await manager.modify_step(
            ...     todolist_id="abc-123",
            ...     step_position=2,
            ...     modifications={"description": "Updated description"}
            ... )
            >>> if not success:
            ...     print(f"Modification failed: {error}")
        """
        ...

    async def decompose_step(
        self, todolist_id: str, step_position: int, subtasks: list[dict[str, Any]]
    ) -> tuple[bool, list[int]]:
        """
        Split a TodoItem into multiple subtasks (replanning).

        Replaces a complex step with multiple simpler steps:
        1. Marks original step as SKIPPED
        2. Inserts subtasks after original position
        3. Renumbers subsequent steps
        4. Updates dependencies (dependents now depend on last subtask)

        Constraints:
        - Maximum 2 replan attempts per step (original.replan_count < 2)
        - Subtasks inherit original's replan_count + 1
        - First subtask depends on original's dependencies
        - Subsequent subtasks depend on previous subtask

        Args:
            todolist_id: ID of the TodoList to modify
            step_position: Position of the step to decompose
            subtasks: List of dicts with "description" and "acceptance_criteria"

        Returns:
            Tuple of (success: bool, new_positions: List[int])
            - (True, [pos1, pos2, ...]) if decomposition succeeded
            - (False, []) if failed

        Example:
            >>> success, new_positions = await manager.decompose_step(
            ...     todolist_id="abc-123",
            ...     step_position=3,
            ...     subtasks=[
            ...         {"description": "Subtask 1", "acceptance_criteria": "..."},
            ...         {"description": "Subtask 2", "acceptance_criteria": "..."}
            ...     ]
            ... )
            >>> if success:
            ...     print(f"Created subtasks at positions: {new_positions}")
        """
        ...

    async def replace_step(
        self, todolist_id: str, step_position: int, new_step_data: dict[str, Any]
    ) -> tuple[bool, int | None]:
        """
        Replace a TodoItem with an alternative approach (replanning).

        Replaces a failed step with a different approach:
        1. Marks original step as SKIPPED
        2. Creates new step at same position
        3. Preserves original's dependencies
        4. Increments replan_count

        Constraints:
        - Maximum 2 replan attempts per step (original.replan_count < 2)
        - New step inherits original's replan_count + 1
        - Position and dependencies preserved

        Args:
            todolist_id: ID of the TodoList to modify
            step_position: Position of the step to replace
            new_step_data: Dict with "description" and "acceptance_criteria"

        Returns:
            Tuple of (success: bool, new_position: Optional[int])
            - (True, position) if replacement succeeded
            - (False, None) if failed

        Example:
            >>> success, new_pos = await manager.replace_step(
            ...     todolist_id="abc-123",
            ...     step_position=2,
            ...     new_step_data={
            ...         "description": "Alternative approach",
            ...         "acceptance_criteria": "..."
            ...     }
            ... )
            >>> if success:
            ...     print(f"Replaced step at position {new_pos}")
        """
        ...
