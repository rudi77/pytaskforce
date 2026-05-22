"""Tests for taskforce.application.agent_plugin_registry.

Verifies entry-point discovery for tools, CLI apps, and config dirs:
- well-formed entries are returned
- malformed values are logged and skipped (no exception)
- missing target modules are logged and skipped
- group routing is correct (iter_entry_points only yields the requested group)
"""

from __future__ import annotations

import sys
import types
from importlib.metadata import EntryPoint
from pathlib import Path
from unittest.mock import patch

import pytest

from taskforce.application import agent_plugin_registry as registry


def _ep(name: str, value: str, group: str) -> EntryPoint:
    """Construct an EntryPoint instance for tests (cross-Python-version safe)."""
    return EntryPoint(name=name, value=value, group=group)


class _FakeEntryPoint:
    """Minimal stand-in for ``importlib.metadata.EntryPoint`` whose ``load``
    method can be overridden — the real class is immutable so monkeypatching
    its attributes fails with ``AttributeError``.
    """

    def __init__(self, name: str, value: str, group: str, load_fn=None):
        self.name = name
        self.value = value
        self.group = group
        self._load_fn = load_fn

    def load(self):
        if self._load_fn is None:
            raise ModuleNotFoundError(self.value)
        return self._load_fn()


# ---------------------------------------------------------------------------
# iter_entry_points
# ---------------------------------------------------------------------------


