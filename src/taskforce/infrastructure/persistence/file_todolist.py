"""
File-Based TodoList Manager

This module provides a file-based implementation of the TodoListManagerProtocol,
combining the PlanGenerator (domain logic) with file persistence for TodoLists.

The implementation is compatible with Agent V2 todolist files and provides:
- TodoList creation using PlanGenerator (LLM-based)
- File persistence (JSON format)
- Load/save/update/delete operations
- Atomic writes for safety
"""

import json
from pathlib import Path
from typing import Any

import aiofiles
import structlog

from taskforce.core.domain.plan import PlanGenerator, TodoList
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.todolist import TodoListManagerProtocol


class FileTodoListManager(TodoListManagerProtocol):
    """
    File-based TodoList persistence implementing TodoListManagerProtocol.

    TodoList files are stored as JSON in the directory structure:
    {work_dir}/todolists/todolist_{todolist_id}.json

    This class combines:
    - PlanGenerator for LLM-based plan creation (domain logic)
    - File I/O for persistence (infrastructure concern)

    Example:
        >>> manager = FileTodoListManager(
        ...     work_dir=".taskforce",
        ...     llm_provider=llm_service
        ... )
        >>> todolist = await manager.create_todolist(
        ...     mission="Analyze data.csv",
        ...     tools_desc="..."
        ... )
        >>> loaded = await manager.load_todolist(todolist.todolist_id)
        >>> assert loaded.mission == "Analyze data.csv"
    """

    def __init__(self, work_dir: str, llm_provider: LLMProviderProtocol):
        """
        Initialize FileTodoListManager.

        Args:
            work_dir: Base directory for todolist storage
            llm_provider: LLM provider for plan generation
        """
        self.work_dir = Path(work_dir)
        self.todolists_dir = self.work_dir / "todolists"
        self.todolists_dir.mkdir(parents=True, exist_ok=True)

        # Use PlanGenerator for domain logic (plan creation)
        self.plan_generator = PlanGenerator(llm_provider=llm_provider)

        self.logger = structlog.get_logger().bind(component="file_todolist_manager")

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

        Delegates plan generation to PlanGenerator, then persists to file.

        Args:
            mission: User's mission description
            tools_desc: Formatted description of available tools
            answers: Dict of question keys -> user answers
            model: Model alias to use (default: "fast")
            memory_manager: Optional memory manager (not used)

        Returns:
            TodoList with generated items, persisted to disk

        Raises:
            RuntimeError: If LLM generation fails
            ValueError: If JSON parsing fails
        """
        # Generate plan using domain logic
        todolist = await self.plan_generator.generate_plan(
            mission=mission, tools_desc=tools_desc, answers=answers, model=model
        )

        # Persist to file
        await self._write_todolist(todolist)

        self.logger.info(
            "todolist_created_and_saved",
            todolist_id=todolist.todolist_id,
            item_count=len(todolist.items),
        )

        return todolist

    async def load_todolist(self, todolist_id: str) -> TodoList:
        """
        Load a TodoList from storage by ID.

        Args:
            todolist_id: Unique identifier for the TodoList

        Returns:
            TodoList loaded from file

        Raises:
            FileNotFoundError: If the todolist file is not found
        """
        todolist_path = self._get_todolist_path(todolist_id)

        if not todolist_path.exists():
            raise FileNotFoundError(f"Todolist file not found: {todolist_path}")

        async with aiofiles.open(todolist_path, "r", encoding="utf-8") as f:
            content = await f.read()
            todolist = TodoList.from_json(content)

        self.logger.info("todolist_loaded", todolist_id=todolist_id)
        return todolist

    async def update_todolist(self, todolist: TodoList) -> TodoList:
        """
        Persist TodoList changes to storage.

        Args:
            todolist: TodoList object with modifications

        Returns:
            The same TodoList object after persisting
        """
        await self._write_todolist(todolist)

        self.logger.info("todolist_updated", todolist_id=todolist.todolist_id)
        return todolist

    async def get_todolist(self, todolist_id: str) -> TodoList:
        """
        Get a TodoList by ID (alias for load_todolist).

        Args:
            todolist_id: Unique identifier for the TodoList

        Returns:
            TodoList loaded from file

        Raises:
            FileNotFoundError: If the todolist file is not found
        """
        return await self.load_todolist(todolist_id)

    async def delete_todolist(self, todolist_id: str) -> bool:
        """
        Delete a TodoList from storage.

        Args:
            todolist_id: Unique identifier for the TodoList

        Returns:
            True if deletion was successful

        Raises:
            FileNotFoundError: If the todolist file is not found
        """
        todolist_path = self._get_todolist_path(todolist_id)

        if not todolist_path.exists():
            raise FileNotFoundError(f"Todolist file not found: {todolist_path}")

        todolist_path.unlink()

        self.logger.info("todolist_deleted", todolist_id=todolist_id)
        return True

    async def _write_todolist(self, todolist: TodoList) -> None:
        """
        Write TodoList to file (internal helper).

        Uses atomic write pattern (write to temp file, then rename).

        Args:
            todolist: TodoList to persist
        """
        todolist_path = self._get_todolist_path(todolist.todolist_id)
        temp_path = todolist_path.with_suffix(".tmp")

        # Ensure directory exists
        todolist_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file
        async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
            content = json.dumps(todolist.to_dict(), indent=2, ensure_ascii=False)
            await f.write(content)

        # Atomic rename
        temp_path.replace(todolist_path)

    def _get_todolist_path(self, todolist_id: str) -> Path:
        """
        Get the file path for a todolist.

        Args:
            todolist_id: Unique identifier for the TodoList

        Returns:
            Path to the todolist JSON file
        """
        return self.todolists_dir / f"todolist_{todolist_id}.json"

