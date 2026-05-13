"""Verify the four Google Workspace contributions register via entry-points.

Phase 3 (#246, ADR-027) extracted Gmail / Drive / Calendar into the
``taskforce-google-workspace`` package and declared them via the
``taskforce.tools`` entry-point group (ADR-026). These tests pin both
halves: the entry-point declaration *and* the matching short-names in
the resolved tool registry.

The ``authenticate`` tool stayed in the framework (provider-agnostic,
``taskforce.infrastructure.tools.native.auth_tool``); it's checked here
too because moving it out of the butler package was part of the same
phase.
"""

from __future__ import annotations

from importlib.metadata import entry_points

import pytest

from taskforce.application.agent_plugin_registry import (
    GROUP_TOOLS,
    load_tool_descriptors,
)
from taskforce.infrastructure.tools import registry as tool_registry


_GOOGLE_TOOLS = {
    "gmail": ("GmailTool", "taskforce_google_workspace.gmail"),
    "google_drive": ("GoogleDriveTool", "taskforce_google_workspace.drive"),
    "calendar": ("CalendarTool", "taskforce_google_workspace.calendar"),
}


@pytest.mark.parametrize("short_name,expected", list(_GOOGLE_TOOLS.items()))
def test_google_tool_resolves_via_entry_point(
    short_name: str,
    expected: tuple[str, str],
) -> None:
    """``importlib.metadata`` must list each Google tool under ``taskforce.tools``."""
    cls_name, module_path = expected
    eps = list(entry_points(group=GROUP_TOOLS))
    matches = [ep for ep in eps if ep.name == short_name]
    if not matches:
        pytest.skip(
            f"taskforce-google-workspace not installed (no entry-point for {short_name!r})"
        )
    ep = matches[0]
    assert ep.value == f"{module_path}:{cls_name}"


@pytest.mark.parametrize("short_name,expected", list(_GOOGLE_TOOLS.items()))
def test_loader_returns_correct_descriptor(
    short_name: str,
    expected: tuple[str, str],
) -> None:
    """``load_tool_descriptors`` returns the registry-compatible shape."""
    cls_name, module_path = expected
    descriptors = load_tool_descriptors()
    if short_name not in descriptors:
        pytest.skip(f"taskforce-google-workspace not installed (no descriptor for {short_name!r})")
    spec = descriptors[short_name]
    assert spec["type"] == cls_name
    assert spec["module"] == module_path
    assert spec["params"] == {}


@pytest.mark.parametrize("short_name,expected", list(_GOOGLE_TOOLS.items()))
def test_merged_registry_exposes_google_tool(
    short_name: str,
    expected: tuple[str, str],
) -> None:
    """The framework tool registry must surface each Google tool by short name."""
    cls_name, module_path = expected
    tool_registry._invalidate_caches()
    try:
        spec = tool_registry.get_tool_definition(short_name)
    finally:
        tool_registry._invalidate_caches()
    if spec is None:
        pytest.skip(f"taskforce-google-workspace not installed (registry miss for {short_name!r})")
    assert spec["type"] == cls_name
    assert spec["module"] == module_path


def test_authenticate_tool_is_framework_native() -> None:
    """`authenticate` moved out of butler in Phase 3 — must resolve to native."""
    spec = tool_registry.get_tool_definition("authenticate")
    assert spec is not None
    assert spec["module"] == "taskforce.infrastructure.tools.native.auth_tool"
    assert spec["type"] == "AuthTool"
