"""Tests for the ``custom_dir_subpath`` kwarg on the unified AgentRegistry.

Mirrors ``tests/unit/infrastructure/persistence/test_file_agent_registry_custom_dir_subpath.py``
but for the application-layer ``AgentRegistry`` class.
"""

from __future__ import annotations

from taskforce.application.agent_registry import AgentRegistry


def test_default_custom_dir_subpath_is_custom(tmp_path) -> None:
    """Default value matches the pre-iteration-1 behaviour exactly."""
    registry = AgentRegistry(config_dir=tmp_path)
    assert registry.custom_dir == tmp_path / "custom"
    assert registry.custom_dir.exists()


def test_custom_dir_subpath_nested_value(tmp_path) -> None:
    """A nested subpath like ``custom/<tenant_id>`` works as the plugin needs."""
    registry = AgentRegistry(
        config_dir=tmp_path,
        custom_dir_subpath="custom/tenant_a",
    )
    assert registry.custom_dir == tmp_path / "custom" / "tenant_a"
    assert registry.custom_dir.exists()


def test_two_subpaths_are_isolated(tmp_path) -> None:
    """Two registries with different subpaths land in disjoint directories."""
    registry_a = AgentRegistry(
        config_dir=tmp_path,
        custom_dir_subpath="custom/tenant_a",
    )
    registry_b = AgentRegistry(
        config_dir=tmp_path,
        custom_dir_subpath="custom/tenant_b",
    )

    assert registry_a.custom_dir != registry_b.custom_dir
    assert registry_a.custom_dir.exists()
    assert registry_b.custom_dir.exists()
