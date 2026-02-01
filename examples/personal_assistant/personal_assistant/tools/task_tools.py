"""Task management tools for the personal assistant plugin."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from personal_assistant.storage import load_store, new_id, save_store
from personal_assistant.tools.tool_base import ApprovalRiskLevel


class TaskListTool:
    """List tasks from the local store."""

    @property
    def name(self) -> str:
        return "task_list"

    @property
    def description(self) -> str:
        return "List tasks with optional status filter."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "open or done"},
                "limit": {"type": "integer", "description": "Max number of results"},
                "store_path": {"type": "string", "description": "Override store file"},
            },
        }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        limit = kwargs.get("limit")
        if limit is not None and (not isinstance(limit, int) or limit < 1):
            return False, "limit must be a positive integer"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        store = load_store(_path_from_kwargs(kwargs))
        tasks = store.get("tasks", [])
        status = kwargs.get("status")
        if status:
            tasks = [task for task in tasks if task.get("status") == status]
        limit = kwargs.get("limit")
        if limit:
            tasks = tasks[:limit]
        return {"success": True, "tasks": tasks, "count": len(tasks)}


class TaskCreateTool:
    """Create a task in the local store."""

    @property
    def name(self) -> str:
        return "task_create"

    @property
    def description(self) -> str:
        return "Create a new task with optional due date."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "notes": {"type": "string"},
                "due": {"type": "string", "description": "ISO due date"},
                "store_path": {"type": "string", "description": "Override store file"},
            },
            "required": ["title"],
        }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        title = kwargs.get("title")
        if not isinstance(title, str) or not title.strip():
            return False, "title must be a non-empty string"
        return True, None

    async def execute(
        self,
        title: str,
        notes: str | None = None,
        due: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        store_path = _path_from_kwargs(kwargs)
        store = load_store(store_path)
        task = {
            "id": new_id("task"),
            "title": title,
            "notes": notes,
            "due": due,
            "status": "open",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        store.setdefault("tasks", []).append(task)
        save_store(store, store_path)
        return {"success": True, "task": task}


class TaskCompleteTool:
    """Mark a task as complete."""

    @property
    def name(self) -> str:
        return "task_complete"

    @property
    def description(self) -> str:
        return "Complete a task by ID (approval required)."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "store_path": {"type": "string", "description": "Override store file"},
            },
            "required": ["task_id"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        task_id = kwargs.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            return False, "task_id must be a non-empty string"
        return True, None

    async def execute(self, task_id: str, **kwargs: Any) -> dict[str, Any]:
        store_path = _path_from_kwargs(kwargs)
        store = load_store(store_path)
        task = _find_by_id(store.get("tasks", []), task_id)
        if not task:
            return {"success": False, "error": f"Task not found: {task_id}"}
        task["status"] = "done"
        task["completed_at"] = datetime.utcnow().isoformat() + "Z"
        save_store(store, store_path)
        return {"success": True, "task": task}


def _find_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    """Find an item by id."""
    for item in items:
        if item.get("id") == item_id:
            return item
    return None


def _path_from_kwargs(kwargs: dict[str, Any]) -> Path | None:
    """Resolve store path from kwargs."""
    store_path = kwargs.get("store_path")
    if store_path:
        return Path(store_path)
    return None
