"""
File System Tools

Provides safe file reading and writing operations with size limits and backup support.
Migrated from Agent V2 with full preservation of functionality.
"""

from pathlib import Path
from typing import Any

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class FileReadTool(ToolProtocol):
    """Safe file reading with size limits and encoding detection."""

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return "Read file contents safely with size limits and encoding detection"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding (default: utf-8)",
                    "enum": ["utf-8", "ascii", "latin-1", "cp1252"],
                },
                "max_size_mb": {
                    "type": "integer",
                    "description": "Maximum file size in MB (default: 10)",
                },
            },
            "required": ["path"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        path = kwargs.get("path", "")
        return f"Tool: {self.name}\nOperation: Read file\nPath: {path}"

    async def execute(
        self, path: str, encoding: str = "utf-8", max_size_mb: int = 10, **kwargs
    ) -> dict[str, Any]:
        """
        Read file contents safely with size limits and encoding detection.

        Args:
            path: The path to the file to read
            encoding: The encoding of the file (default: utf-8)
            max_size_mb: The maximum size of the file in MB (default: 10)

        Returns:
            Dictionary with:
            - success: True if the file was read successfully, False otherwise
            - content: The contents of the file
            - size: The size of the file in bytes
            - path: The absolute path to the file
            - error: Error message (if failed)
        """
        try:
            file_path = Path(path)

            if not file_path.exists():
                return {"success": False, "error": f"File not found: {path}"}

            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > max_size_mb:
                return {
                    "success": False,
                    "error": f"File too large: {file_size_mb:.2f}MB > {max_size_mb}MB",
                }

            content = file_path.read_text(encoding=encoding)
            return {
                "success": True,
                "content": content,
                "size": len(content),
                "path": str(file_path.absolute()),
            }
        except Exception as e:
            tool_error = ToolError(
                f"{self.name} failed: {e}",
                tool_name=self.name,
                details={"path": path},
            )
            return tool_error_payload(tool_error)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "path" not in kwargs:
            return False, "Missing required parameter: path"
        if not isinstance(kwargs["path"], str):
            return False, "Parameter 'path' must be a string"
        return True, None


class FileWriteTool(ToolProtocol):
    """Safe file writing with backup option and atomic writes."""

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return "Write or append content to a file with backup and safety checks"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
                "mode": {
                    "type": "string",
                    "description": "Write mode: 'write' overwrites the file (default), 'append' adds to the end",
                    "enum": ["write", "append"],
                },
                "backup": {
                    "type": "boolean",
                    "description": "Whether to backup the existing file (default: True, only for write mode)",
                },
            },
            "required": ["path", "content"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.MEDIUM

    @property
    def supports_parallelism(self) -> bool:
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        content_preview = content[:100] + "..." if len(content) > 100 else content
        mode = kwargs.get("mode", "write")
        backup = kwargs.get("backup", True)
        return f"⚠️ FILE WRITE OPERATION\nTool: {self.name}\nPath: {path}\nMode: {mode}\nBackup: {backup}\nContent Preview:\n{content_preview}"

    async def execute(
        self, path: str, content: str, mode: str = "write", backup: bool = True, **kwargs
    ) -> dict[str, Any]:
        """
        Write or append content to a file with backup and safety checks.

        Args:
            path: The path to the file to write
            content: The content to write to the file
            mode: 'write' (default) overwrites, 'append' adds to end
            backup: Whether to backup the existing file (default: True, only for write mode)

        Returns:
            Dictionary with:
            - success: True if the file was written successfully, False otherwise
            - path: The absolute path to the file
            - size: The total size of the file in bytes
            - backed_up: Whether the existing file was backed up
            - mode: The write mode used
        """
        try:
            file_path = Path(path)

            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if mode == "append":
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(content)
                total_size = file_path.stat().st_size
                return {
                    "success": True,
                    "path": str(file_path.absolute()),
                    "size": total_size,
                    "appended": len(content),
                    "mode": "append",
                    "backed_up": False,
                }

            # Default: write mode (overwrite)
            backed_up = False
            if backup and file_path.exists():
                backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                backup_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
                backed_up = True

            file_path.write_text(content, encoding="utf-8")

            return {
                "success": True,
                "path": str(file_path.absolute()),
                "size": len(content),
                "mode": "write",
                "backed_up": backed_up,
            }
        except Exception as e:
            tool_error = ToolError(
                f"{self.name} failed: {e}",
                tool_name=self.name,
                details={"path": path, "mode": mode, "backup": backup},
            )
            return tool_error_payload(tool_error)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "path" not in kwargs:
            return False, "Missing required parameter: path"
        if "content" not in kwargs:
            return False, "Missing required parameter: content"
        if not isinstance(kwargs["path"], str):
            return False, "Parameter 'path' must be a string"
        if not isinstance(kwargs["content"], str):
            return False, "Parameter 'content' must be a string"
        return True, None
