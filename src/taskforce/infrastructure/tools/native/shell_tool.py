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
import re
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


def _default_workspace_dir() -> Path:
    """Return the cwd a shell command should run in when none is passed.

    When the agent runs inside a project workspace (``WorkspaceContextProtocol``
    installed by the executor for project-linked conversations), commands
    default to the project root. Outside of a project the process cwd is
    used — today's behaviour bit-for-bit.
    """
    from taskforce.core.interfaces.workspace import get_workspace_context

    ctx = get_workspace_context()
    if ctx is not None:
        return ctx.root()
    return Path.cwd()


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

    workspace_dir = Path(cwd) if cwd else _default_workspace_dir()
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
        # The sandbox already SIGTERM/SIGKILL'd the subprocess (see
        # ``_terminate_process`` in ``infrastructure/sandbox/in_process.py``).
        # We swallow the cancellation here so the cooperative interrupt
        # path (ADR-019) sees a normal tool result and the agent can
        # persist a clean paused-state snapshot at the next ReAct boundary
        # rather than tearing down the whole task.
        return {
            "success": False,
            "error": "Command cancelled",
            "command": command,
        }
    except Exception as exc:
        # Some exceptions (notably ``NotImplementedError()`` raised by
        # ``asyncio.create_subprocess_exec`` on Windows when the event
        # loop policy is ``SelectorEventLoop``) have an empty ``str(exc)``,
        # which used to surface as ``"<tool> failed: "`` — completely
        # opaque to both the agent and the operator. Always include the
        # exception type so the failure mode is greppable in logs and
        # actionable for the agent. Issue #274.
        exc_type = type(exc).__name__
        exc_msg = str(exc) or repr(exc)
        tool_error = ToolError(
            f"{tool_name} failed: [{exc_type}] {exc_msg}",
            tool_name=tool_name,
            details={
                "command": command,
                "cwd": cwd,
                "timeout": timeout,
                "exception_type": exc_type,
            },
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
        payload["error"] = result.stderr or f"Command failed with code {result.returncode}"
    return payload


# Defence-in-depth blocklist of obviously-catastrophic commands.
#
# This is NOT a security boundary. A substring/regex blocklist cannot
# catch command substitution (``$(...)``, backticks), ``eval``, aliases
# or PATH tricks — the issue #277 bypasses. The real control is the
# mandatory HIGH-risk approval gate (``requires_approval = True``): a
# human sees and approves every command. The blocklist only exists to
# stop the agent from *accidentally* generating a destructive command.
#
# Matching runs against a normalised form of the command (lowercased,
# quotes stripped, whitespace collapsed) so the trivial obfuscations
# (``rm -rf  /*``, ``rm -rf '/'``) no longer slip through.
_DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+(?:-\S+\s+)+/"),          # rm <flags> /<path>
    re.compile(r"\bdd\s+if=/dev/(?:zero|u?random)"),
    re.compile(r"\bmkfs\b"),
    re.compile(r":\(\)\s*\{.*&.*\}\s*;?\s*:"),    # fork bomb
    re.compile(r">\s*/dev/sd[a-z]"),
    re.compile(r"\bformat\s+[a-z]:"),
    re.compile(r"\bdel\s+/[a-z]"),
]


def _normalise_for_blocklist(command: str) -> str:
    """Lowercase, strip quotes/backticks, collapse whitespace.

    Defeats the trivial blocklist bypasses (extra spaces, quoting). It
    does NOT defeat command substitution or ``eval`` — those are the
    approval gate's job, not the blocklist's.
    """
    no_quotes = command.lower().replace("'", "").replace('"', "").replace("`", " ")
    return re.sub(r"\s+", " ", no_quotes).strip()


def _is_dangerous_command(command: str) -> bool:
    """True when *command* matches a known-catastrophic pattern."""
    normalised = _normalise_for_blocklist(command)
    return any(pattern.search(normalised) for pattern in _DANGEROUS_PATTERNS)


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
        if _is_dangerous_command(command):
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
        if _is_dangerous_command(command):
            return {"success": False, "error": "Command blocked for safety reasons"}

        # ``_run_via_sandbox`` already wraps every non-cancellation exception
        # in a typed ``ToolError`` payload (see #274); no extra layer needed.
        return await _run_via_sandbox(
            tool_name=self.name,
            kind="bash",
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
