"""Tests for ButlerRoleLoader."""

from pathlib import Path

import pytest
import yaml

from taskforce.application.butler_role_loader import ButlerRoleLoader
from taskforce.core.domain.butler_role import ButlerRole


@pytest.fixture
def config_dir(tmp_path):
    """Create a config directory with butler_roles."""
    roles_dir = tmp_path / "configs" / "butler_roles"
    roles_dir.mkdir(parents=True)
    return tmp_path / "configs"


@pytest.fixture
def project_dir(tmp_path):
    """Create a project-local .taskforce directory."""
    proj = tmp_path / "project" / ".taskforce"
    proj.mkdir(parents=True)
    return proj


def _write_role(directory, name: str, data: dict) -> None:
    """Write a role YAML to a directory."""
    roles_dir = directory / "butler_roles"
    roles_dir.mkdir(parents=True, exist_ok=True)
    with open(roles_dir / f"{name}.yaml", "w") as f:
        yaml.dump(data, f)


class TestButlerRoleLoader:
    """Tests for role loading, listing, and merging."""

    def test_load_from_config_dir(self, config_dir, project_dir) -> None:
        _write_role(
            config_dir,
            "accountant",
            {
                "name": "accountant",
                "description": "Accounting assistant",
                "persona_prompt": "You are an accountant.",
                "sub_agents": [{"specialist": "pc-agent", "description": "Docs"}],
                "tools": ["memory", "ask_user"],
            },
        )

        loader = ButlerRoleLoader(config_dir=config_dir, project_dir=project_dir)
        role = loader.load("accountant")

        assert role.name == "accountant"
        assert role.description == "Accounting assistant"
        assert role.persona_prompt == "You are an accountant."
        assert len(role.sub_agents) == 1
        assert len(role.tools) == 2

    def test_load_from_project_dir(self, config_dir, project_dir) -> None:
        _write_role(
            project_dir,
            "custom_role",
            {
                "name": "custom_role",
                "description": "Custom project role",
                "persona_prompt": "You are custom.",
                "tools": ["memory"],
            },
        )

        loader = ButlerRoleLoader(config_dir=config_dir, project_dir=project_dir)
        role = loader.load("custom_role")

        assert role.name == "custom_role"
        assert role.description == "Custom project role"

    def test_load_config_dir_takes_precedence(self, config_dir, project_dir) -> None:
        """Config dir should be searched first."""
        _write_role(
            config_dir,
            "shared",
            {
                "name": "shared",
                "description": "From config dir",
            },
        )
        _write_role(
            project_dir,
            "shared",
            {
                "name": "shared",
                "description": "From project dir",
            },
        )

        loader = ButlerRoleLoader(config_dir=config_dir, project_dir=project_dir)
        role = loader.load("shared")

        assert role.description == "From config dir"

    def test_load_not_found(self, config_dir, project_dir) -> None:
        loader = ButlerRoleLoader(config_dir=config_dir, project_dir=project_dir)

        with pytest.raises(FileNotFoundError, match="nonexistent"):
            loader.load("nonexistent")

    def test_load_infers_name_from_filename(self, config_dir, project_dir) -> None:
        _write_role(
            config_dir,
            "it_support",
            {
                "description": "IT Support",
                "persona_prompt": "Handle IT.",
            },
        )

        loader = ButlerRoleLoader(config_dir=config_dir, project_dir=project_dir)
        role = loader.load("it_support")

        assert role.name == "it_support"

    def test_list_available(self, config_dir, project_dir) -> None:
        _write_role(
            config_dir,
            "accountant",
            {
                "name": "accountant",
                "description": "Accounting",
            },
        )
        _write_role(
            config_dir,
            "it_support",
            {
                "name": "it_support",
                "description": "IT Support",
            },
        )
        _write_role(
            project_dir,
            "custom",
            {
                "name": "custom",
                "description": "Custom",
            },
        )

        loader = ButlerRoleLoader(config_dir=config_dir, project_dir=project_dir)
        roles = loader.list_available()

        names = {r.name for r in roles}
        assert "accountant" in names
        assert "it_support" in names
        assert "custom" in names

    def test_list_available_deduplicates(self, config_dir, project_dir) -> None:
        """Same role name in both dirs should only appear once."""
        _write_role(config_dir, "shared", {"name": "shared", "description": "Config"})
        _write_role(project_dir, "shared", {"name": "shared", "description": "Project"})

        loader = ButlerRoleLoader(config_dir=config_dir, project_dir=project_dir)
        roles = loader.list_available()

        shared_roles = [r for r in roles if r.name == "shared"]
        assert len(shared_roles) == 1

    def test_list_available_empty(self, config_dir, project_dir) -> None:
        loader = ButlerRoleLoader(config_dir=config_dir, project_dir=project_dir)
        roles = loader.list_available()
        assert roles == []


