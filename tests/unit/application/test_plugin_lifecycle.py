"""REST plugin lifecycle — discovery disable switch, init isolation, shutdown.

Covers the ``taskforce.plugins`` entry-point lifecycle in
``taskforce.application.plugin_loader``.

Spec: docs/spec/plugins.md.
"""

from __future__ import annotations

import pytest

from taskforce.application import plugin_loader
from taskforce.application.plugin_loader import (
    PluginInfo,
    PluginRegistry,
    discover_plugins,
    get_loaded_plugins,
    load_plugin,
    shutdown_plugins,
)


@pytest.fixture
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> PluginRegistry:
    """Swap the global plugin registry for a fresh one per test."""
    fresh = PluginRegistry()
    monkeypatch.setattr(plugin_loader, "_plugin_registry", fresh)
    return fresh


@pytest.mark.spec("plugins.disable_env_var_short_circuits_discovery")
@pytest.mark.parametrize("flag", ["1", "true", "yes", "on", "TRUE", "On"])
def test_disable_env_var_short_circuits_discovery(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    """TASKFORCE_DISABLE_PLUGINS short-circuits discover_plugins() to an
    empty list before any plugin code is loaded — case-insensitively."""
    monkeypatch.setenv("TASKFORCE_DISABLE_PLUGINS", flag)
    assert discover_plugins() == []


@pytest.mark.spec("plugins.plugin_initialize_failure_is_isolated")
def test_plugin_initialize_failure_is_isolated(
    isolated_registry: PluginRegistry,
) -> None:
    """A plugin whose initialize() raises is recorded with an error, stays
    uninitialized, and never appears in get_loaded_plugins()."""

    class _BrokenPlugin:
        name = "broken"
        version = "1.0.0"

        def initialize(self, config: dict) -> None:
            raise TypeError("bad plugin config")

    info = PluginInfo(name="broken", entry_point="broken:plugin")
    info.plugin_class = _BrokenPlugin
    isolated_registry.plugins["broken"] = info

    ok = load_plugin(info)

    assert ok is False
    assert info.initialized is False
    assert info.error is not None and "bad plugin config" in info.error
    assert get_loaded_plugins() == []


@pytest.mark.spec("plugins.plugin_shutdown_failure_does_not_block_others")
def test_plugin_shutdown_failure_does_not_block_others(
    isolated_registry: PluginRegistry,
) -> None:
    """One plugin's shutdown() raising does not prevent the rest from being
    shut down."""
    shut_down: list[str] = []

    class _Plugin:
        def __init__(self, name: str, fail: bool) -> None:
            self.name = name
            self.version = "1.0.0"
            self._fail = fail

        def shutdown(self) -> None:
            if self._fail:
                raise RuntimeError("shutdown boom")
            shut_down.append(self.name)

    for name, fail in [("bad", True), ("good", False)]:
        info = PluginInfo(name=name, entry_point=f"{name}:plugin")
        info.plugin_class = _Plugin
        info.instance = _Plugin(name, fail)
        info.initialized = True
        isolated_registry.plugins[name] = info

    shutdown_plugins()  # must not raise despite the bad plugin

    assert shut_down == ["good"]
