"""Tests that the project ``work_dir`` reaches path-aware tools.

The conversations route resolves ``project_id`` to ``project.path``
and passes it as ``work_dir`` to the executor. The executor installs
a ``WorkspaceContextProtocol`` for the duration of the mission so
file/shell/python tools see the project as their default workspace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.core.interfaces.workspace import (
    get_workspace_context,
    resolve_workspace_path,
    set_workspace_context,
)


@pytest.fixture(autouse=True)
def clear_workspace_after_test():
    """Make sure no test leaks a workspace context into the next."""
    yield
    set_workspace_context(None)


class TestProjectWorkspaceContext:
    """``_ProjectWorkspace`` should expose the project root via the protocol."""

    def test_root_returns_configured_path(self, tmp_path: Path) -> None:
        from taskforce.application.executor import _ProjectWorkspace

        ws = _ProjectWorkspace(tmp_path)
        assert ws.root() == tmp_path

    def test_resolve_workspace_path_routes_relative_under_root(
        self, tmp_path: Path
    ) -> None:
        from taskforce.application.executor import _ProjectWorkspace

        set_workspace_context(_ProjectWorkspace(tmp_path))
        resolved = resolve_workspace_path("foo/bar.txt")
        assert resolved == (tmp_path / "foo" / "bar.txt").resolve()

    def test_resolve_workspace_path_rejects_traversal(
        self, tmp_path: Path
    ) -> None:
        from taskforce.application.executor import _ProjectWorkspace
        from taskforce.core.interfaces.workspace import WorkspaceTraversalError

        set_workspace_context(_ProjectWorkspace(tmp_path))
        with pytest.raises(WorkspaceTraversalError):
            resolve_workspace_path("../../../etc/passwd")

    def test_no_context_means_passthrough(self) -> None:
        # Bit-for-bit baseline: with no project linked, paths are
        # passed through unchanged so existing single-tenant behaviour
        # is preserved.
        assert get_workspace_context() is None
        assert resolve_workspace_path("foo/bar.txt") == Path("foo/bar.txt")


class TestShellToolDefaultCwd:
    """``shell_tool._default_workspace_dir`` picks up the workspace root."""

    def test_uses_workspace_root_when_set(self, tmp_path: Path) -> None:
        from taskforce.application.executor import _ProjectWorkspace
        from taskforce.infrastructure.tools.native.shell_tool import (
            _default_workspace_dir,
        )

        set_workspace_context(_ProjectWorkspace(tmp_path))
        assert _default_workspace_dir() == tmp_path

    def test_falls_back_to_process_cwd(self) -> None:
        import os

        from taskforce.infrastructure.tools.native.shell_tool import (
            _default_workspace_dir,
        )

        # No context installed (autouse fixture cleared it).
        assert str(_default_workspace_dir()) == os.getcwd()
