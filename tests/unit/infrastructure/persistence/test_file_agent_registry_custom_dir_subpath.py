"""Tests for the ``custom_dir_subpath`` kwarg on FileAgentRegistry.

This kwarg lets external packages (e.g. ``taskforce-enterprise``) point
the mutable custom-agent directory at a nested subpath like
``custom/<tenant_id>`` without forking the registry class.
"""

from __future__ import annotations

from taskforce.infrastructure.persistence.file_agent_registry import (
    FileAgentRegistry,
)


def test_default_custom_dir_subpath_is_custom(tmp_path) -> None:
    """Default value matches the pre-iteration-1 behaviour exactly."""
    registry = FileAgentRegistry(configs_dir=str(tmp_path))
    assert registry.custom_dir == tmp_path / "custom"
    assert registry.custom_dir.exists()


def test_custom_dir_subpath_simple_value(tmp_path) -> None:
    """A simple subpath value is honoured."""
    registry = FileAgentRegistry(
        configs_dir=str(tmp_path),
        custom_dir_subpath="agents",
    )
    assert registry.custom_dir == tmp_path / "agents"
    assert registry.custom_dir.exists()


def test_custom_dir_subpath_nested_value(tmp_path) -> None:
    """A nested subpath like ``custom/<tenant_id>`` works as the plugin needs."""
    registry = FileAgentRegistry(
        configs_dir=str(tmp_path),
        custom_dir_subpath="custom/tenant_a",
    )
    assert registry.custom_dir == tmp_path / "custom" / "tenant_a"
    assert registry.custom_dir.exists()


def test_two_subpaths_are_isolated(tmp_path) -> None:
    """Two registries with different subpaths land in disjoint directories."""
    registry_a = FileAgentRegistry(
        configs_dir=str(tmp_path),
        custom_dir_subpath="custom/tenant_a",
    )
    registry_b = FileAgentRegistry(
        configs_dir=str(tmp_path),
        custom_dir_subpath="custom/tenant_b",
    )

    assert registry_a.custom_dir != registry_b.custom_dir
    assert registry_a.custom_dir.parent == registry_b.custom_dir.parent
    assert registry_a.custom_dir.exists()
    assert registry_b.custom_dir.exists()
