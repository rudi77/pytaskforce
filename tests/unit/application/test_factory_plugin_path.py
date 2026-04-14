"""Tests for plugin_path support in AgentFactory config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.application.factory import AgentFactory
from taskforce.core.domain.agent_definition import AgentSource


class TestBuildDefinitionPluginPath:
    """Tests for _build_definition_from_config with plugin_path."""

    def setup_method(self):
        self.factory = AgentFactory()

    def test_config_without_plugin_path_uses_profile_source(self):
        """Config without plugin_path creates a PROFILE-sourced definition."""
        config = {
            "profile": "test_agent",
            "tools": ["file_read", "ask_user"],
        }
        definition = self.factory._build_definition_from_config(
            profile_name="test_agent",
            config=config,
            work_dir=None,
            planning_strategy=None,
            planning_strategy_params=None,
        )
        assert definition.source == AgentSource.PROFILE
        assert definition.plugin_path is None

    def test_config_with_plugin_path_uses_plugin_source(self, tmp_path: Path):
        """Config with plugin_path creates a PLUGIN-sourced definition."""
        config = {
            "profile": "test_agent",
            "plugin_path": str(tmp_path / "my_plugin"),
            "tools": ["file_read", "custom_tool"],
        }
        definition = self.factory._build_definition_from_config(
            profile_name="test_agent",
            config=config,
            work_dir=None,
            planning_strategy=None,
            planning_strategy_params=None,
        )
        assert definition.source == AgentSource.PLUGIN
        assert definition.plugin_path == str((tmp_path / "my_plugin").resolve())

    def test_relative_plugin_path_resolved_against_config_dir(self, tmp_path: Path):
        """Relative plugin_path is resolved against config_dir."""
        config_dir = tmp_path / "configs"
        config_dir.mkdir()

        config = {
            "profile": "test_agent",
            "plugin_path": "..",
            "tools": ["file_read"],
        }
        definition = self.factory._build_definition_from_config(
            profile_name="test_agent",
            config=config,
            work_dir=None,
            planning_strategy=None,
            planning_strategy_params=None,
            config_dir=config_dir,
        )
        assert definition.source == AgentSource.PLUGIN
        assert definition.plugin_path == str(tmp_path.resolve())

    def test_relative_plugin_path_without_config_dir_uses_cwd(self):
        """Relative plugin_path without config_dir resolves against CWD."""
        config = {
            "profile": "test_agent",
            "plugin_path": "examples/my_plugin",
            "tools": ["file_read"],
        }
        definition = self.factory._build_definition_from_config(
            profile_name="test_agent",
            config=config,
            work_dir=None,
            planning_strategy=None,
            planning_strategy_params=None,
        )
        assert definition.source == AgentSource.PLUGIN
        expected = str((Path.cwd() / "examples/my_plugin").resolve())
        assert definition.plugin_path == expected

    def test_absolute_plugin_path_used_as_is(self, tmp_path: Path):
        """Absolute plugin_path is used without modification."""
        abs_path = tmp_path / "my_plugin"
        config = {
            "profile": "test_agent",
            "plugin_path": str(abs_path),
            "tools": ["file_read"],
        }
        definition = self.factory._build_definition_from_config(
            profile_name="test_agent",
            config=config,
            work_dir=None,
            planning_strategy=None,
            planning_strategy_params=None,
            config_dir=tmp_path / "other_dir",  # should be ignored for absolute paths
        )
        assert definition.plugin_path == str(abs_path.resolve())

    def test_other_definition_fields_preserved_with_plugin_path(self, tmp_path: Path):
        """All other definition fields are preserved when plugin_path is set."""
        config = {
            "profile": "test_agent",
            "plugin_path": str(tmp_path),
            "specialist": "coding",
            "system_prompt": "You are a test agent.",
            "tools": ["file_read", "python"],
            "agent": {
                "planning_strategy": "spar",
                "max_steps": 25,
            },
        }
        definition = self.factory._build_definition_from_config(
            profile_name="test_agent",
            config=config,
            work_dir="/tmp/work",
            planning_strategy=None,
            planning_strategy_params=None,
        )
        assert definition.source == AgentSource.PLUGIN
        assert definition.specialist == "coding"
        assert definition.system_prompt == "You are a test agent."
        assert "file_read" in definition.tools
        assert "python" in definition.tools
        assert definition.planning_strategy == "spar"
        assert definition.max_steps == 25
        assert definition.work_dir == "/tmp/work"
