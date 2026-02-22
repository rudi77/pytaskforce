"""Tests for ProfileLoader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from taskforce.application.profile_loader import (
    _FALLBACK_CONFIG,
    DEFAULT_TOOL_NAMES,
    ProfileLoader,
)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with a dev.yaml profile."""
    dev_config = {
        "profile": "dev",
        "persistence": {"type": "file", "work_dir": ".taskforce"},
        "agent": {"max_steps": 30},
        "tools": DEFAULT_TOOL_NAMES,
    }
    (tmp_path / "dev.yaml").write_text(yaml.dump(dev_config))
    return tmp_path


@pytest.fixture
def loader(config_dir: Path) -> ProfileLoader:
    """Create a ProfileLoader pointing to the temp config directory."""
    return ProfileLoader(config_dir)


class TestProfileLoaderLoad:
    """Tests for ProfileLoader.load()."""

    def test_load_existing_profile(self, loader: ProfileLoader) -> None:
        config = loader.load("dev")
        assert config["profile"] == "dev"
        assert config["agent"]["max_steps"] == 30

    def test_load_missing_profile_raises(self, loader: ProfileLoader) -> None:
        with pytest.raises(FileNotFoundError, match="Profile not found"):
            loader.load("nonexistent")

    def test_load_custom_profile(self, config_dir: Path) -> None:
        custom_dir = config_dir / "custom"
        custom_dir.mkdir()
        custom_config = {"profile": "my_custom", "agent": {"max_steps": 5}}
        (custom_dir / "my_custom.yaml").write_text(yaml.dump(custom_config))

        loader = ProfileLoader(config_dir)
        config = loader.load("my_custom")
        assert config["profile"] == "my_custom"
        assert config["agent"]["max_steps"] == 5

    def test_standard_profile_takes_precedence_over_custom(
        self, config_dir: Path
    ) -> None:
        """If both {config_dir}/foo.yaml and {config_dir}/custom/foo.yaml exist,
        the standard location wins."""
        standard_config = {"profile": "foo", "source": "standard"}
        (config_dir / "foo.yaml").write_text(yaml.dump(standard_config))

        custom_dir = config_dir / "custom"
        custom_dir.mkdir()
        custom_config = {"profile": "foo", "source": "custom"}
        (custom_dir / "foo.yaml").write_text(yaml.dump(custom_config))

        loader = ProfileLoader(config_dir)
        config = loader.load("foo")
        assert config["source"] == "standard"


class TestProfileLoaderLoadSafe:
    """Tests for ProfileLoader.load_safe()."""

    def test_load_safe_existing_profile(self, loader: ProfileLoader) -> None:
        config = loader.load_safe("dev")
        assert config["profile"] == "dev"

    def test_load_safe_missing_returns_fallback(
        self, loader: ProfileLoader
    ) -> None:
        config = loader.load_safe("nonexistent")
        assert config == _FALLBACK_CONFIG
        # Verify it's a deep copy (not the same object)
        assert config is not _FALLBACK_CONFIG


class TestProfileLoaderGetDefaults:
    """Tests for ProfileLoader.get_defaults()."""

    def test_get_defaults_loads_dev(self, loader: ProfileLoader) -> None:
        config = loader.get_defaults()
        assert config["profile"] == "dev"

    def test_get_defaults_fallback_when_no_dev(self, tmp_path: Path) -> None:
        loader = ProfileLoader(tmp_path)
        config = loader.get_defaults()
        assert config == _FALLBACK_CONFIG


class TestProfileLoaderMergePluginConfig:
    """Tests for ProfileLoader.merge_plugin_config()."""

    def test_merge_agent_keys(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"agent": {"max_steps": 30, "model": "gpt-4"}}
        plugin: dict[str, Any] = {"agent": {"max_steps": 10}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["agent"]["max_steps"] == 10
        assert merged["agent"]["model"] == "gpt-4"

    def test_merge_context_policy_replaces(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"context_policy": {"max_items": 10}}
        plugin: dict[str, Any] = {"context_policy": {"max_items": 5, "extra": True}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["context_policy"] == {"max_items": 5, "extra": True}

    def test_merge_specialist_replaces(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"specialist": "coding"}
        plugin: dict[str, Any] = {"specialist": "rag"}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["specialist"] == "rag"

    def test_merge_persistence_work_dir(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {
            "persistence": {"type": "file", "work_dir": ".taskforce"}
        }
        plugin: dict[str, Any] = {"persistence": {"work_dir": ".plugin_data"}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["persistence"]["work_dir"] == ".plugin_data"
        assert merged["persistence"]["type"] == "file"

    def test_merge_mcp_servers_concatenated(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"mcp_servers": [{"name": "server1"}]}
        plugin: dict[str, Any] = {"mcp_servers": [{"name": "server2"}]}
        merged = loader.merge_plugin_config(base, plugin)
        assert len(merged["mcp_servers"]) == 2
        assert merged["mcp_servers"][0]["name"] == "server1"
        assert merged["mcp_servers"][1]["name"] == "server2"

    def test_merge_context_management_update(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"context_management": {"strategy": "fifo"}}
        plugin: dict[str, Any] = {"context_management": {"max_tokens": 1000}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["context_management"]["strategy"] == "fifo"
        assert merged["context_management"]["max_tokens"] == 1000

    def test_merge_does_not_mutate_base(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"agent": {"max_steps": 30}}
        plugin: dict[str, Any] = {"agent": {"max_steps": 10}}
        loader.merge_plugin_config(base, plugin)
        assert base["agent"]["max_steps"] == 30

    def test_merge_empty_plugin(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"agent": {"max_steps": 30}}
        merged = loader.merge_plugin_config(base, {})
        assert merged == base

    def test_merge_llm_not_overridden(self, loader: ProfileLoader) -> None:
        """Plugin should NOT be able to override llm config (security)."""
        base: dict[str, Any] = {"llm": {"default_model": "main"}}
        plugin: dict[str, Any] = {"llm": {"default_model": "hacked"}}
        merged = loader.merge_plugin_config(base, plugin)
        # Plugin doesn't have a 'llm' merge path, so base value is kept
        assert merged["llm"]["default_model"] == "main"
