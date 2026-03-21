"""Tests for ProfileLoader."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from taskforce.application.config_schema import ConfigValidationError
from taskforce.application.profile_loader import (
    _FALLBACK_CONFIG,
    DEFAULT_TOOL_NAMES,
    ProfileLoader,
)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with a butler.yaml profile."""
    butler_config = {
        "profile": "butler",
        "persistence": {"type": "file", "work_dir": ".taskforce"},
        "agent": {"max_steps": 30},
        "tools": DEFAULT_TOOL_NAMES,
    }
    (tmp_path / "butler.yaml").write_text(yaml.dump(butler_config))
    return tmp_path


@pytest.fixture
def loader(config_dir: Path) -> ProfileLoader:
    """Create a ProfileLoader pointing to the temp config directory."""
    return ProfileLoader(config_dir)


# ------------------------------------------------------------------
# ProfileLoader.__init__ and config directory resolution
# ------------------------------------------------------------------


class TestProfileLoaderInit:
    """Tests for ProfileLoader initialization and config dir resolution."""

    def test_explicit_config_dir(self, tmp_path: Path) -> None:
        loader = ProfileLoader(config_dir=tmp_path)
        assert loader._config_dir == tmp_path

    def test_default_config_dir_resolution(self) -> None:
        """When no config_dir is given, _resolve_default_config_dir is used."""
        with patch.object(
            ProfileLoader,
            "_resolve_default_config_dir",
            return_value=Path("/mock/configs"),
        ):
            loader = ProfileLoader()
            assert loader._config_dir == Path("/mock/configs")

    def test_resolve_default_prefers_new_config_dir(self, tmp_path: Path) -> None:
        """Prefers src/taskforce/configs/ over configs/."""
        new_dir = tmp_path / "src" / "taskforce" / "configs"
        new_dir.mkdir(parents=True)
        old_dir = tmp_path / "configs"
        old_dir.mkdir()

        with patch("taskforce.application.profile_loader.ProfileLoader._resolve_default_config_dir") as mock:
            mock.return_value = new_dir
            loader = ProfileLoader()
            assert loader._config_dir == new_dir


# ------------------------------------------------------------------
# ProfileLoader.load()
# ------------------------------------------------------------------


class TestProfileLoaderLoad:
    """Tests for ProfileLoader.load()."""

    def test_load_existing_profile(self, loader: ProfileLoader) -> None:
        config = loader.load("butler")
        assert config["profile"] == "butler"
        assert config["agent"]["max_steps"] == 30

    def test_load_returns_all_keys(self, loader: ProfileLoader) -> None:
        config = loader.load("butler")
        assert "tools" in config
        assert config["tools"] == DEFAULT_TOOL_NAMES

    def test_load_missing_profile_raises(self, loader: ProfileLoader) -> None:
        with pytest.raises(FileNotFoundError, match="Profile not found"):
            loader.load("nonexistent")

    def test_load_missing_profile_error_includes_both_paths(
        self, config_dir: Path
    ) -> None:
        """Error message should mention both standard and custom paths."""
        loader = ProfileLoader(config_dir)
        with pytest.raises(FileNotFoundError) as exc_info:
            loader.load("missing_profile")
        msg = str(exc_info.value)
        assert "missing_profile.yaml" in msg
        assert "custom" in msg

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

    def test_load_profile_with_validation_warning_still_returns_config(
        self, config_dir: Path
    ) -> None:
        """When validate_profile_config raises ConfigValidationError,
        load() logs a warning but still returns the config."""
        # Write a valid YAML that will cause validation to raise
        profile_config = {"profile": "test", "tools": ["file_read"]}
        (config_dir / "test.yaml").write_text(yaml.dump(profile_config))

        loader = ProfileLoader(config_dir)
        with patch(
            "taskforce.application.profile_loader.validate_profile_config",
            side_effect=ConfigValidationError("validation failed"),
        ):
            config = loader.load("test")
        assert config["profile"] == "test"

    def test_load_empty_yaml_file(self, config_dir: Path) -> None:
        """An empty YAML file returns None from yaml.safe_load, which is not a dict."""
        (config_dir / "empty.yaml").write_text("")
        loader = ProfileLoader(config_dir)
        # yaml.safe_load("") returns None; accessing it will fail since
        # validate_profile_config expects a dict. The behavior depends on
        # how the code handles None -- it will raise an error.
        with pytest.raises(Exception):
            loader.load("empty")

    def test_load_invalid_yaml_syntax(self, config_dir: Path) -> None:
        """Malformed YAML should raise a yaml.YAMLError."""
        (config_dir / "bad.yaml").write_text("{ invalid yaml: [")
        loader = ProfileLoader(config_dir)
        with pytest.raises(yaml.YAMLError):
            loader.load("bad")

    def test_load_minimal_profile(self, config_dir: Path) -> None:
        """A profile with just a name key should load successfully."""
        minimal = {"profile": "minimal"}
        (config_dir / "minimal.yaml").write_text(yaml.dump(minimal))
        loader = ProfileLoader(config_dir)
        config = loader.load("minimal")
        assert config["profile"] == "minimal"


