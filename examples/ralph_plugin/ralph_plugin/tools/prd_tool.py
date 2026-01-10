"""
Ralph PRD Tool

Manages prd.json file for tracking user stories and their completion status.
Supports reading the next pending story and marking stories as complete.

V3 Enhancements:
- get_current_context: Returns minimal context (current story + progress) to reduce token usage
- verify_and_complete: Gates completion on verification (py_compile + pytest)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol

if TYPE_CHECKING:
    from ralph_plugin.tools.verification_tool import RalphVerificationTool


class RalphPRDTool(ToolProtocol):
    """
    Tool for managing PRD tracking via prd.json.

    Supports:
    - Reading prd.json to find the next pending user story
    - Marking a user story as complete (passes: true)
    - Atomic file writes to prevent corruption
    - V3: Minimal context retrieval (get_current_context)
    - V3: Verification-gated completion (verify_and_complete)
    """

    def __init__(
        self,
        prd_path: str = "prd.json",
        project_root: str | None = None,
        pytest_timeout: int = 60,
        verification_tool: RalphVerificationTool | None = None,
    ):
        """
        Initialize RalphPRDTool.

        Args:
            prd_path: Path to prd.json file (default: "prd.json" in current directory)
            project_root: Root directory for verification (default: current directory)
            pytest_timeout: Timeout in seconds for pytest execution (default: 60)
            verification_tool: Optional verification tool instance for code verification
        """
        self.prd_path = Path(prd_path)
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.pytest_timeout = pytest_timeout
        self._verification_tool = verification_tool

    def _get_verification_tool(self) -> RalphVerificationTool:
        """Get or create the verification tool instance."""
        if self._verification_tool is None:
            # Lazy import to avoid circular dependency
            from ralph_plugin.tools.verification_tool import RalphVerificationTool

            self._verification_tool = RalphVerificationTool(
                project_root=str(self.project_root),
                pytest_timeout=self.pytest_timeout,
            )
        return self._verification_tool

    @property
    def name(self) -> str:
        """Return tool name."""
        return "ralph_prd"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Manage PRD tracking via prd.json. Actions: "
            "'get_next' finds next pending story, "
            "'mark_complete' marks a story done, "
            "'get_current_context' returns minimal context (current story + progress only), "
            "'verify_and_complete' runs py_compile + pytest before marking complete."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get_next", "mark_complete", "get_current_context", "verify_and_complete"],
                    "description": (
                        "Action: 'get_next' finds next pending story, "
                        "'mark_complete' marks story done, "
                        "'get_current_context' returns minimal context, "
                        "'verify_and_complete' verifies then marks complete"
                    ),
                },
                "story_id": {
                    "type": "integer",
                    "description": "Story ID (required for mark_complete and verify_and_complete)",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Python files to verify with py_compile (for verify_and_complete)",
                },
                "test_path": {
                    "type": "string",
                    "description": "Path to test file/directory for pytest (for verify_and_complete)",
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
        files = kwargs.get("files", [])
        test_path = kwargs.get("test_path")

        if action == "mark_complete":
            return (
                f"Tool: {self.name}\n"
                f"Operation: Mark story {story_id} as complete (passes: true)\n"
                f"File: {self.prd_path}"
            )
        elif action == "verify_and_complete":
            preview = (
                f"Tool: {self.name}\n"
                f"Operation: Verify then mark story {story_id} as complete\n"
            )
            if files:
                preview += f"Files to verify: {', '.join(files[:3])}"
                if len(files) > 3:
                    preview += f" ... and {len(files) - 3} more"
                preview += "\n"
            if test_path:
                preview += f"Test path: {test_path}\n"
            return preview
        elif action == "get_current_context":
            return f"Tool: {self.name}\nOperation: Get minimal context (current story + progress)"
        return f"Tool: {self.name}\nOperation: Read next pending story\nFile: {self.prd_path}"

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        action = kwargs.get("action")
        valid_actions = ["get_next", "mark_complete", "get_current_context", "verify_and_complete"]
        if action not in valid_actions:
            return False, f"Invalid action: {action}. Must be one of: {', '.join(valid_actions)}"

        if action in ["mark_complete", "verify_and_complete"]:
            if "story_id" not in kwargs:
                return False, f"story_id is required when action is '{action}'"
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

    async def execute(
        self,
        action: str,
        story_id: int | None = None,
        files: list[str] | None = None,
        test_path: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute PRD tool action.

        Args:
            action: Action to perform (get_next, mark_complete, get_current_context, verify_and_complete)
            story_id: Required for mark_complete and verify_and_complete
            files: Python files to verify (for verify_and_complete)
            test_path: Test path for pytest (for verify_and_complete)

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
            elif action == "get_current_context":
                return await self._get_current_context()
            elif action == "verify_and_complete":
                if story_id is None:
                    return {"success": False, "error": "story_id is required for verify_and_complete"}
                return await self._verify_and_complete(story_id, files or [], test_path)
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

    async def _get_current_context(self) -> dict[str, Any]:
        """
        Return minimal context for current iteration.

        This reduces token usage by returning only:
        - Current story (first with passes: false)
        - Progress summary (completed/total)
        - Last 3 completed story titles (for context)

        Returns:
            Dictionary with minimal context data
        """
        data = self._load_prd()

        if "_error" in data:
            return {"success": False, "error": data["_error"]}

        stories = data.get("stories", [])

        # Find current story (first with passes: false)
        current_story = None
        for story in stories:
            if not story.get("passes", False):
                current_story = story
                break

        # Calculate progress
        completed_count = sum(1 for s in stories if s.get("passes", False))
        total_count = len(stories)

        # Get last 3 completed titles for context
        completed_titles = [s.get("title", "Untitled") for s in stories if s.get("passes", False)]
        recent_completed = completed_titles[-3:] if completed_titles else []

        return {
            "success": True,
            "current_story": current_story,
            "progress": f"{completed_count}/{total_count}",
            "completed_count": completed_count,
            "remaining_count": total_count - completed_count,
            "recent_completed": recent_completed,
            "output": (
                f"Progress: {completed_count}/{total_count}. "
                f"Current: {current_story.get('title', 'None') if current_story else 'All complete!'}"
            ),
        }

    async def _verify_and_complete(
        self,
        story_id: int,
        files: list[str],
        test_path: str | None,
    ) -> dict[str, Any]:
        """
        Verify code before marking story as complete.

        This implements the verification gate using RalphVerificationTool:
        1. Run py_compile on all specified files
        2. Run pytest on test_path (if provided)
        3. Only mark story complete if both pass

        Args:
            story_id: Story ID to mark complete
            files: Python files to verify with py_compile
            test_path: Path to test file/directory for pytest

        Returns:
            Dictionary with verification result and completion status
        """
        # Step 1: Verify story exists
        data = self._load_prd()
        if "_error" in data:
            return {"success": False, "error": data["_error"]}

        stories = data.get("stories", [])
        story = None
        for s in stories:
            if s.get("id") == story_id:
                story = s
                break

        if not story:
            return {"success": False, "error": f"Story {story_id} not found"}

        # Step 2: Use verification tool for full verification
        verification_tool = self._get_verification_tool()
        verify_result = await verification_tool.execute(
            action="full_verify",
            files=files or [],
            test_path=test_path,
        )

        if not verify_result["success"]:
            return {
                "success": False,
                "stage": verify_result.get("stage", "unknown"),
                "error": verify_result.get("error", "Verification failed"),
                "details": verify_result.get("errors", verify_result.get("output", "")),
                "output": verify_result.get("output", "Fix issues before marking story complete."),
                "story_id": story_id,
            }

        # Step 3: All verification passed - mark complete
        story["passes"] = True
        self._save_prd(data)

        return {
            "success": True,
            "output": f"Verification passed. Story {story_id} marked as complete.",
            "story_id": story_id,
            "syntax_files_checked": verify_result.get("syntax_files_checked", 0),
            "tests_run": test_path is not None,
        }
