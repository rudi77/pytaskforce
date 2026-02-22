"""
Edit Tool - Exact String Replacement

Provides surgical file editing via exact string replacement, similar to Claude Code's Edit tool.
This approach ensures precise, predictable edits without regex complexity or accidental changes.
"""

from pathlib import Path
from typing import Any

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class EditTool(ToolProtocol):
    """
    Perform exact string replacements in files.

    Similar to Claude Code's Edit tool, this enables surgical file modifications by:
    - Finding exact string matches (not regex)
    - Replacing with new content
    - Optionally replacing all occurrences
    - Creating backups before modification

    The edit will FAIL if old_string is not unique in the file (unless replace_all=True).
    This prevents accidental unintended changes.
    """

    @property
    def name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return (
            "Perform exact string replacements in files. "
            "Finds and replaces exact text matches. "
            "The edit will FAIL if old_string is not unique (unless replace_all=True). "
            "Use replace_all=True for renaming variables or strings across the file."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to modify",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The text to replace it with (must be different from old_string)",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: false). If false and multiple matches exist, the edit fails.",
                },
                "backup": {
                    "type": "boolean",
                    "description": "Create a backup file before editing (default: true)",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.MEDIUM

    @property
    def supports_parallelism(self) -> bool:
        return False  # File edits should not run in parallel

    def get_approval_preview(self, **kwargs: Any) -> str:
        file_path = kwargs.get("file_path", "")
        old_string = kwargs.get("old_string", "")
        new_string = kwargs.get("new_string", "")
        replace_all = kwargs.get("replace_all", False)

        # Truncate long strings for preview
        old_preview = old_string[:200] + "..." if len(old_string) > 200 else old_string
        new_preview = new_string[:200] + "..." if len(new_string) > 200 else new_string

        return (
            f"⚠️ FILE EDIT OPERATION\n"
            f"Tool: {self.name}\n"
            f"File: {file_path}\n"
            f"Replace All: {replace_all}\n"
            f"---OLD TEXT---\n{old_preview}\n"
            f"---NEW TEXT---\n{new_preview}"
        )

    async def execute(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        backup: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Perform exact string replacement in a file.

        Args:
            file_path: Absolute path to the file to modify
            old_string: The exact text to find and replace
            new_string: The text to replace it with
            replace_all: Replace all occurrences (default: False)
            backup: Create backup before editing (default: True)

        Returns:
            Dictionary with:
            - success: True if edit was successful
            - file_path: Path to the modified file
            - occurrences_found: Number of old_string occurrences found
            - occurrences_replaced: Number of replacements made
            - backed_up: Whether a backup was created
            - error: Error message if failed
        """
        try:
            path = Path(file_path)

            # Validate file exists
            if not path.exists():
                return {"success": False, "error": f"File not found: {file_path}"}

            if not path.is_file():
                return {"success": False, "error": f"Path is not a file: {file_path}"}

            # Validate strings
            if old_string == new_string:
                return {"success": False, "error": "old_string and new_string must be different"}

            if not old_string:
                return {"success": False, "error": "old_string cannot be empty"}

            # Read file content
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return {"success": False, "error": f"Cannot read file as text: {file_path}"}

            # Count occurrences
            occurrences = content.count(old_string)

            if occurrences == 0:
                return {
                    "success": False,
                    "error": "old_string not found in file. Make sure you're using the exact text including whitespace and indentation.",
                    "file_path": file_path,
                    "occurrences_found": 0,
                }

            # Check for uniqueness if not replace_all
            if not replace_all and occurrences > 1:
                return {
                    "success": False,
                    "error": (
                        f"old_string found {occurrences} times in file. "
                        "Either provide more context to make it unique, or use replace_all=True to replace all occurrences."
                    ),
                    "file_path": file_path,
                    "occurrences_found": occurrences,
                }

            # Create backup if requested
            backed_up = False
            if backup:
                backup_path = path.with_suffix(path.suffix + ".bak")
                backup_path.write_text(content, encoding="utf-8")
                backed_up = True

            # Perform replacement
            if replace_all:
                new_content = content.replace(old_string, new_string)
                occurrences_replaced = occurrences
            else:
                new_content = content.replace(old_string, new_string, 1)
                occurrences_replaced = 1

            # Write modified content
            path.write_text(new_content, encoding="utf-8")

            return {
                "success": True,
                "file_path": str(path.absolute()),
                "occurrences_found": occurrences,
                "occurrences_replaced": occurrences_replaced,
                "backed_up": backed_up,
            }

        except Exception as e:
            tool_error = ToolError(
                f"{self.name} failed: {e}",
                tool_name=self.name,
                details={"file_path": file_path},
            )
            return tool_error_payload(tool_error)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "file_path" not in kwargs:
            return False, "Missing required parameter: file_path"
        if "old_string" not in kwargs:
            return False, "Missing required parameter: old_string"
        if "new_string" not in kwargs:
            return False, "Missing required parameter: new_string"
        if not isinstance(kwargs["file_path"], str):
            return False, "Parameter 'file_path' must be a string"
        if not isinstance(kwargs["old_string"], str):
            return False, "Parameter 'old_string' must be a string"
        if not isinstance(kwargs["new_string"], str):
            return False, "Parameter 'new_string' must be a string"
        return True, None
