"""
Shell, Bash, and PowerShell Tools

Provides shell command execution with safety limits and timeout handling.
Migrated from Agent V2 with full preservation of functionality.

Security note:
    The shell tool uses a **blocklist** approach to prevent known-dangerous
    commands (e.g., ``rm -rf /``, fork bombs). Blocklists are inherently
    incomplete and should only be relied upon in **development / trusted
    execution contexts**. For production or untrusted environments, run
    shell commands inside a sandboxed container or VM, or switch to an
    allowlist-based approach.
"""

import os
from pathlib import Path
from typing import Any

from taskforce.application.infrastructure_overrides import get_sandboxed_executor
from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.interfaces.sandbox import (
    CommandKind,
    SandboxedExecutorProtocol,
    SandboxRequest,
)
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol
from taskforce.infrastructure.sandbox.in_process import InProcessSandboxedExecutor

# Module-level fallback executor reused across tool calls so the in-process
# default has a single instance per process.
_DEFAULT_EXECUTOR: SandboxedExecutorProtocol = InProcessSandboxedExecutor()


def _resolve_executor() -> SandboxedExecutorProtocol:
    """Return the currently installed sandboxed executor (or the default)."""
    return get_sandboxed_executor() or _DEFAULT_EXECUTOR


async def _run_via_sandbox(
    *,
    tool_name: str,
    kind: CommandKind,
    command: str,
    timeout: int,
    cwd: str | None,
) -> dict[str, Any]:
    """Execute a shell-style command through the sandbox executor seam.

    Maps :class:`SandboxResult` back to the historical dict shape every
    shell tool returns so its callers (and stored tool-result caches)
    are unaffected.
    """
    import asyncio

    workspace_dir = Path(cwd) if cwd else Path.cwd()
    request = SandboxRequest(
        kind=kind,
        script=command,
        workspace_dir=workspace_dir,
        timeout_seconds=float(timeout) if timeout else None,
    )
    try:
        result = await _resolve_executor().run(request)
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}
    except asyncio.CancelledError:
        # Tools historically returned a dict for cancellation rather than
        # propagating the exception so the agent loop sees a normal tool
        # result. Preserve that contract.
        return {
            "success": False,
            "error": f"Command cancelled after {timeout}s",
            "command": command,
        }
    except Exception as exc:  # pragma: no cover — defensive
        tool_error = ToolError(
            f"{tool_name} failed: {exc}",
            tool_name=tool_name,
            details={"command": command, "cwd": cwd, "timeout": timeout},
        )
        return tool_error_payload(tool_error)

    if result.timed_out:
        return {"success": False, "error": result.stderr}

    success = result.returncode == 0
    payload: dict[str, Any] = {
        "success": success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "command": command,
    }
    if not success:
        payload["error"] = (
            result.stderr or f"Command failed with code {result.returncode}"
        )
    return payload

# Dangerous command patterns shared across shell tools
_DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    "format c:",
    "del /f /s /q",
    ":(){ :|:& };:",  # Fork bomb
    "> /dev/sda",
    "mkfs.",
]


