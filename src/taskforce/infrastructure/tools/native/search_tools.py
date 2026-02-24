"""
Search Tools - Grep and Glob

Provides powerful file searching capabilities similar to Claude Code:
- GrepTool: Search file contents using regex patterns (like ripgrep)
- GlobTool: Find files by name patterns (like find with glob syntax)
"""

import re
from pathlib import Path
from typing import Any

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class GrepTool(ToolProtocol):
    """
    Search file contents using regular expressions.

    Similar to ripgrep (rg), this tool searches for patterns in files with support for:
    - Full regex syntax
    - File filtering by glob patterns or file types
    - Context lines (before/after matches)
    - Multiple output modes (content, files_with_matches, count)
    """

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return (
            "Search file contents using regular expressions. "
            "Supports regex patterns, file filtering by glob/type, context lines, "
            "and multiple output modes (content, files_with_matches, count)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in (default: current directory)",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py', '**/*.ts')",
                },
                "file_type": {
                    "type": "string",
                    "description": "File type to search (e.g., 'py', 'js', 'ts', 'rust')",
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "description": "Output mode: 'content' shows lines, 'files_with_matches' shows paths, 'count' shows counts",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case insensitive search (default: false)",
                },
                "context_before": {
                    "type": "integer",
                    "description": "Number of lines to show before each match",
                },
                "context_after": {
                    "type": "integer",
                    "description": "Number of lines to show after each match",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 100)",
                },
                "include_line_numbers": {
                    "type": "boolean",
                    "description": "Include line numbers in output (default: true)",
                },
            },
            "required": ["pattern"],
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
        pattern = kwargs.get("pattern", "")
        path = kwargs.get("path", ".")
        return f"Tool: {self.name}\nOperation: Search for pattern\nPattern: {pattern}\nPath: {path}"

    async def execute(  # type: ignore[override]
        self,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        file_type: str | None = None,
        output_mode: str = "files_with_matches",
        case_insensitive: bool = False,
        context_before: int = 0,
        context_after: int = 0,
        max_results: int = 100,
        include_line_numbers: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Search file contents using regular expressions.

        Args:
            pattern: Regular expression pattern to search for
            path: File or directory to search in
            glob: Glob pattern to filter files
            file_type: File type to search (e.g., 'py', 'js')
            output_mode: Output mode (content, files_with_matches, count)
            case_insensitive: Case insensitive search
            context_before: Lines to show before match
            context_after: Lines to show after match
            max_results: Maximum results to return
            include_line_numbers: Include line numbers in output

        Returns:
            Dictionary with search results
        """
        try:
            search_path = Path(path)
            if not search_path.exists():
                return {"success": False, "error": f"Path not found: {path}"}

            # Compile regex pattern
            flags = re.IGNORECASE if case_insensitive else 0
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                return {"success": False, "error": f"Invalid regex pattern: {e}"}

            # Build file type to extension mapping
            type_to_ext = {
                "py": "*.py",
                "python": "*.py",
                "js": "*.js",
                "javascript": "*.js",
                "ts": "*.ts",
                "typescript": "*.ts",
                "tsx": "*.tsx",
                "jsx": "*.jsx",
                "rust": "*.rs",
                "go": "*.go",
                "java": "*.java",
                "c": "*.c",
                "cpp": "*.cpp",
                "h": "*.h",
                "hpp": "*.hpp",
                "md": "*.md",
                "yaml": "*.yaml",
                "yml": "*.yml",
                "json": "*.json",
                "toml": "*.toml",
                "html": "*.html",
                "css": "*.css",
                "sql": "*.sql",
                "sh": "*.sh",
                "bash": "*.sh",
            }

            # Determine glob pattern
            if file_type and file_type.lower() in type_to_ext:
                glob_pattern = type_to_ext[file_type.lower()]
            elif glob:
                glob_pattern = glob
            else:
                glob_pattern = None

            # Collect files to search
            files_to_search = self._collect_files(search_path, glob_pattern)

            results = []
            files_with_matches = []
            match_counts: dict[str, int] = {}
            total_matches = 0

            for file_path in files_to_search:
                if total_matches >= max_results:
                    break

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    lines = content.splitlines()
                    file_matches = []

                    for line_num, line in enumerate(lines, 1):
                        if regex.search(line):
                            file_matches.append((line_num, line))
                            total_matches += 1
                            if total_matches >= max_results:
                                break

                    if file_matches:
                        files_with_matches.append(str(file_path))
                        match_counts[str(file_path)] = len(file_matches)

                        if output_mode == "content":
                            for line_num, line in file_matches:
                                # Get context lines
                                context_lines = []
                                if context_before > 0:
                                    start = max(0, line_num - context_before - 1)
                                    for ctx_num in range(start, line_num - 1):
                                        ctx_line = lines[ctx_num] if ctx_num < len(lines) else ""
                                        context_lines.append((ctx_num + 1, ctx_line, "before"))

                                context_lines.append((line_num, line, "match"))

                                if context_after > 0:
                                    end = min(len(lines), line_num + context_after)
                                    for ctx_num in range(line_num, end):
                                        ctx_line = lines[ctx_num] if ctx_num < len(lines) else ""
                                        context_lines.append((ctx_num + 1, ctx_line, "after"))

                                if include_line_numbers:
                                    result_entry = {
                                        "file": str(file_path),
                                        "line_number": line_num,
                                        "content": line,
                                        "context": context_lines if context_before or context_after else None,
                                    }
                                else:
                                    result_entry = {
                                        "file": str(file_path),
                                        "content": line,
                                        "context": context_lines if context_before or context_after else None,
                                    }
                                results.append(result_entry)

                except (OSError, UnicodeDecodeError):
                    # Skip files that can't be read
                    continue

            # Format output based on mode
            if output_mode == "files_with_matches":
                return {
                    "success": True,
                    "files": files_with_matches,
                    "count": len(files_with_matches),
                    "pattern": pattern,
                }
            elif output_mode == "count":
                return {
                    "success": True,
                    "counts": match_counts,
                    "total_matches": total_matches,
                    "files_searched": len(files_to_search),
                    "pattern": pattern,
                }
            else:  # content
                return {
                    "success": True,
                    "matches": results,
                    "total_matches": len(results),
                    "files_with_matches": len(files_with_matches),
                    "pattern": pattern,
                }

        except Exception as e:
            tool_error = ToolError(
                f"{self.name} failed: {e}",
                tool_name=self.name,
                details={"pattern": pattern, "path": path},
            )
            return tool_error_payload(tool_error)

    def _collect_files(self, search_path: Path, glob_pattern: str | None) -> list[Path]:
        """Collect files to search based on path and glob pattern."""
        files = []

        if search_path.is_file():
            files.append(search_path)
        elif search_path.is_dir():
            if glob_pattern:
                # Handle recursive glob patterns
                if "**" in glob_pattern:
                    files.extend(search_path.glob(glob_pattern))
                else:
                    files.extend(search_path.rglob(glob_pattern))
            else:
                # Search all text files recursively
                for file_path in search_path.rglob("*"):
                    if file_path.is_file() and not self._is_binary(file_path):
                        files.append(file_path)

        # Filter out common non-text directories
        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build"}
        files = [f for f in files if not any(skip_dir in f.parts for skip_dir in skip_dirs)]

        return files

    def _is_binary(self, file_path: Path) -> bool:
        """Check if a file is likely binary."""
        binary_extensions = {
            ".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib",
            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
            ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
            ".mp3", ".mp4", ".avi", ".mov", ".wav",
            ".bin", ".dat", ".db", ".sqlite",
        }
        return file_path.suffix.lower() in binary_extensions

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "pattern" not in kwargs:
            return False, "Missing required parameter: pattern"
        if not isinstance(kwargs["pattern"], str):
            return False, "Parameter 'pattern' must be a string"
        return True, None


class GlobTool(ToolProtocol):
    """
    Find files by name patterns using glob syntax.

    Similar to find command with glob patterns, this tool locates files by:
    - Glob pattern matching (e.g., '**/*.py', 'src/**/*.ts')
    - Optional sorting by modification time
    - Filtering by file type
    """

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return (
            "Find files by name patterns using glob syntax. "
            "Returns matching file paths sorted by modification time. "
            "Supports patterns like '**/*.py' or 'src/**/*.ts'."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files (e.g., '**/*.py', 'src/**/*.ts')",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: current directory)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 100)",
                },
                "sort_by_mtime": {
                    "type": "boolean",
                    "description": "Sort results by modification time (default: true)",
                },
                "include_hidden": {
                    "type": "boolean",
                    "description": "Include hidden files (default: false)",
                },
                "files_only": {
                    "type": "boolean",
                    "description": "Return only files, not directories (default: true)",
                },
            },
            "required": ["pattern"],
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
        pattern = kwargs.get("pattern", "")
        path = kwargs.get("path", ".")
        return f"Tool: {self.name}\nOperation: Find files\nPattern: {pattern}\nPath: {path}"

    async def execute(  # type: ignore[override]
        self,
        pattern: str,
        path: str = ".",
        max_results: int = 100,
        sort_by_mtime: bool = True,
        include_hidden: bool = False,
        files_only: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Find files by name patterns using glob syntax.

        Args:
            pattern: Glob pattern to match files
            path: Directory to search in
            max_results: Maximum results to return
            sort_by_mtime: Sort by modification time
            include_hidden: Include hidden files
            files_only: Return only files (not directories)

        Returns:
            Dictionary with matching file paths
        """
        try:
            search_path = Path(path)
            if not search_path.exists():
                return {"success": False, "error": f"Path not found: {path}"}
            if not search_path.is_dir():
                return {"success": False, "error": f"Path is not a directory: {path}"}

            # Collect matching files
            skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build"}

            matches = []
            for match in search_path.glob(pattern):
                # Skip common non-essential directories
                if any(skip_dir in match.parts for skip_dir in skip_dirs):
                    continue

                # Skip hidden files if not included
                if not include_hidden and any(part.startswith(".") for part in match.parts[len(search_path.parts):]):
                    continue

                # Skip directories if files_only
                if files_only and match.is_dir():
                    continue

                matches.append(match)

            # Sort by modification time if requested
            if sort_by_mtime:
                matches.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

            # Limit results
            matches = matches[:max_results]

            # Convert to string paths
            file_paths = [str(m) for m in matches]

            return {
                "success": True,
                "files": file_paths,
                "count": len(file_paths),
                "pattern": pattern,
                "search_path": str(search_path.absolute()),
            }

        except Exception as e:
            tool_error = ToolError(
                f"{self.name} failed: {e}",
                tool_name=self.name,
                details={"pattern": pattern, "path": path},
            )
            return tool_error_payload(tool_error)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "pattern" not in kwargs:
            return False, "Missing required parameter: pattern"
        if not isinstance(kwargs["pattern"], str):
            return False, "Parameter 'pattern' must be a string"
        return True, None
