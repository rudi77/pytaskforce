"""Dual-format tests for ``ButlerRoleLoader``.

The loader must support both the legacy ``{role}.yaml`` format (with a top-level
``persona_prompt:`` key) and the new ``{role}.agent.md`` format (markdown body +
YAML frontmatter), and must prefer the ``.agent.md`` variant when both exist.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# The butler package lives under agents/butler/src/taskforce_butler. Make sure
# we can import it even when the package isn't installed into the venv.
_BUTLER_SRC = Path(__file__).resolve().parents[3] / "agents" / "butler" / "src"
if _BUTLER_SRC.is_dir() and str(_BUTLER_SRC) not in sys.path:
    sys.path.insert(0, str(_BUTLER_SRC))

try:
    from taskforce_butler.role_loader import ButlerRoleLoader  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover
    pytest.skip(f"taskforce_butler not importable: {exc}", allow_module_level=True)


def test_loads_yaml_role(tmp_path: Path) -> None:
    roles_dir = tmp_path / "butler_roles"
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
    loader = ButlerRoleLoader(config_dir=tmp_path, project_dir=tmp_path)
    role = loader.load("tester")
    assert role.name == "tester"
    assert "You are a tester" in role.persona_prompt
    assert role.tools == ("memory",)


def test_loads_agent_md_role(tmp_path: Path) -> None:
    roles_dir = tmp_path / "butler_roles"
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
    loader = ButlerRoleLoader(config_dir=tmp_path, project_dir=tmp_path)
    role = loader.load("tester")
    assert role.name == "tester"
    assert "# Tester" in role.persona_prompt
    assert "You are a tester" in role.persona_prompt
    assert role.tools == ("memory",)


def test_agent_md_takes_precedence_over_yaml(tmp_path: Path) -> None:
    roles_dir = tmp_path / "butler_roles"
    roles_dir.mkdir()
    (roles_dir / "tester.yaml").write_text(
        yaml.dump({"name": "tester", "persona_prompt": "OLD"}),
        encoding="utf-8",
    )
    (roles_dir / "tester.agent.md").write_text(
        "---\nname: tester\n---\nNEW\n",
        encoding="utf-8",
    )
    loader = ButlerRoleLoader(config_dir=tmp_path, project_dir=tmp_path)
    role = loader.load("tester")
    assert "NEW" in role.persona_prompt
    assert "OLD" not in role.persona_prompt


def test_missing_role_raises(tmp_path: Path) -> None:
    loader = ButlerRoleLoader(config_dir=tmp_path, project_dir=tmp_path)
    with pytest.raises(FileNotFoundError, match="nope"):
        loader.load("nope")


def test_list_available_lists_both_formats(tmp_path: Path) -> None:
    roles_dir = tmp_path / "butler_roles"
    roles_dir.mkdir()
    (roles_dir / "yaml_role.yaml").write_text(
        yaml.dump({"name": "yaml_role", "persona_prompt": "yaml"}),
        encoding="utf-8",
    )
    (roles_dir / "md_role.agent.md").write_text(
        "---\nname: md_role\n---\nmd\n",
        encoding="utf-8",
    )
    loader = ButlerRoleLoader(config_dir=tmp_path, project_dir=tmp_path)
    names = {r.name for r in loader.list_available()}
    # Names from files in agents/butler/configs/roles are also discovered via
    # the package location, so we only assert the tmp-path additions are present.
    assert "yaml_role" in names
    assert "md_role" in names