class ShellTool(ToolProtocol):
    """Execute shell commands with safety limits and timeout.

    Platform-aware: uses ``/bin/bash`` on Linux/macOS and the system
    default shell (``cmd.exe``) on Windows.
    """

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        if os.name == "nt":
            return "Execute shell commands with timeout and safety limits (Windows cmd)"
        return "Execute bash commands with timeout and safety limits"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Command timeout in seconds (default: 30)",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for command execution (optional)",
                },
            },
            "required": ["command"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.HIGH

    @property
    def supports_parallelism(self) -> bool:
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        cwd = kwargs.get("cwd", "current directory")
        timeout = kwargs.get("timeout", 30)
        return f"⚠️ SHELL COMMAND EXECUTION\nTool: {self.name}\nCommand: {command}\nWorking Directory: {cwd}\nTimeout: {timeout}s"

    async def execute(
        self, command: str, timeout: int = 30, cwd: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """
        Execute shell command with safety checks and timeout.

        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds (default: 30)
            cwd: Working directory for execution (optional)

        Returns:
            Dictionary with:
            - success: bool - True if command succeeded (returncode == 0)
            - stdout: str - Standard output
            - stderr: str - Standard error
            - returncode: int - Command return code
            - command: str - Executed command
            - error: str - Error message (if failed)
        """
        # Safety check - block dangerous commands
        if any(pattern in command.lower() for pattern in _DANGEROUS_PATTERNS):
            return {"success": False, "error": "Command blocked for safety reasons"}

        return await _run_via_sandbox(
            tool_name=self.name,
            kind="shell",
            command=command,
            timeout=timeout,
            cwd=cwd,
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "command" not in kwargs:
            return False, "Missing required parameter: command"
        if not isinstance(kwargs["command"], str):
            return False, "Parameter 'command' must be a string"
        return True, None


class BashTool(ToolProtocol):
    """Execute bash commands explicitly via ``/bin/bash``.

    Unlike ``ShellTool`` which adapts to the platform, ``BashTool``
    always uses bash.  Useful when the agent must run Unix commands
    regardless of the host OS (e.g. inside WSL or Docker containers).
    """

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return "Execute bash commands with timeout and safety limits"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Bash command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Command timeout in seconds (default: 30)",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for command execution (optional)",
                },
            },
            "required": ["command"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.HIGH

    @property
    def supports_parallelism(self) -> bool:
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        cwd = kwargs.get("cwd", "current directory")
        timeout = kwargs.get("timeout", 30)
        return (
            f"⚠️ BASH COMMAND EXECUTION\n"
            f"Tool: {self.name}\nCommand: {command}\n"
            f"Working Directory: {cwd}\nTimeout: {timeout}s"
        )

    async def execute(
        self, command: str, timeout: int = 30, cwd: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Execute bash command with safety checks and timeout.

        Args:
            command: Bash command to execute.
            timeout: Command timeout in seconds (default: 30).
            cwd: Working directory for execution (optional).

        Returns:
            Dictionary with success, stdout, stderr, returncode, command keys.
        """
        if any(pattern in command.lower() for pattern in _DANGEROUS_PATTERNS):
            return {"success": False, "error": "Command blocked for safety reasons"}

        try:
            return await _run_via_sandbox(
                tool_name=self.name,
                kind="bash",
                command=command,
                timeout=timeout,
                cwd=cwd,
            )
        except Exception as e:
            tool_error = ToolError(
                f"{self.name} failed: {e}",
                tool_name=self.name,
                details={"command": command, "cwd": cwd, "timeout": timeout},
            )
            return tool_error_payload(tool_error)

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "command" not in kwargs:
            return False, "Missing required parameter: command"
        if not isinstance(kwargs["command"], str):
            return False, "Parameter 'command' must be a string"
        return True, None


class PowerShellTool(ToolProtocol):
    """Execute PowerShell commands with safety limits and timeout."""

    @property
    def name(self) -> str:
        return "powershell"

    @property
    def description(self) -> str:
        return "Execute PowerShell commands with timeout and safety limits"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "PowerShell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Command timeout in seconds (default: 30)",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for command execution (optional)",
                },
            },
            "required": ["command"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.HIGH

    @property
    def supports_parallelism(self) -> bool:
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        cwd = kwargs.get("cwd", "current directory")
        timeout = kwargs.get("timeout", 30)
        return f"⚠️ POWERSHELL COMMAND EXECUTION\nTool: {self.name}\nCommand: {command}\nWorking Directory: {cwd}\nTimeout: {timeout}s"

    async def execute(
        self, command: str, timeout: int = 30, cwd: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """
        Execute PowerShell command with safety checks and timeout.

        Args:
            command: PowerShell command to execute
            timeout: Command timeout in seconds (default: 30)
            cwd: Working directory for execution (optional)

        Returns:
            Dictionary with:
            - success: bool - True if command succeeded (returncode == 0)
            - stdout: str - Standard output
            - stderr: str - Standard error
            - returncode: int - Command return code
            - command: str - Executed command
            - cwd: str - Working directory used
            - error: str - Error message (if failed)
        """
        # Safety check - block dangerous powershell commands (case-insensitive)
        dangerous_patterns = [
            "Remove-Item -Path * -Force",
            "Remove-Item -Path * -Recurse",
            "Remove-Item -Path * -Recurse -Force",
        ]
        lower_cmd = command.lower()
        lower_patterns = [p.lower() for p in dangerous_patterns]
        if any(pattern in lower_cmd for pattern in lower_patterns):
            return {"success": False, "error": "Command blocked for safety reasons"}

        # Coerce command to string (LLM may send non-string by mistake)
        if not isinstance(command, str):
            try:
                command = str(command)
            except Exception:
                return {
                    "success": False,
                    "error": "Invalid command type; expected string",
                }

        # Sanitize and validate cwd
        cwd_path: str | None = None
        if cwd is not None:
            if not isinstance(cwd, str):
                return {"success": False, "error": "cwd must be a string path"}
            sanitized = cwd.strip()
            if (sanitized.startswith('"') and sanitized.endswith('"')) or (
                sanitized.startswith("'") and sanitized.endswith("'")
            ):
                sanitized = sanitized[1:-1]
            # Expand env vars and user (~)
            sanitized = os.path.expandvars(os.path.expanduser(sanitized))
            # Normalize separators for Windows
            if os.name == "nt":
                sanitized = sanitized.replace("/", "\\")
            if sanitized == "":
                cwd_path = None
            else:
                p = Path(sanitized)
                if not p.exists() or not p.is_dir():
                    return {
                        "success": False,
                        "error": f"cwd does not exist or is not a directory: {sanitized}",
                    }
                cwd_path = str(p)

        # Force UTF-8 output from PowerShell to avoid encoding errors with
        # non-ASCII characters (e.g. German umlauts in file paths).
        utf8_prefix = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "$OutputEncoding = [System.Text.Encoding]::UTF8; "
        )
        wrapped_command = utf8_prefix + command

        return await _run_via_sandbox(
            tool_name=self.name,
            kind="powershell",
            command=wrapped_command,
            timeout=timeout,
            cwd=cwd_path,
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "command" not in kwargs:
            return False, "Missing required parameter: command"
        if not isinstance(kwargs["command"], str):
            return False, "Parameter 'command' must be a string"
        return True, None
