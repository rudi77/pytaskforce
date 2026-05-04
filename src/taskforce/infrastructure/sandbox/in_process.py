"""In-process implementation of ``SandboxedExecutorProtocol``.

This is the framework's default executor: it runs the requested
command directly on the host via ``asyncio.create_subprocess_exec``
without any isolation other than the workspace directory chosen by
the caller. It exists so dangerous tools have a single, replaceable
exec seam — operators who want real isolation install a container-
backed implementation through
:func:`taskforce.application.infrastructure_overrides.set_sandboxed_executor`.

Single-tenant / self-hosted builds are bit-for-bit identical to the
previous behaviour where each tool called ``create_subprocess_exec``
on its own.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from typing import Any

from taskforce.core.interfaces.sandbox import (
    CommandKind,
    SandboxedExecutorProtocol,
    SandboxRequest,
    SandboxResult,
)


def _interpreter_argv(kind: CommandKind, script: str) -> list[str]:
    if kind == "bash":
        bash_path = shutil.which("bash") or "/bin/bash"
        return [bash_path, "-c", script]
    if kind == "powershell":
        # Prefer PowerShell 7+ when available; fall back to Windows PowerShell.
        ps_path = shutil.which("pwsh") or shutil.which("powershell")
        if ps_path is None:
            raise FileNotFoundError(
                "PowerShell executable not found (neither 'pwsh' nor 'powershell')."
            )
        return [
            ps_path,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ]
    # kind == "shell" — let the platform decide.
    if sys.platform == "win32":
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        return [comspec, "/c", script]
    sh_path = shutil.which("sh") or "/bin/sh"
    return [sh_path, "-c", script]


class InProcessSandboxedExecutor(SandboxedExecutorProtocol):
    """Default executor: run the command in a host subprocess.

    There is no isolation. Operators who care about multi-tenant
    safety install a container-backed implementation; this default's
    job is solely to keep the protocol seam in place so that
    replacement is one configuration call.
    """

    async def run(self, request: SandboxRequest) -> SandboxResult:
        argv = _interpreter_argv(request.kind, request.script)

        env: dict[str, str] | None = None
        if request.env:
            env = {**os.environ, **request.env}

        kwargs: dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": str(request.workspace_dir) if request.workspace_dir else None,
        }
        if env is not None:
            kwargs["env"] = env

        process = await asyncio.create_subprocess_exec(*argv, **kwargs)

        try:
            if request.timeout_seconds is None:
                stdout, stderr = await process.communicate()
            else:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=request.timeout_seconds,
                )
        except TimeoutError:
            process.kill()
            try:
                await process.wait()
            except Exception:  # pragma: no cover — best-effort cleanup
                pass
            return SandboxResult(
                stdout="",
                stderr=f"Command timed out after {request.timeout_seconds}s",
                returncode=-1,
                timed_out=True,
            )

        return SandboxResult(
            stdout=(stdout or b"").decode("utf-8", errors="replace"),
            stderr=(stderr or b"").decode("utf-8", errors="replace"),
            returncode=process.returncode if process.returncode is not None else -1,
        )
