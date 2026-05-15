"""Workspace context protocol for path-scoped tool execution.

ADR-022 §5 (first half): a thin contract that lets a host process
(typically the ``taskforce-enterprise`` plugin) tell tools where the
agent's writable workspace lives so file-, search- and shell-style
tools resolve relative paths against that root and reject ``..``
traversal.

This is the *cooperative* layer of ADR-022's split between path
scoping (cheap, well-behaved tools) and sandboxed execution (which
defends against malicious tools and lands in ADR-022 §5 second half /
Slice 5). Path scoping is opt-in: a host that never installs a
context gets today's behaviour bit-for-bit.

Two integration points::

* ``BaseTool`` subclasses that accept paths call
  :func:`resolve_workspace_path`. With no context set the helper
  returns ``Path(raw)`` exactly as today — no behaviour change for
  framework-only single-tenant deployments.
* External code (the enterprise plugin's per-request hook, a CLI
  flag, a test fixture) calls :func:`set_workspace_context` to install
  a per-request ``WorkspaceContextProtocol`` instance via the
  module-level ``ContextVar``.

The *content* of a workspace context — how it discovers its root for
the current ``(tenant_id, agent_id)`` — is intentionally not
specified by the framework. Plugins implement this however they like
(filesystem layout, database lookup, ContextVar chain, etc.) and the
framework only sees the resolved root.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from pathlib import Path
from typing import Protocol


class WorkspaceTraversalError(ValueError):
    """Raised when a path would escape the active workspace root.

    Triggered by ``..`` traversal that takes the resolved path
    outside the configured workspace, or by an absolute path that
    points elsewhere on the filesystem.

    The error is intentionally a ``ValueError`` subclass so existing
    ``try/except`` blocks around path validation still catch it.
    Tools should let it propagate to the executor, which reports it
    as a tool failure rather than a tool result.
    """


class WorkspaceContextProtocol(Protocol):
    """Contract for a per-request workspace scope.

    Implementations are typically built per-request by a host plugin
    (e.g. the enterprise plugin's ``EnterpriseWorkspaceContext`` rooted
    at ``${WORK_DIR}/tenants/${tenant_id}/agents/${agent_id}/workspace/``)
    and installed on the ``ContextVar`` for the duration of an agent
    invocation.
    """

    def root(self) -> Path:
        """Return the absolute filesystem root the agent may read/write under."""
        ...


_workspace_context: ContextVar[WorkspaceContextProtocol | None] = ContextVar(
    "taskforce_workspace_context", default=None
)


def set_workspace_context(ctx: WorkspaceContextProtocol | None) -> None:
    """Install (or clear) the active workspace context for this request scope."""
    _workspace_context.set(ctx)


def get_workspace_context() -> WorkspaceContextProtocol | None:
    """Return the active workspace context, or ``None`` when none is set."""
    return _workspace_context.get()


def resolve_workspace_path(raw_path: str | Path) -> Path:
    """Resolve ``raw_path`` against the active workspace, if any.

    Behaviour depends on whether a workspace context is active:

    * **No context** (single-tenant CLI, framework default): returns
      ``Path(raw_path)`` exactly as supplied — today's behaviour.
      No traversal check, no normalisation. This preserves
      bit-for-bit compatibility for callers that do not opt in.
    * **Context active**: resolves ``raw_path`` against the context's
      ``root()``. Absolute paths must lie inside the root; relative
      paths are joined to the root and any ``..`` segment that would
      escape raises :class:`WorkspaceTraversalError`.

    The check uses ``Path.resolve(strict=False)`` so the path does
    not need to exist yet — important for ``file_write`` which
    creates files. The check compares the resolved path's parents to
    the resolved root, so symlinks already on disk are followed
    before the check (this is intentional: a symlink that escapes
    the workspace is a configuration error and should fail).
    """
    ctx = get_workspace_context()
    if ctx is None:
        return Path(raw_path)

    root = ctx.root().resolve(strict=False)
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate

    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkspaceTraversalError(f"path {raw_path!r} escapes workspace root {root}") from exc

    return resolved


@contextlib.contextmanager
def workspace_scope(
    ctx: WorkspaceContextProtocol | None,
) -> Iterator[None]:
    """Install ``ctx`` as the active workspace for the duration of the block.

    Restores the previous context on exit so nested or sequential
    scopes don't leak. ``ctx=None`` is a no-op that still preserves
    the bracketing semantics — useful when callers don't always have a
    workspace to install.
    """
    if ctx is None:
        yield
        return
    token = _workspace_context.set(ctx)
    try:
        yield
    finally:
        _workspace_context.reset(token)


__all__ = [
    "WorkspaceContextProtocol",
    "WorkspaceTraversalError",
    "set_workspace_context",
    "get_workspace_context",
    "resolve_workspace_path",
    "workspace_scope",
]