def test_iter_entry_points_yields_group(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only entries of the requested group are yielded."""
    expected = [
        _ep("a", "mod_a:ClsA", "taskforce.tools"),
        _ep("b", "mod_b:ClsB", "taskforce.tools"),
    ]

    def fake_entry_points(group: str):
        assert group == "taskforce.tools"
        return expected

    monkeypatch.setattr(registry, "entry_points", fake_entry_points)
    result = list(registry.iter_entry_points("taskforce.tools"))
    assert result == expected


@pytest.mark.spec("plugins.broken_entry_point_is_skipped_with_warning")
def test_iter_entry_points_handles_metadata_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A metadata error becomes a logged warning + empty iterator."""

    def boom(group: str):
        raise RuntimeError("broken wheel metadata")

    monkeypatch.setattr(registry, "entry_points", boom)
    result = list(registry.iter_entry_points("taskforce.tools"))
    assert result == []


# ---------------------------------------------------------------------------
# load_tool_descriptors
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_tool_module() -> types.ModuleType:
    """Install a synthetic module so import succeeds."""
    mod_name = "_taskforce_test_fake_tool_mod"
    mod = types.ModuleType(mod_name)
    mod.FakeTool = type("FakeTool", (), {})
    sys.modules[mod_name] = mod
    yield mod
    sys.modules.pop(mod_name, None)


def test_load_tool_descriptors_returns_descriptor_shape(
    monkeypatch: pytest.MonkeyPatch,
    fake_tool_module: types.ModuleType,
) -> None:
    """Well-formed entry returns the registry-compatible descriptor."""
    monkeypatch.setattr(
        registry,
        "iter_entry_points",
        lambda group: iter(
            [_ep("fake_tool", "_taskforce_test_fake_tool_mod:FakeTool", "taskforce.tools")]
        )
        if group == registry.GROUP_TOOLS
        else iter([]),
    )
    result = registry.load_tool_descriptors()
    assert result == {
        "fake_tool": {
            "type": "FakeTool",
            "module": "_taskforce_test_fake_tool_mod",
            "params": {},
        }
    }


@pytest.mark.spec("plugins.broken_entry_point_is_skipped_with_warning")
def test_load_tool_descriptors_skips_malformed_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entry with no ':' separator is logged and skipped."""
    monkeypatch.setattr(
        registry,
        "iter_entry_points",
        lambda group: iter([_ep("bad", "no_colon_here", "taskforce.tools")])
        if group == registry.GROUP_TOOLS
        else iter([]),
    )
    assert registry.load_tool_descriptors() == {}


@pytest.mark.spec("plugins.broken_entry_point_is_skipped_with_warning")
def test_load_tool_descriptors_skips_unimportable_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entry pointing at a non-importable module is logged and skipped."""
    monkeypatch.setattr(
        registry,
        "iter_entry_points",
        lambda group: iter(
            [_ep("ghost", "this_module_does_not_exist:Ghost", "taskforce.tools")]
        )
        if group == registry.GROUP_TOOLS
        else iter([]),
    )
    assert registry.load_tool_descriptors() == {}


# ---------------------------------------------------------------------------
# load_cli_apps
# ---------------------------------------------------------------------------


@pytest.mark.spec("plugins.entry_point_cli_app_adds_subcommand")
def test_load_cli_apps_returns_loaded_typer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful ep.load returns the loaded attribute under its name."""
    sentinel = object()
    fake_ep = _FakeEntryPoint(
        "butler", "mod_x:app", registry.GROUP_CLI_APPS, load_fn=lambda: sentinel
    )
    monkeypatch.setattr(
        registry,
        "iter_entry_points",
        lambda group: iter([fake_ep]) if group == registry.GROUP_CLI_APPS else iter([]),
    )
    result = registry.load_cli_apps()
    assert result == {"butler": sentinel}


@pytest.mark.spec("plugins.broken_entry_point_is_skipped_with_warning")
def test_load_cli_apps_skips_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing ep.load is logged and skipped."""

    def boom():
        raise ModuleNotFoundError("mod_x not installed")

    fake_ep = _FakeEntryPoint("ghost", "mod_x:app", registry.GROUP_CLI_APPS, load_fn=boom)
    monkeypatch.setattr(
        registry,
        "iter_entry_points",
        lambda group: iter([fake_ep]) if group == registry.GROUP_CLI_APPS else iter([]),
    )
    assert registry.load_cli_apps() == {}


# ---------------------------------------------------------------------------
# load_config_dirs
# ---------------------------------------------------------------------------


@pytest.mark.spec("plugins.entry_point_config_dir_resolves_profile")
@pytest.mark.spec("plugins.config_dir_probes_three_candidate_paths")
@pytest.mark.spec("profiles.entry_point_packages_register_config_dirs")
def test_load_config_dirs_resolves_relative_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Entry-point resolves relative to the imported package dir."""
    # Build a synthetic package with a __file__ and a sibling configs/ dir.
    package_dir = tmp_path / "fake_pkg"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("")
    configs_dir = package_dir / "configs"
    configs_dir.mkdir()

    mod_name = "_taskforce_test_fake_config_pkg"
    mod = types.ModuleType(mod_name)
    mod.__file__ = str(package_dir / "__init__.py")
    sys.modules[mod_name] = mod
    try:
        monkeypatch.setattr(
            registry,
            "iter_entry_points",
            lambda group: iter(
                [_ep("fake", f"{mod_name}:configs", registry.GROUP_CONFIG_DIRS)]
            )
            if group == registry.GROUP_CONFIG_DIRS
            else iter([]),
        )
        result = registry.load_config_dirs()
    finally:
        sys.modules.pop(mod_name, None)

    assert "fake" in result
    assert result["fake"].resolve() == configs_dir.resolve()


@pytest.mark.spec("plugins.broken_entry_point_is_skipped_with_warning")
@pytest.mark.spec("plugins.config_dir_probes_three_candidate_paths")
def test_load_config_dirs_skips_missing_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """If none of the candidate dirs exist, the entry is logged and skipped."""
    package_dir = tmp_path / "fake_pkg_no_configs"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("")
    # No configs subdir created intentionally.

    mod_name = "_taskforce_test_fake_no_configs_pkg"
    mod = types.ModuleType(mod_name)
    mod.__file__ = str(package_dir / "__init__.py")
    sys.modules[mod_name] = mod
    try:
        monkeypatch.setattr(
            registry,
            "iter_entry_points",
            lambda group: iter(
                [_ep("fake", f"{mod_name}:configs", registry.GROUP_CONFIG_DIRS)]
            )
            if group == registry.GROUP_CONFIG_DIRS
            else iter([]),
        )
        result = registry.load_config_dirs()
    finally:
        sys.modules.pop(mod_name, None)
    assert result == {}


@pytest.mark.spec("plugins.broken_entry_point_is_skipped_with_warning")
def test_load_config_dirs_skips_unimportable_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing module produces a logged warning + skipped entry."""
    monkeypatch.setattr(
        registry,
        "iter_entry_points",
        lambda group: iter(
            [_ep("ghost", "nonexistent_pkg_for_testing:configs", registry.GROUP_CONFIG_DIRS)]
        )
        if group == registry.GROUP_CONFIG_DIRS
        else iter([]),
    )
    assert registry.load_config_dirs() == {}


@pytest.mark.spec("plugins.config_dir_probes_three_candidate_paths")
def test_load_config_dirs_probes_parent_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Resolution falls through to ``package_dir.parent.parent/relpath`` —
    the editable-install layout ``agents/<name>/configs`` where the package
    lives at ``agents/<name>/src/<pkg>``."""
    package_dir = tmp_path / "agent_root" / "src" / "fake_pkg2"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("")
    # configs/ sits two levels above the package — neither the first nor the
    # second probe candidate, so this only resolves if all three are tried.
    configs_dir = package_dir.parent.parent / "configs"
    configs_dir.mkdir()

    mod_name = "_taskforce_test_fake_config_pkg2"
    mod = types.ModuleType(mod_name)
    mod.__file__ = str(package_dir / "__init__.py")
    sys.modules[mod_name] = mod
    try:
        monkeypatch.setattr(
            registry,
            "iter_entry_points",
            lambda group: iter(
                [_ep("fake2", f"{mod_name}:configs", registry.GROUP_CONFIG_DIRS)]
            )
            if group == registry.GROUP_CONFIG_DIRS
            else iter([]),
        )
        result = registry.load_config_dirs()
    finally:
        sys.modules.pop(mod_name, None)

    assert "fake2" in result
    assert result["fake2"].resolve() == configs_dir.resolve()


# ---------------------------------------------------------------------------
# Integration: registry merge picks up entry-point tools
# ---------------------------------------------------------------------------


@pytest.mark.spec("plugins.entry_point_tool_appears_in_registry")
def test_tool_registry_picks_up_entry_point_tools(
    monkeypatch: pytest.MonkeyPatch,
    fake_tool_module: types.ModuleType,
) -> None:
    """Patching load_tool_descriptors makes the merged registry expose the tool."""
    from taskforce.infrastructure.tools import registry as tool_registry

    fake_descriptor = {
        "fake_ep_tool": {
            "type": "FakeTool",
            "module": "_taskforce_test_fake_tool_mod",
            "params": {},
        }
    }

    monkeypatch.setattr(
        "taskforce.application.agent_plugin_registry.load_tool_descriptors",
        lambda: fake_descriptor,
    )
    # Clear caches so the next lookup picks up the patched descriptor.
    tool_registry._invalidate_caches()
    try:
        assert tool_registry.is_registered("fake_ep_tool")
        spec = tool_registry.get_tool_definition("fake_ep_tool")
        assert spec is not None
        assert spec["type"] == "FakeTool"
        assert spec["module"] == "_taskforce_test_fake_tool_mod"
    finally:
        tool_registry._invalidate_caches()


@pytest.mark.spec("plugins.entry_point_tool_overrides_builtin")
@pytest.mark.spec("tools.entry_point_tool_overrides_builtin")
def test_entry_point_overrides_builtin(
    monkeypatch: pytest.MonkeyPatch,
    fake_tool_module: types.ModuleType,
) -> None:
    """When an entry-point declares the same short name, it wins over the builtin."""
    from taskforce.infrastructure.tools import registry as tool_registry

    override = {
        "python": {
            "type": "FakeTool",
            "module": "_taskforce_test_fake_tool_mod",
            "params": {},
        }
    }
    monkeypatch.setattr(
        "taskforce.application.agent_plugin_registry.load_tool_descriptors",
        lambda: override,
    )
    tool_registry._invalidate_caches()
    try:
        spec = tool_registry.get_tool_definition("python")
        assert spec is not None
        assert spec["module"] == "_taskforce_test_fake_tool_mod"
        assert spec["type"] == "FakeTool"
    finally:
        tool_registry._invalidate_caches()
