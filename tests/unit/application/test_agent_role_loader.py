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
