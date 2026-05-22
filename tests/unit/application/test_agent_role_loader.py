"""Dual-format tests for ``AgentRoleLoader``.

The loader must support both the legacy ``{role}.yaml`` format (with a top-level
``persona_prompt:`` key) and the new ``{role}.agent.md`` format (markdown body +
YAML frontmatter), and must prefer the ``.agent.md`` variant when both exist.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from taskforce.application.agent_role_loader import AgentRoleLoader


def test_loads_yaml_role(tmp_path: Path) -> None:
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    (roles_dir / "tester.yaml").write_text(
        yaml.dump(
            {
                "name": "tester",
                "description": "Test role",
                "persona_prompt": "You are a tester.",
                "tools": ["memory"],
            }
        ),
        encoding="utf-8",
    )
    loader = AgentRoleLoader(search_dirs=[roles_dir])
    role = loader.load("tester")
    assert role.name == "tester"
    assert "You are a tester" in role.persona_prompt
    assert role.tools == ("memory",)


def test_loads_agent_md_role(tmp_path: Path) -> None:
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    (roles_dir / "tester.agent.md").write_text(
        "---\n"
        "name: tester\n"
        "description: Test role\n"
        "tools: [memory]\n"
        "---\n"
        "\n"
        "# Tester\n"
        "\n"
        "You are a tester.\n",
        encoding="utf-8",
    )
    loader = AgentRoleLoader(search_dirs=[roles_dir])
    role = loader.load("tester")
    assert role.name == "tester"
    assert "# Tester" in role.persona_prompt
    assert "You are a tester" in role.persona_prompt
    assert role.tools == ("memory",)


def test_agent_md_takes_precedence_over_yaml(tmp_path: Path) -> None:
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    (roles_dir / "tester.yaml").write_text(
        yaml.dump({"name": "tester", "persona_prompt": "OLD"}),
        encoding="utf-8",
    )
    (roles_dir / "tester.agent.md").write_text(
        "---\nname: tester\n---\nNEW\n",
        encoding="utf-8",
    )
    loader = AgentRoleLoader(search_dirs=[roles_dir])
    role = loader.load("tester")
    assert "NEW" in role.persona_prompt
    assert "OLD" not in role.persona_prompt


def test_missing_role_raises(tmp_path: Path) -> None:
    loader = AgentRoleLoader(search_dirs=[tmp_path])
    with pytest.raises(FileNotFoundError, match="nope"):
        loader.load("nope")


def test_list_available_lists_both_formats(tmp_path: Path) -> None:
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    (roles_dir / "yaml_role.yaml").write_text(
        yaml.dump({"name": "yaml_role", "persona_prompt": "yaml"}),
        encoding="utf-8",
    )
    (roles_dir / "md_role.agent.md").write_text(
        "---\nname: md_role\n---\nmd\n",
        encoding="utf-8",
    )
    loader = AgentRoleLoader(search_dirs=[roles_dir])
    names = {r.name for r in loader.list_available()}
    assert names == {"yaml_role", "md_role"}


def test_first_match_wins_across_search_dirs(tmp_path: Path) -> None:
    """Project-local overrides should win over package-shipped defaults."""
    pkg_dir = tmp_path / "package"
    pkg_dir.mkdir()
    proj_dir = tmp_path / "project"
    proj_dir.mkdir()

    (pkg_dir / "tester.yaml").write_text(
        yaml.dump({"name": "tester", "persona_prompt": "package"}),
        encoding="utf-8",
    )
    (proj_dir / "tester.yaml").write_text(
        yaml.dump({"name": "tester", "persona_prompt": "project"}),
        encoding="utf-8",
    )

    # project-local listed first in search_dirs → wins.
    loader = AgentRoleLoader(search_dirs=[proj_dir, pkg_dir])
    role = loader.load("tester")
    assert "project" in role.persona_prompt


@pytest.mark.spec("agent-daemon.role_overlay_replaces_tools_and_sub_agents")
def test_merge_replaces_tools_and_sub_agents(tmp_path: Path) -> None:
    """A role overlay replaces the base profile's tools and sub_agents
    wholesale; infrastructure keys stay from the base."""
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    (roles_dir / "specialist.yaml").write_text(
        yaml.dump(
            {
                "name": "specialist",
                "persona_prompt": "Role persona.",
                "tools": ["memory", "wiki"],
                "sub_agents": [{"specialist": "role_sub"}],
            }
        ),
        encoding="utf-8",
    )
    loader = AgentRoleLoader(search_dirs=[roles_dir])
    role = loader.load("specialist")

    base = {
        "tools": ["python", "shell", "git"],
        "sub_agents": [{"specialist": "base_sub"}],
        "persistence": {"type": "file"},
        "llm": {"default_model": "main"},
    }
    merged = loader.merge_into_config(base, role)

    assert merged["tools"] == ["memory", "wiki"]
    assert merged["sub_agents"] == [{"specialist": "role_sub"}]
    assert merged["system_prompt"] == "Role persona."
    # Infrastructure keys are untouched.
    assert merged["persistence"] == {"type": "file"}
    assert merged["llm"] == {"default_model": "main"}


@pytest.mark.spec("agent-daemon.role_overlay_appends_event_sources_and_rules")
def test_merge_appends_event_sources_and_rules(tmp_path: Path) -> None:
    """A role overlay appends its event_sources and rules to the base set."""
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    (roles_dir / "watcher.yaml").write_text(
        yaml.dump(
            {
                "name": "watcher",
                "persona_prompt": "p",
                "event_sources": [{"type": "calendar"}],
                "rules": [{"name": "role_rule"}],
            }
        ),
        encoding="utf-8",
    )
    loader = AgentRoleLoader(search_dirs=[roles_dir])
    role = loader.load("watcher")

    base = {
        "event_sources": [{"type": "webhook"}],
        "rules": [{"name": "base_rule"}],
    }
    merged = loader.merge_into_config(base, role)

    assert merged["event_sources"] == [{"type": "webhook"}, {"type": "calendar"}]
    assert [r["name"] for r in merged["rules"]] == ["base_rule", "role_rule"]