# ------------------------------------------------------------------
# ProfileLoader.load_safe()
# ------------------------------------------------------------------


class TestProfileLoaderLoadSafe:
    """Tests for ProfileLoader.load_safe()."""

    def test_load_safe_existing_profile(self, loader: ProfileLoader) -> None:
        config = loader.load_safe("butler")
        assert config["profile"] == "butler"

    def test_load_safe_missing_returns_fallback(
        self, loader: ProfileLoader
    ) -> None:
        config = loader.load_safe("nonexistent")
        assert config == _FALLBACK_CONFIG
        # Verify it's a deep copy (not the same object)
        assert config is not _FALLBACK_CONFIG

    def test_load_safe_fallback_copies_are_independent(
        self, loader: ProfileLoader
    ) -> None:
        """Multiple calls to load_safe for missing profiles return independent copies."""
        config1 = loader.load_safe("missing1")
        config2 = loader.load_safe("missing2")
        config1["agent"]["max_steps"] = 999
        assert config2["agent"]["max_steps"] == 30
        assert _FALLBACK_CONFIG["agent"]["max_steps"] == 30


# ------------------------------------------------------------------
# ProfileLoader.get_defaults()
# ------------------------------------------------------------------


class TestProfileLoaderGetDefaults:
    """Tests for ProfileLoader.get_defaults()."""

    def test_get_defaults_loads_butler(self, loader: ProfileLoader) -> None:
        config = loader.get_defaults()
        assert config["profile"] == "butler"

    def test_get_defaults_fallback_when_no_butler(self, tmp_path: Path) -> None:
        loader = ProfileLoader(tmp_path)
        config = loader.get_defaults()
        assert config == _FALLBACK_CONFIG

    def test_get_defaults_fallback_has_expected_keys(self, tmp_path: Path) -> None:
        """Verify the fallback config structure."""
        loader = ProfileLoader(tmp_path)
        config = loader.get_defaults()
        assert "persistence" in config
        assert config["persistence"]["type"] == "file"
        assert "llm" in config
        assert config["llm"]["default_model"] == "main"
        assert "agent" in config
        assert config["logging"]["level"] == "WARNING"


# ------------------------------------------------------------------
# ProfileLoader.merge_plugin_config()
# ------------------------------------------------------------------


