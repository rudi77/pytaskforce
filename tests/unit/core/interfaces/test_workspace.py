"""Tests for the workspace context protocol and path resolver.

Verifies the two opt-in branches of :func:`resolve_workspace_path`:

1. **No context active** (framework default): the function is a
   thin ``Path()`` constructor — no scoping, no traversal check, no
   normalisation. This preserves bit-for-bit compatibility for
   single-tenant CLI deployments that do not opt in.
2. **Context active**: relative paths are joined to the workspace
   root, absolute paths must lie inside the root, and any
   ``..`` traversal that would escape the root raises
   :class:`WorkspaceTraversalError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from taskforce.core.interfaces.workspace import (
    WorkspaceTraversalError,
    get_workspace_context,
    resolve_workspace_path,
    set_workspace_context,
)


@dataclass
class _StubContext:
    """Minimal WorkspaceContextProtocol for tests."""

    _root: Path

    def root(self) -> Path:
        return self._root


@pytest.fixture(autouse=True)
def _reset_context():
    set_workspace_context(None)
    yield
    set_workspace_context(None)


# ----------------------------------------------------------------------
# No context (default behaviour preserved)
# ----------------------------------------------------------------------


def test_resolve_with_no_context_returns_raw_path():
    """Single-tenant CLI: no context installed, no scoping applied."""
    assert get_workspace_context() is None
    result = resolve_workspace_path("relative/file.txt")
    assert result == Path("relative/file.txt")


def test_resolve_with_no_context_does_not_normalize():
    """No normalisation when no context — preserves today's behaviour."""
    raw = "../escape/me"
    result = resolve_workspace_path(raw)
    # When no context is installed the helper must NOT raise — it just
    # passes through. Path-based traversal is the host's problem.
    assert result == Path(raw)


def test_resolve_accepts_path_object_without_context():
    p = Path("a/b/c")
    assert resolve_workspace_path(p) == p


# ----------------------------------------------------------------------
# Context active: relative paths join to root
# ----------------------------------------------------------------------


def test_resolve_relative_path_joins_to_root(tmp_path: Path):
    set_workspace_context(_StubContext(tmp_path))
    result = resolve_workspace_path("notes.txt")
    assert result == (tmp_path / "notes.txt").resolve()


def test_resolve_nested_relative_path_joins_to_root(tmp_path: Path):
    set_workspace_context(_StubContext(tmp_path))
    result = resolve_workspace_path("docs/meeting/2026-04.md")
    expected = (tmp_path / "docs" / "meeting" / "2026-04.md").resolve()
    assert result == expected


# ----------------------------------------------------------------------
# Context active: absolute paths are scoped
# ----------------------------------------------------------------------


def test_resolve_absolute_path_inside_root_passes(tmp_path: Path):
    set_workspace_context(_StubContext(tmp_path))
    inside = tmp_path / "deep" / "file.txt"
    result = resolve_workspace_path(str(inside))
    assert result == inside.resolve()


def test_resolve_absolute_path_outside_root_rejected(tmp_path: Path):
    other = tmp_path.parent / "other_workspace"
    other.mkdir()
    set_workspace_context(_StubContext(tmp_path))
    with pytest.raises(WorkspaceTraversalError):
        resolve_workspace_path(str(other / "file.txt"))


# ----------------------------------------------------------------------
# Context active: traversal rejection
# ----------------------------------------------------------------------


def test_resolve_dotdot_traversal_rejected(tmp_path: Path):
    set_workspace_context(_StubContext(tmp_path))
    with pytest.raises(WorkspaceTraversalError):
        resolve_workspace_path("../escape.txt")


def test_resolve_deep_dotdot_traversal_rejected(tmp_path: Path):
    set_workspace_context(_StubContext(tmp_path))
    with pytest.raises(WorkspaceTraversalError):
        resolve_workspace_path("a/b/../../../escape.txt")


def test_resolve_dotdot_inside_root_allowed(tmp_path: Path):
    """``..`` segments that stay inside the workspace are fine."""
    set_workspace_context(_StubContext(tmp_path))
    result = resolve_workspace_path("a/b/../c.txt")
    assert result == (tmp_path / "a" / "c.txt").resolve()


@pytest.mark.skipif(
    Path("/").exists() is False,
    reason="POSIX-only path traversal scenario",
)
def test_resolve_root_path_rejected(tmp_path: Path):
    set_workspace_context(_StubContext(tmp_path))
    with pytest.raises(WorkspaceTraversalError):
        resolve_workspace_path("/etc/hosts")


# ----------------------------------------------------------------------
# Context lifecycle
# ----------------------------------------------------------------------


def test_clear_context_returns_to_default(tmp_path: Path):
    set_workspace_context(_StubContext(tmp_path))
    set_workspace_context(None)
    assert resolve_workspace_path("../wherever") == Path("../wherever")


def test_context_isolation_between_calls(tmp_path: Path):
    """A second context replaces the first."""
    other = tmp_path / "other"
    other.mkdir()
    set_workspace_context(_StubContext(tmp_path))
    assert resolve_workspace_path("a") == (tmp_path / "a").resolve()

    set_workspace_context(_StubContext(other))
    assert resolve_workspace_path("a") == (other / "a").resolve()