class TestButlerRoleLoaderMerge:
    """Tests for merge_into_config semantics."""

    def _base_config(self) -> dict:
        return {
            "profile": "butler",
            "specialist": "butler",
            "persistence": {"type": "file", "work_dir": ".taskforce"},
            "llm": {"default_model": "main"},
            "sub_agents": [
                {"specialist": "pc-agent", "description": "PC ops"},
                {"specialist": "coding_agent", "description": "Coding"},
            ],
            "tools": ["memory", "gmail", "calendar"],
            "event_sources": [{"type": "webhook"}],
            "rules": [{"name": "base_rule"}],
            "mcp_servers": [{"type": "stdio", "command": "base"}],
            "notifications": {"default_channel": "telegram"},
        }

    def test_merge_replaces_sub_agents(self) -> None:
        role = ButlerRole(
            name="accountant",
            sub_agents=({"specialist": "pc-agent", "description": "Docs"},),
        )

        loader = ButlerRoleLoader(config_dir=Path("/nonexistent"))
        merged = loader.merge_into_config(self._base_config(), role)

        assert len(merged["sub_agents"]) == 1
        assert merged["sub_agents"][0]["specialist"] == "pc-agent"

    def test_merge_replaces_tools(self) -> None:
        role = ButlerRole(
            name="accountant",
            tools=("memory", "ask_user"),
        )

        loader = ButlerRoleLoader(config_dir=Path("/nonexistent"))
        merged = loader.merge_into_config(self._base_config(), role)

        assert merged["tools"] == ["memory", "ask_user"]

    def test_merge_appends_event_sources(self) -> None:
        role = ButlerRole(
            name="accountant",
            event_sources=({"type": "calendar", "poll": 5},),
        )

        loader = ButlerRoleLoader(config_dir=Path("/nonexistent"))
        merged = loader.merge_into_config(self._base_config(), role)

        assert len(merged["event_sources"]) == 2
        assert merged["event_sources"][0]["type"] == "webhook"
        assert merged["event_sources"][1]["type"] == "calendar"

    def test_merge_appends_rules(self) -> None:
        role = ButlerRole(
            name="accountant",
            rules=({"name": "invoice_rule"},),
        )

        loader = ButlerRoleLoader(config_dir=Path("/nonexistent"))
        merged = loader.merge_into_config(self._base_config(), role)

        assert len(merged["rules"]) == 2

    def test_merge_appends_mcp_servers(self) -> None:
        role = ButlerRole(
            name="accountant",
            mcp_servers=({"type": "sse", "url": "http://localhost"},),
        )

        loader = ButlerRoleLoader(config_dir=Path("/nonexistent"))
        merged = loader.merge_into_config(self._base_config(), role)

        assert len(merged["mcp_servers"]) == 2

    def test_merge_sets_system_prompt(self) -> None:
        role = ButlerRole(
            name="accountant",
            persona_prompt="You are an accountant.",
        )

        loader = ButlerRoleLoader(config_dir=Path("/nonexistent"))
        merged = loader.merge_into_config(self._base_config(), role)

        assert merged["system_prompt"] == "You are an accountant."
        assert merged["specialist"] is None

    def test_merge_preserves_infrastructure(self) -> None:
        role = ButlerRole(name="accountant", persona_prompt="Accountant.")

        loader = ButlerRoleLoader(config_dir=Path("/nonexistent"))
        merged = loader.merge_into_config(self._base_config(), role)

        assert merged["persistence"] == {"type": "file", "work_dir": ".taskforce"}
        assert merged["llm"] == {"default_model": "main"}
        assert merged["notifications"] == {"default_channel": "telegram"}
        assert merged["profile"] == "butler"

    def test_merge_stores_role_metadata(self) -> None:
        role = ButlerRole(name="accountant", description="Accounting assistant")

        loader = ButlerRoleLoader(config_dir=Path("/nonexistent"))
        merged = loader.merge_into_config(self._base_config(), role)

        assert merged["_role_name"] == "accountant"
        assert merged["_role_description"] == "Accounting assistant"

    def test_merge_does_not_mutate_original(self) -> None:
        base = self._base_config()
        original_tools = list(base["tools"])

        role = ButlerRole(name="accountant", tools=("memory",))
        loader = ButlerRoleLoader(config_dir=Path("/nonexistent"))
        loader.merge_into_config(base, role)

        assert base["tools"] == original_tools

    def test_merge_empty_role_keeps_base(self) -> None:
        """A role with no overrides should preserve base sub_agents and tools."""
        base = self._base_config()
        role = ButlerRole(name="empty")

        loader = ButlerRoleLoader(config_dir=Path("/nonexistent"))
        merged = loader.merge_into_config(base, role)

        # Empty role doesn't override sub_agents/tools
        assert len(merged["sub_agents"]) == 2
        assert len(merged["tools"]) == 3
        assert merged["specialist"] is None