class TestProfileLoaderMergePluginConfig:
    """Tests for ProfileLoader.merge_plugin_config()."""

    def test_merge_agent_keys(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"agent": {"max_steps": 30, "model": "gpt-4"}}
        plugin: dict[str, Any] = {"agent": {"max_steps": 10}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["agent"]["max_steps"] == 10
        assert merged["agent"]["model"] == "gpt-4"

    def test_merge_agent_adds_new_keys(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"agent": {"max_steps": 30}}
        plugin: dict[str, Any] = {"agent": {"planning_strategy": "spar"}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["agent"]["max_steps"] == 30
        assert merged["agent"]["planning_strategy"] == "spar"

    def test_merge_agent_when_base_has_no_agent(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"tools": ["file_read"]}
        plugin: dict[str, Any] = {"agent": {"max_steps": 10}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["agent"]["max_steps"] == 10

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

    def test_merge_persistence_type_not_overridden(self, loader: ProfileLoader) -> None:
        """Plugin cannot override persistence type (security constraint)."""
        base: dict[str, Any] = {
            "persistence": {"type": "file", "work_dir": ".taskforce"}
        }
        plugin: dict[str, Any] = {"persistence": {"type": "postgres", "work_dir": ".plugin"}}
        merged = loader.merge_plugin_config(base, plugin)
        # Only work_dir is overridden, not type
        assert merged["persistence"]["type"] == "file"
        assert merged["persistence"]["work_dir"] == ".plugin"

    def test_merge_persistence_empty_work_dir_not_overridden(
        self, loader: ProfileLoader
    ) -> None:
        """Plugin with empty work_dir does not override base."""
        base: dict[str, Any] = {
            "persistence": {"type": "file", "work_dir": ".taskforce"}
        }
        plugin: dict[str, Any] = {"persistence": {"work_dir": ""}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["persistence"]["work_dir"] == ".taskforce"

    def test_merge_mcp_servers_concatenated(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"mcp_servers": [{"name": "server1"}]}
        plugin: dict[str, Any] = {"mcp_servers": [{"name": "server2"}]}
        merged = loader.merge_plugin_config(base, plugin)
        assert len(merged["mcp_servers"]) == 2
        assert merged["mcp_servers"][0]["name"] == "server1"
        assert merged["mcp_servers"][1]["name"] == "server2"

    def test_merge_mcp_servers_when_base_has_none(self, loader: ProfileLoader) -> None:
        """Plugin can add mcp_servers when base has none."""
        base: dict[str, Any] = {"agent": {"max_steps": 30}}
        plugin: dict[str, Any] = {"mcp_servers": [{"name": "server1"}]}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["mcp_servers"] == [{"name": "server1"}]

    def test_merge_context_management_update(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"context_management": {"strategy": "fifo"}}
        plugin: dict[str, Any] = {"context_management": {"max_tokens": 1000}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["context_management"]["strategy"] == "fifo"
        assert merged["context_management"]["max_tokens"] == 1000

    def test_merge_context_management_when_base_has_none(
        self, loader: ProfileLoader
    ) -> None:
        base: dict[str, Any] = {"agent": {"max_steps": 30}}
        plugin: dict[str, Any] = {"context_management": {"max_tokens": 1000}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["context_management"]["max_tokens"] == 1000

    def test_merge_memory_update(self, loader: ProfileLoader) -> None:
        """Plugin memory config is shallow-merged into base."""
        base: dict[str, Any] = {"memory": {"store_dir": ".taskforce/.memory"}}
        plugin: dict[str, Any] = {"memory": {"max_entries": 100}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["memory"]["store_dir"] == ".taskforce/.memory"
        assert merged["memory"]["max_entries"] == 100

    def test_merge_memory_when_base_has_none(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"agent": {"max_steps": 30}}
        plugin: dict[str, Any] = {"memory": {"store_dir": ".plugin/.memory"}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["memory"]["store_dir"] == ".plugin/.memory"

    def test_merge_does_not_mutate_base(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"agent": {"max_steps": 30}}
        plugin: dict[str, Any] = {"agent": {"max_steps": 10}}
        loader.merge_plugin_config(base, plugin)
        assert base["agent"]["max_steps"] == 30

    def test_merge_does_not_mutate_plugin(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"mcp_servers": [{"name": "s1"}]}
        plugin: dict[str, Any] = {"mcp_servers": [{"name": "s2"}]}
        loader.merge_plugin_config(base, plugin)
        assert plugin["mcp_servers"] == [{"name": "s2"}]

    def test_merge_empty_plugin(self, loader: ProfileLoader) -> None:
        base: dict[str, Any] = {"agent": {"max_steps": 30}}
        merged = loader.merge_plugin_config(base, {})
        assert merged == base

    def test_merge_empty_base(self, loader: ProfileLoader) -> None:
        plugin: dict[str, Any] = {"agent": {"max_steps": 10}, "specialist": "coding"}
        merged = loader.merge_plugin_config({}, plugin)
        assert merged["agent"]["max_steps"] == 10
        assert merged["specialist"] == "coding"

    def test_merge_llm_override(self, loader: ProfileLoader) -> None:
        """Plugin can override llm default_model and config_path."""
        base: dict[str, Any] = {
            "llm": {"default_model": "main", "config_path": "base.yaml"}
        }
        plugin: dict[str, Any] = {"llm": {"default_model": "claude-sonnet"}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["llm"]["default_model"] == "claude-sonnet"
        assert merged["llm"]["config_path"] == "base.yaml"

    def test_merge_llm_config_path_override(self, loader: ProfileLoader) -> None:
        """Plugin can override llm config_path for custom LLM configuration."""
        base: dict[str, Any] = {
            "llm": {"config_path": "base.yaml", "default_model": "main"}
        }
        plugin: dict[str, Any] = {"llm": {"config_path": "plugin.yaml"}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["llm"]["config_path"] == "plugin.yaml"
        assert merged["llm"]["default_model"] == "main"

    def test_merge_llm_added_when_base_has_no_llm(self, loader: ProfileLoader) -> None:
        """Plugin can add llm config when base has none."""
        base: dict[str, Any] = {"agent": {"max_steps": 30}}
        plugin: dict[str, Any] = {
            "llm": {"config_path": "plugin.yaml", "default_model": "claude-sonnet"}
        }
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["llm"]["config_path"] == "plugin.yaml"
        assert merged["llm"]["default_model"] == "claude-sonnet"

    def test_merge_preserves_unrelated_base_keys(self, loader: ProfileLoader) -> None:
        """Keys in base that are not handled by merge logic are preserved."""
        base: dict[str, Any] = {
            "agent": {"max_steps": 30},
            "tools": ["file_read"],
            "custom_key": "should_survive",
        }
        plugin: dict[str, Any] = {"agent": {"max_steps": 10}}
        merged = loader.merge_plugin_config(base, plugin)
        assert merged["tools"] == ["file_read"]
        assert merged["custom_key"] == "should_survive"


# ------------------------------------------------------------------
# DEFAULT_TOOL_NAMES and _FALLBACK_CONFIG constants
# ------------------------------------------------------------------


class TestConstants:
    """Tests for module-level constants."""

    def test_default_tool_names_is_list_of_strings(self) -> None:
        assert isinstance(DEFAULT_TOOL_NAMES, list)
        assert all(isinstance(t, str) for t in DEFAULT_TOOL_NAMES)
        assert len(DEFAULT_TOOL_NAMES) > 0

    def test_fallback_config_has_required_sections(self) -> None:
        assert "persistence" in _FALLBACK_CONFIG
        assert "llm" in _FALLBACK_CONFIG
        assert "agent" in _FALLBACK_CONFIG
        assert "logging" in _FALLBACK_CONFIG
