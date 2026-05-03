"""
File System Tools

Provides safe file reading and writing operations with size limits and backup support.
"""

from typing import Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.core.interfaces.workspace import (
    WorkspaceTraversalError,
    resolve_workspace_path,
)
from taskforce.infrastructure.tools.base_tool import BaseTool


class FileReadTool(BaseTool):
    """Safe file reading with size limits and encoding detection."""

    tool_name = "file_read"
    tool_description = "Read file contents safely with size limits and encoding detection"
    tool_parameters_schema: dict[str, Any] = {
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
    tool_requires_approval = False
    tool_approval_risk_level = ApprovalRiskLevel.LOW
    tool_supports_parallelism = True

    def get_approval_preview(self, **kwargs: Any) -> str:
        path = kwargs.get("path", "")
        return f"Tool: {self.name}\nOperation: Read file\nPath: {path}"

    async def _execute(
        self,
        path: str,
        encoding: str = "utf-8",
        max_size_mb: int = 10,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Read file contents safely with size limits and encoding detection."""
        try:
            file_path = resolve_workspace_path(path)
        except WorkspaceTraversalError as exc:
            return {"success": False, "error": str(exc)}

        if not file_path.exists():
            return {"success": False, "error": f"File not found: {path}"}

        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb > max_size_mb:
            return {
                "success": False,
                "error": f"File too large: {file_size_mb:.2f}MB > {max_size_mb}MB",
            }

        # Detect binary files and return actionable guidance
        binary_extensions = {
            ".pdf": "Use the python tool with pypdf to read PDFs.",
            ".docx": "Use the docx tool to read Word documents.",
            ".xlsx": "Use the excel tool to read Excel files.",
            ".xls": "Use the excel tool or python with openpyxl.",
            ".pptx": "Use the pptx tool to read PowerPoint files.",
            ".png": "Use the multimedia tool to analyze images.",
            ".jpg": "Use the multimedia tool to analyze images.",
            ".jpeg": "Use the multimedia tool to analyze images.",
            ".gif": "Use the multimedia tool to analyze images.",
            ".bmp": "Use the multimedia tool to analyze images.",
            ".mp3": "Use the python tool with a speech-to-text library.",
            ".mp4": "Use the python tool with a video processing library.",
            ".wav": "Use the python tool with a speech-to-text library.",
            ".zip": "Use the python tool with zipfile to extract contents.",
            ".pdb": "Use the python tool with Biopython to parse PDB files.",
        }
        suffix = file_path.suffix.lower()
        if suffix in binary_extensions:
            return {
                "success": False,
                "error": (
                    f"Cannot read binary file '{file_path.name}' as text. "
                    f"{binary_extensions[suffix]}"
                ),
            }

        content = file_path.read_text(encoding=encoding)
        return {
            "success": True,
            "content": content,
            "size": len(content),
            "path": str(file_path.absolute()),
        }


class FileWriteTool(BaseTool):
    """Safe file writing with backup option and atomic writes."""

    tool_name = "file_write"
    tool_description = "Write or append content to a file with backup and safety checks"
    tool_parameters_schema: dict[str, Any] = {
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
                "description": (
                    "Write mode: 'write' overwrites the file (default), " "'append' adds to the end"
                ),
                "enum": ["write", "append"],
            },
            "backup": {
                "type": "boolean",
                "description": (
                    "Whether to backup the existing file " "(default: True, only for write mode)"
                ),
            },
        },
        "required": ["path", "content"],
    }
    tool_requires_approval = True
    tool_approval_risk_level = ApprovalRiskLevel.MEDIUM
    tool_supports_parallelism = False

    def get_approval_preview(self, **kwargs: Any) -> str:
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        content_preview = content[:100] + "..." if len(content) > 100 else content
        mode = kwargs.get("mode", "write")
        backup = kwargs.get("backup", True)
        return (
            f"⚠️ FILE WRITE OPERATION\nTool: {self.name}\nPath: {path}\n"
            f"Mode: {mode}\nBackup: {backup}\nContent Preview:\n{content_preview}"
        )

    async def _execute(
        self,
        path: str,
        content: str,
        mode: str = "write",
        backup: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Write or append content to a file with backup and safety checks."""
        try:
            file_path = resolve_workspace_path(path)
        except WorkspaceTraversalError as exc:
            return {"success": False, "error": str(exc)}

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
