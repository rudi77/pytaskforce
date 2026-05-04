"""Sandboxed-executor protocol for dangerous tools (ADR-022 §5).

The framework's ``bash`` / ``shell`` / ``powershell`` tools today spawn
host subprocesses directly. In a multi-tenant deployment that's
unsafe: cooperative path scoping (``WorkspaceContextProtocol``) keeps
well-behaved tools inside their workspace, but a process can still
read host secrets, mount network sockets, or exhaust shared resources.

This module defines the contract for *executing* those tools so the
real isolation (containers, cgroups, gVisor, …) lives outside the
framework. The framework ships an in-process default that preserves
today's behaviour; the enterprise plugin replaces it with a
container-backed implementation. Tools call ``run()`` instead of
``asyncio.create_subprocess_exec`` directly so the exec strategy is
an installable concern.

Two protocols + two value objects keep the surface deliberately small:
the executor knows nothing about workspaces or tenants and is decided
once at startup, not per call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol


CommandKind = Literal["shell", "bash", "powershell"]


@dataclass(frozen=True)
class SandboxRequest:
    """One command to execute under the sandboxed executor.

    Attributes:
        kind: Which interpreter to use. ``shell`` lets the
            implementation pick the platform default.
        script: The command string. Implementations are expected to
            pass it to the interpreter as a single ``-c`` argument
            (or the platform equivalent).
        workspace_dir: Directory the command should run in. Sandbox
            implementations mount this read-write inside the
            container; in-process executors ``chdir`` into it.
        env: Additional environment variables to expose. Implementations
            are encouraged NOT to forward the host's full environment.
        timeout_seconds: Hard wall-clock limit. ``None`` means no
            framework-imposed timeout (a sandboxed implementation may
            still apply its own).
    """

    kind: CommandKind
    script: str
    workspace_dir: Path
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of one ``SandboxRequest``.

    The shape mirrors what the existing in-process tools return so
    they can adopt the executor without changing their public payloads.
    """

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False


class SandboxedExecutorProtocol(Protocol):
    """Run a dangerous-tool command and return the result.

    Implementations are responsible for whatever isolation they
    promise (container, jail, in-process). The framework default is
    in-process and explicitly *not* isolating — see
    :func:`taskforce.application.infrastructure_overrides.warn_if_multi_tenant_without_sandbox`
    for the startup warning that fires when this default is used in a
    multi-tenant runtime.
    """

    async def run(self, request: SandboxRequest) -> SandboxResult:
        """Execute ``request`` and return its outcome.

        Implementations MUST honour ``request.workspace_dir`` as the
        only filesystem the command can write to. Sandbox-backed
        implementations enforce this with a mount; the in-process
        default uses it as the subprocess CWD and trusts the
        framework's path-scoping (``WorkspaceContextProtocol``) to
        keep well-behaved tools inside it.

        Implementations SHOULD raise no exceptions for command failure;
        a non-zero ``returncode`` plus stderr is the expected channel
        for "the command ran and failed".
        """
        ...
