"""
Ralph PRD Tool

Manages prd.json file for tracking user stories and their completion status.
Supports reading the next pending story and marking stories as complete.
"""

import json
from pathlib import Path
from typing import Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class RalphPRDTool(ToolProtocol):
    """
    Tool for managing PRD tracking via prd.json.

    Supports:
    - Reading prd.json to find the next pending user story
    - Marking a user story as complete (passes: true)
    - Atomic file writes to prevent corruption
    """

    def __init__(self, prd_path: str = "prd.json"):
        """
        Initialize RalphPRDTool.

        Args:
            prd_path: Path to prd.json file (default: "prd.json" in current directory)
        """
        self.prd_path = Path(prd_path)

    @property
    def name(self) -> str:
        """Return tool name."""
        return "ralph_prd"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Manage PRD tracking via prd.json. Can read the next pending user story "
            "(where passes: false) or mark a story as complete (passes: true). "
            "Stories are stored in format: {id, title, passes, success_criteria}."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get_next", "mark_complete"],
                    "description": "Action to perform: 'get_next' to find next pending story, 'mark_complete' to mark a story as done",
                },
                "story_id": {
                    "type": "integer",
                    "description": "Story ID to mark as complete (required when action is 'mark_complete')",
                },
            },
            "required": ["action"],
        }

    @property
    def requires_approval(self) -> bool:
        """
        Approval requirement depends on action.

        - get_next: No approval (read-only)
        - mark_complete: Requires approval (modifies state)
        """
        # Note: This is checked at tool level, not per action
        # We return True to be safe, but get_next should ideally not require approval
        # The actual approval check happens in get_approval_preview/execute
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Medium risk - modifies tracking state."""
        return ApprovalRiskLevel.MEDIUM

    @property
    def supports_parallelism(self) -> bool:
        """Read operations are safe, but writes should be serialized."""
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        action = kwargs.get("action", "unknown")
        story_id = kwargs.get("story_id")
        if action == "mark_complete":
            return (
                f"Tool: {self.name}\n"
                f"Operation: Mark story {story_id} as complete (passes: true)\n"
                f"File: {self.prd_path}"
            )
        return f"Tool: {self.name}\nOperation: Read next pending story\nFile: {self.prd_path}"

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        action = kwargs.get("action")
        if action not in ["get_next", "mark_complete"]:
            return False, f"Invalid action: {action}. Must be 'get_next' or 'mark_complete'"

        if action == "mark_complete":
            if "story_id" not in kwargs:
                return False, "story_id is required when action is 'mark_complete'"
            if not isinstance(kwargs["story_id"], int):
                return False, "story_id must be an integer"

        return True, None

    def _load_prd(self) -> dict[str, Any]:
        """Load prd.json, creating empty structure if file doesn't exist."""
        if not self.prd_path.exists():
            return {"stories": []}

        try:
            with open(self.prd_path, encoding="utf-8") as f:
                data = json.load(f)
                # Ensure stories list exists and is a list
                if "stories" not in data:
                    data["stories"] = []
                elif not isinstance(data["stories"], list):
                    # Fix invalid format - convert to list
                    data["stories"] = []
                return data
        except (json.JSONDecodeError, OSError) as e:
            return {"stories": [], "_error": f"Failed to load prd.json: {str(e)}"}

    def _save_prd(self, data: dict[str, Any]) -> None:
        """
        Save prd.json atomically using temporary file + rename.

        This prevents corruption if the process is interrupted during write.
        Uses Path.replace() which is atomic on both Windows and Unix.
        """
        # Validate data structure
        if not isinstance(data, dict):
            raise ValueError("PRD data must be a dictionary")
        if "stories" not in data:
            data["stories"] = []
        if not isinstance(data["stories"], list):
            raise ValueError("PRD stories must be a list")

        # Write to temporary file first
        temp_file = self.prd_path.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # Atomic rename (works on Windows and Unix since Python 3.3+)
            # On Windows, this requires the target file to not be open
            temp_file.replace(self.prd_path)
        except Exception:
            # Clean up temp file on error
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass  # Ignore cleanup errors
            raise

    async def execute(self, action: str, story_id: int | None = None, **kwargs: Any) -> dict[str, Any]:
        """
        Execute PRD tool action.

        Args:
            action: Either "get_next" or "mark_complete"
            story_id: Required when action is "mark_complete"

        Returns:
            Dictionary with success status and result data
        """
        try:
            if action == "get_next":
                return await self._get_next_story()
            elif action == "mark_complete":
                if story_id is None:
                    return {"success": False, "error": "story_id is required for mark_complete"}
                return await self._mark_story_complete(story_id)
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"success": False, "error": str(e), "error_type": type(e).__name__}

    async def _get_next_story(self) -> dict[str, Any]:
        """Find and return the next pending user story (passes: false)."""
        data = self._load_prd()

        if "_error" in data:
            return {"success": False, "error": data["_error"]}

        stories = data.get("stories", [])
        # Find first story where passes is False or missing
        for story in stories:
            if not story.get("passes", False):
                return {
                    "success": True,
                    "story": story,
                    "output": f"Found next pending story: {story.get('title', 'Untitled')} (ID: {story.get('id')})",
                }

        return {
            "success": True,
            "story": None,
            "output": "No pending stories found. All stories are complete!",
        }

    async def _mark_story_complete(self, story_id: int) -> dict[str, Any]:
        """Mark a story as complete (passes: true) by ID."""
        data = self._load_prd()

        if "_error" in data:
            return {"success": False, "error": data["_error"]}

        stories = data.get("stories", [])
        found = False

        for story in stories:
            if story.get("id") == story_id:
                story["passes"] = True
                found = True
                break

        if not found:
            return {"success": False, "error": f"Story with ID {story_id} not found"}

        # Atomic save
        self._save_prd(data)

        return {
            "success": True,
            "output": f"Story {story_id} marked as complete (passes: true)",
            "story_id": story_id,
        }
