"""
Shell and PowerShell Tools

Provides shell command execution with safety limits and timeout handling.
Migrated from Agent V2 with full preservation of functionality.
"""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class ShellTool(ToolProtocol):
    """Execute shell commands with safety limits and timeout."""

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "Execute shell commands with timeout and safety limits"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
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

    def get_approval_preview(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        cwd = kwargs.get("cwd", "current directory")
        timeout = kwargs.get("timeout", 30)
        return f"⚠️ SHELL COMMAND EXECUTION\nTool: {self.name}\nCommand: {command}\nWorking Directory: {cwd}\nTimeout: {timeout}s"

    async def execute(
        self, command: str, timeout: int = 30, cwd: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
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
        try:
            # Safety check - block dangerous commands
            dangerous_patterns = [
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

            if any(pattern in command.lower() for pattern in dangerous_patterns):
                return {"success": False, "error": "Command blocked for safety reasons"}

            # Execute command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )

                success = process.returncode == 0
                stdout_text = stdout.decode() if stdout else ""
                stderr_text = stderr.decode() if stderr else ""

                resp = {
                    "success": success,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "returncode": process.returncode,
                    "command": command,
                }
                if not success:
                    resp["error"] = (
                        stderr_text or f"Command failed with code {process.returncode}"
                    )
                return resp
            except asyncio.TimeoutError:
                process.kill()
                return {
                    "success": False,
                    "error": f"Command timed out after {timeout}s",
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

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
    def parameters_schema(self) -> Dict[str, Any]:
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

    def get_approval_preview(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        cwd = kwargs.get("cwd", "current directory")
        timeout = kwargs.get("timeout", 30)
        return f"⚠️ POWERSHELL COMMAND EXECUTION\nTool: {self.name}\nCommand: {command}\nWorking Directory: {cwd}\nTimeout: {timeout}s"

    async def execute(
        self, command: str, timeout: int = 30, cwd: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
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

        # Resolve PowerShell executable
        shell_exe = shutil.which("pwsh") or shutil.which("powershell")
        if not shell_exe:
            return {
                "success": False,
                "error": "No PowerShell executable found (pwsh/powershell)",
            }

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
        cwd_path: Optional[str] = None
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

        try:
            # Execute command explicitly via PowerShell
            process = await asyncio.create_subprocess_exec(
                shell_exe,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd_path,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            return {
                "success": False,
                "error": f"Command timed out after {timeout}s",
                "command": command,
                "cwd": cwd_path,
                "returncode": None,
            }
        except asyncio.CancelledError:
            try:
                process.kill()
            except Exception:
                pass
            return {
                "success": False,
                "error": f"Command cancelled after {timeout}s",
                "command": command,
                "cwd": cwd_path,
                "returncode": None,
            }
        except Exception as e:
            try:
                process.kill()
            except Exception:
                pass
            return {
                "success": False,
                "error": str(e),
                "command": command,
                "cwd": cwd_path,
            }

        success = process.returncode == 0
        stdout_text = stdout.decode() if stdout else ""
        stderr_text = stderr.decode() if stderr else ""

        resp = {
            "success": success,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "returncode": process.returncode,
            "command": command,
        }
        if not success:
            resp["error"] = (
                stderr_text or f"Command failed with code {process.returncode}"
            )
        return resp

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "command" not in kwargs:
            return False, "Missing required parameter: command"
        if not isinstance(kwargs["command"], str):
            return False, "Parameter 'command' must be a string"
        return True, None

