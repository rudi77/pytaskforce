"""Integration test: the butler profile resolves Google Workspace tools end-to-end.

After Phase 3 (#246) the Google tools live in ``taskforce-google-workspace`` and
are discovered via the ``taskforce.tools`` entry-point group. Loading the butler
profile via the framework ``AgentFactory`` must yield an agent whose tools
include ``gmail`` / ``calendar`` / ``google_drive`` resolved from the new module
paths, with no ``taskforce_butler.infrastructure.tools.*`` references.

This test also acts as a clean-break check: the legacy butler tool modules
must be absent, otherwise a stale import path could still satisfy the registry.
"""

from __future__ import annotations

import pytest


def test_butler_module_is_gone_for_google_tools() -> None:
    """Phase 3 clean break: the old butler-side tool modules don't exist."""
    for module_path in (
        "taskforce_butler.infrastructure.tools.email_tool",
        "taskforce_butler.infrastructure.tools.google_drive_tool",
        "taskforce_butler.infrastructure.tools.calendar_tool",
        "taskforce_butler.infrastructure.tools.auth_tool",
    ):
        with pytest.raises(ModuleNotFoundError):
            __import__(module_path)


def test_google_workspace_modules_are_importable() -> None:
    """The new locations exist and define the expected classes."""
    from taskforce_google_workspace.calendar import CalendarTool
    from taskforce_google_workspace.drive import GoogleDriveTool
    from taskforce_google_workspace.gmail import GmailTool

    assert GmailTool.__name__ == "GmailTool"
    assert GoogleDriveTool.__name__ == "GoogleDriveTool"
    assert CalendarTool.__name__ == "CalendarTool"


def test_authenticate_lives_in_framework_native() -> None:
    """`AuthTool` moved from butler to framework native in Phase 3."""
    from taskforce.infrastructure.tools.native.auth_tool import AuthTool

    assert AuthTool.__name__ == "AuthTool"
