"""Sandbox-aware tools for SWE-bench evaluation.

These tools implement ``ToolProtocol`` and delegate all I/O to the
Inspect AI ``SandboxEnvironment``, allowing the Taskforce agent to
operate inside a Docker container where the target repository lives.
"""

from __future__ import annotations

from typing import Any

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol

# Type alias — the actual SandboxEnvironment is resolved at runtime
# to avoid hard import-time dependency on inspect_ai.
SandboxEnv = Any


class SandboxShellTool(ToolProtocol):
    """Execute bash commands inside the SWE-bench Docker sandbox."""

    def __init__(self, sandbox_env: SandboxEnv) -> None:
        self._sandbox = sandbox_env

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return (
            "Execute bash commands inside the repository sandbox. "
            "Use this to run tests, install dependencies, inspect the "
            "repo structure, and apply changes."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Bash command to execute in the sandbox",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Command timeout in seconds (default: 120)",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (optional, relative to repo root)",
                },
            },
            "required": ["command"],
        }

    @property
    def requires_approval(self) -> bool:
        return False  # Sandbox is isolated — no approval needed

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"sandbox shell: {kwargs.get('command', '')}"

    async def execute(
        self, command: str, timeout: int = 120, cwd: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Execute a bash command inside the Docker sandbox."""
        try:
            result = await self._sandbox.exec(
                cmd=["bash", "--login", "-c", command],
                timeout=timeout,
                cwd=cwd,
            )
            resp: dict[str, Any] = {
                "success": result.success,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "returncode": result.returncode,
                "command": command,
            }
            if not result.success:
                resp["error"] = (
                    result.stderr or f"Command failed with code {result.returncode}"
                )
            return resp
        except TimeoutError:
            return {"success": False, "error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return tool_error_payload(
                ToolError(f"sandbox shell failed: {e}", tool_name="shell")
            )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "command" not in kwargs:
            return False, "Missing required parameter: command"
        return True, None


class SandboxFileReadTool(ToolProtocol):
    """Read files from inside the SWE-bench Docker sandbox."""

    def __init__(self, sandbox_env: SandboxEnv) -> None:
        self._sandbox = sandbox_env

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return (
            "Read file contents from the repository sandbox. "
            "Output includes line numbers for precise editing."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file (relative to repo root)",
                },
            },
            "required": ["path"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.NONE

    @property
    def supports_parallelism(self) -> bool:
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"sandbox read: {kwargs.get('path', '')}"

    async def execute(self, path: str, **kwargs) -> dict[str, Any]:
        """Read a file from the sandbox with line numbers."""
        try:
            content = await self._sandbox.read_file(path, text=True)
            # Add line numbers to help agent construct exact edit strings
            lines = content.splitlines()
            numbered = "\n".join(f"{i + 1:6d}\t{line}" for i, line in enumerate(lines))
            return {
                "success": True,
                "content": numbered,
                "path": path,
                "lines": len(lines),
            }
        except FileNotFoundError:
            return {"success": False, "error": f"File not found: {path}"}
        except Exception as e:
            return tool_error_payload(
                ToolError(f"sandbox file_read failed: {e}", tool_name="file_read")
            )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "path" not in kwargs:
            return False, "Missing required parameter: path"
        return True, None


class SandboxFileWriteTool(ToolProtocol):
    """Write files inside the SWE-bench Docker sandbox."""

    def __init__(self, sandbox_env: SandboxEnv) -> None:
        self._sandbox = sandbox_env

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return "Write or create files in the repository sandbox"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file (relative to repo root)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"sandbox write: {kwargs.get('path', '')}"

    async def execute(self, path: str, content: str, **kwargs) -> dict[str, Any]:
        """Write a file in the sandbox."""
        try:
            await self._sandbox.write_file(path, content)
            return {"success": True, "path": path, "bytes_written": len(content)}
        except Exception as e:
            return tool_error_payload(
                ToolError(f"sandbox file_write failed: {e}", tool_name="file_write")
            )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "path" not in kwargs:
            return False, "Missing required parameter: path"
        if "content" not in kwargs:
            return False, "Missing required parameter: content"
        return True, None


class SandboxGrepTool(ToolProtocol):
    """Search file contents inside the SWE-bench Docker sandbox using grep."""

    def __init__(self, sandbox_env: SandboxEnv) -> None:
        self._sandbox = sandbox_env

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return "Search file contents with regex patterns in the repository sandbox"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in (default: current dir)",
                },
                "include": {
                    "type": "string",
                    "description": "File glob pattern to include (e.g. '*.py')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum result lines to return (default: 50)",
                },
            },
            "required": ["pattern"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.NONE

    @property
    def supports_parallelism(self) -> bool:
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"sandbox grep: {kwargs.get('pattern', '')}"

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        include: str | None = None,
        max_results: int = 50,
        **kwargs,
    ) -> dict[str, Any]:
        """Run grep inside the sandbox with output limits."""
        try:
            # Normalize include pattern: '**/*.py' -> '*.py' (grep --include
            # uses fnmatch, not recursive globs)
            if include:
                include = include.lstrip("*").lstrip("/")
                if not include.startswith("*"):
                    include = (
                        f"*.{include}"
                        if "." in include and "*" not in include
                        else include
                    )

            cmd = ["grep", "-rn", "--color=never"]
            if include:
                cmd.extend(["--include", include])
            cmd.extend(["--", pattern, path])

            # Pipe through head to limit output and prevent context overflow
            import shlex

            shell_cmd = " ".join(shlex.quote(c) for c in cmd) + f" | head -{max_results}"
            result = await self._sandbox.exec(
                cmd=["bash", "-c", shell_cmd], timeout=30
            )

            # grep exit code 1 = no matches (not an error)
            matches_text = result.stdout or ""
            match_lines = [line for line in matches_text.splitlines() if line.strip()]
            if result.returncode == 1 and not match_lines:
                return {
                    "success": True,
                    "matches": "",
                    "match_count": 0,
                    "note": "No matches found",
                }
            if result.returncode > 1:
                return {
                    "success": False,
                    "error": (
                        result.stderr
                        or f"grep failed with code {result.returncode}"
                    ),
                }
            truncated = len(match_lines) >= max_results
            resp: dict[str, Any] = {
                "success": True,
                "matches": matches_text,
                "match_count": len(match_lines),
            }
            if truncated:
                resp["note"] = (
                    f"Output truncated to {max_results} lines. "
                    "Use a more specific pattern or path to narrow results."
                )
            return resp
        except Exception as e:
            return tool_error_payload(
                ToolError(f"sandbox grep failed: {e}", tool_name="grep")
            )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "pattern" not in kwargs:
            return False, "Missing required parameter: pattern"
        return True, None


class SandboxGlobTool(ToolProtocol):
    """Find files by pattern inside the SWE-bench Docker sandbox."""

    def __init__(self, sandbox_env: SandboxEnv) -> None:
        self._sandbox = sandbox_env

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return "Find files by name pattern in the repository sandbox"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "File glob pattern (e.g. '**/*.py', 'src/*.txt')",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: repo root)",
                },
            },
            "required": ["pattern"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.NONE

    @property
    def supports_parallelism(self) -> bool:
        return True

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"sandbox glob: {kwargs.get('pattern', '')}"

    async def execute(self, pattern: str, path: str = ".", **kwargs) -> dict[str, Any]:
        """Find files matching a glob pattern in the sandbox."""
        try:
            # Normalize pattern: strip leading **/ for find -name compatibility
            # '**/*.py' -> '*.py', 'src/**/*.py' -> '*.py' (find is recursive by default)
            find_pattern = pattern
            if "**/" in find_pattern:
                find_pattern = find_pattern.split("**/")[-1]

            cmd = ["bash", "-c", f"find {path} -name '{find_pattern}' -type f 2>/dev/null | sort | head -200"]
            result = await self._sandbox.exec(cmd=cmd, timeout=30)
            files = [f for f in (result.stdout or "").splitlines() if f.strip()]
            return {"success": True, "files": files, "count": len(files)}
        except Exception as e:
            return tool_error_payload(
                ToolError(f"sandbox glob failed: {e}", tool_name="glob")
            )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "pattern" not in kwargs:
            return False, "Missing required parameter: pattern"
        return True, None


class SandboxEditTool(ToolProtocol):
    """Apply targeted edits to files inside the SWE-bench Docker sandbox."""

    def __init__(self, sandbox_env: SandboxEnv) -> None:
        self._sandbox = sandbox_env

    @property
    def name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return (
            "Apply a targeted edit to a file in the repository sandbox. "
            "Replaces old_string with new_string in the specified file."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: false)",
                },
            },
            "required": ["path", "old_string", "new_string"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"sandbox edit: {kwargs.get('path', '')}"

    async def execute(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """Apply a find-and-replace edit inside the sandbox."""
        try:
            content = await self._sandbox.read_file(path, text=True)
            if old_string not in content:
                # Provide hints about similar content
                first_line = old_string.strip().split("\n")[0][:80]
                search_key = first_line[:40]
                similar = [
                    line.strip()
                    for line in content.splitlines()
                    if search_key and search_key in line
                ][:3]
                hint = ""
                if similar:
                    hint = f" Similar lines found: {similar}"
                return {
                    "success": False,
                    "error": f"old_string not found in {path}.{hint}",
                }
            count = content.count(old_string)
            if count > 1 and not replace_all:
                return {
                    "success": False,
                    "error": (
                        f"old_string found {count} times in {path}. "
                        "Provide more context to make it unique, or set replace_all=true."
                    ),
                }
            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
            await self._sandbox.write_file(path, new_content)
            return {
                "success": True,
                "path": path,
                "replacements": count if replace_all else 1,
            }
        except FileNotFoundError:
            return {"success": False, "error": f"File not found: {path}"}
        except Exception as e:
            return tool_error_payload(
                ToolError(f"sandbox edit failed: {e}", tool_name="edit")
            )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        for param in ("path", "old_string", "new_string"):
            if param not in kwargs:
                return False, f"Missing required parameter: {param}"
        return True, None


class SandboxGitTool(ToolProtocol):
    """Run git commands inside the SWE-bench Docker sandbox."""

    def __init__(self, sandbox_env: SandboxEnv) -> None:
        self._sandbox = sandbox_env

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return (
            "Run git commands in the repository sandbox. "
            "Use for diff, log, status, and other git operations."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Git command (without 'git' prefix), e.g. 'diff', 'status', 'log --oneline -10'",
                },
            },
            "required": ["command"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"sandbox git: {kwargs.get('command', '')}"

    async def execute(self, command: str, **kwargs) -> dict[str, Any]:
        """Run a git command inside the sandbox."""
        try:
            result = await self._sandbox.exec(
                cmd=["bash", "-c", f"git {command}"],
                timeout=60,
            )
            resp: dict[str, Any] = {
                "success": result.success,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "returncode": result.returncode,
            }
            if not result.success:
                resp["error"] = result.stderr or f"git command failed with code {result.returncode}"
            return resp
        except Exception as e:
            return tool_error_payload(
                ToolError(f"sandbox git failed: {e}", tool_name="git")
            )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if "command" not in kwargs:
            return False, "Missing required parameter: command"
        return True, None


def create_sandbox_tools(sandbox_env: SandboxEnv) -> list[ToolProtocol]:
    """Create a full set of sandbox-aware tools for SWE-bench evaluation.

    Args:
        sandbox_env: The Inspect AI SandboxEnvironment instance.

    Returns:
        List of ToolProtocol implementations that operate inside the sandbox.
    """
    return [
        SandboxShellTool(sandbox_env),
        SandboxFileReadTool(sandbox_env),
        SandboxFileWriteTool(sandbox_env),
        SandboxEditTool(sandbox_env),
        SandboxGrepTool(sandbox_env),
        SandboxGlobTool(sandbox_env),
        SandboxGitTool(sandbox_env),
    ]
