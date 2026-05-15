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

Windows fallback
----------------
``asyncio.create_subprocess_exec`` requires the Proactor event loop
on Windows. uvicorn started under certain configurations (especially
``--reload``) can end up running on a Selector loop where the call
raises a bare ``NotImplementedError`` — i.e. every shell/powershell
tool call dies before the agent even gets a result back. To keep the
shell tool useful in that environment we transparently fall back to
``subprocess.run`` on a worker thread. We lose cooperative SIGTERM
on cancel in the fallback path (``subprocess.run`` blocks the thread
until the timeout expires), but a working tool with degraded cancel
beats an unusable one.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from typing import Any

from taskforce.core.interfaces.sandbox import (
    CommandKind,
    SandboxedExecutorProtocol,
    SandboxRequest,
    SandboxResult,
)

# Grace window for SIGTERM before escalating to SIGKILL (or platform
# equivalents). Two seconds matches typical shell behavior and is short
# enough to keep cooperative-interrupt latency under control.
_TERMINATE_GRACE_SECONDS = 2.0


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    """Best-effort graceful → forceful subprocess termination.

    Sends SIGTERM (Linux/macOS) or TerminateProcess (Windows) first; if
    the process does not exit within ``_TERMINATE_GRACE_SECONDS``,
    escalates to SIGKILL. Always awaits the process so no zombies are
    left behind.
    """
    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    except Exception:  # pragma: no cover — best-effort cleanup
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=_TERMINATE_GRACE_SECONDS)
        return
    except TimeoutError:
        pass
    try:
        process.kill()
    except ProcessLookupError:
        return
    except Exception:  # pragma: no cover — best-effort cleanup
        pass
    try:
        await process.wait()
    except Exception:  # pragma: no cover
        pass


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

        try:
            process = await asyncio.create_subprocess_exec(*argv, **kwargs)
        except NotImplementedError:
            # Windows + Selector event loop combo. See the module docstring.
            return await _run_via_thread(argv, env, request)

        try:
            if request.timeout_seconds is None:
                stdout, stderr = await process.communicate()
            else:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=request.timeout_seconds,
                )
        except TimeoutError:
            await _terminate_process(process)
            return SandboxResult(
                stdout="",
                stderr=f"Command timed out after {request.timeout_seconds}s",
                returncode=-1,
                timed_out=True,
            )
        except asyncio.CancelledError:
            # Cooperative interrupt (ADR-019): tear down the subprocess
            # before propagating cancellation so it cannot outlive the
            # caller. Best-effort SIGTERM → SIGKILL escalation; we then
            # re-raise to honour the asyncio cancellation contract.
            await _terminate_process(process)
            raise

        return SandboxResult(
            stdout=(stdout or b"").decode("utf-8", errors="replace"),
            stderr=(stderr or b"").decode("utf-8", errors="replace"),
            returncode=process.returncode if process.returncode is not None else -1,
        )


async def _run_via_thread(
    argv: list[str],
    env: dict[str, str] | None,
    request: SandboxRequest,
) -> SandboxResult:
    """Blocking-subprocess fallback for Windows Selector event loop.

    Used when ``asyncio.create_subprocess_exec`` raises
    ``NotImplementedError`` (Windows + non-Proactor loop). We hand the
    call off to a worker thread via ``asyncio.to_thread`` so the event
    loop stays responsive. ``subprocess.run``'s built-in timeout
    handles the timeout case; on Windows it terminates the process with
    a hard kill on timeout, which is the best ``subprocess`` gives us.

    Cooperative SIGTERM-on-cancel from the Proactor path is *not*
    reproduced here — ``asyncio.to_thread`` runs the function to
    completion regardless of cancel, so a long-running command on the
    Selector loop will sit in the worker thread until the timeout
    elapses. Acceptable trade-off: a usable tool with weaker cancel
    semantics beats a fundamentally broken one.
    """

    def _blocking_run() -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            argv,
            cwd=str(request.workspace_dir) if request.workspace_dir else None,
            env=env,
            input=None,
            capture_output=True,
            timeout=request.timeout_seconds,
            check=False,
        )

    try:
        completed = await asyncio.to_thread(_blocking_run)
    except subprocess.TimeoutExpired as exc:
        return SandboxResult(
            stdout=(exc.stdout or b"").decode("utf-8", errors="replace") if exc.stdout else "",
            stderr=f"Command timed out after {request.timeout_seconds}s",
            returncode=-1,
            timed_out=True,
        )

    return SandboxResult(
        stdout=(completed.stdout or b"").decode("utf-8", errors="replace"),
        stderr=(completed.stderr or b"").decode("utf-8", errors="replace"),
        returncode=completed.returncode if completed.returncode is not None else -1,
    )
