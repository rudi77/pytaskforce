"""Regression tests for FileAgentRegistry extra-dir + .agent.md discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.infrastructure.persistence.file_agent_registry import FileAgentRegistry


@pytest.fixture
def configs_dir(tmp_path: Path) -> Path:
    target = tmp_path / "configs"
    target.mkdir()
    (target / "default.yaml").write_text(
        "specialist: default\ntools:\n  - python\n",
        encoding="utf-8",
    )
    return target


@pytest.fixture
def extra_dir(tmp_path: Path) -> Path:
    target = tmp_path / "agents" / "butler" / "configs"
    target.mkdir(parents=True)
    # Butler ships ``butler.agent.md``: YAML frontmatter + markdown body.
    (target / "butler.agent.md").write_text(
        "---\n"
        "specialist: butler\n"
        "tools:\n"
        "  - calendar\n"
        "  - schedule\n"
        "---\n"
        "\n"
        "You are butler.\n",
        encoding="utf-8",
    )
    # And a coding_agent.yaml to cover both legacy + new formats.
    coding = tmp_path / "agents" / "coding-agent" / "configs"
    coding.mkdir(parents=True)
    (coding / "coding_agent.yaml").write_text(
        "specialist: coder\ntools:\n  - python\n",
        encoding="utf-8",
    )
    return target


def test_list_agents_picks_up_agent_md_from_extra_dirs(
    configs_dir: Path, extra_dir: Path, tmp_path: Path
) -> None:
    coding_dir = tmp_path / "agents" / "coding-agent" / "configs"
    registry = FileAgentRegistry(
        configs_dir=str(configs_dir),
        extra_dirs_provider=lambda: [extra_dir, coding_dir],
    )
    profiles = {a.profile for a in registry.list_agents() if hasattr(a, "profile")}
    assert "default" in profiles
    assert "butler" in profiles
    assert "coding_agent" in profiles


def test_get_agent_resolves_butler_from_extra_dir(
    configs_dir: Path, extra_dir: Path
) -> None:
    registry = FileAgentRegistry(
        configs_dir=str(configs_dir),
        extra_dirs_provider=lambda: [extra_dir],
    )
    butler = registry.get_agent("butler")
    assert butler is not None
    assert getattr(butler, "profile", None) == "butler"
    assert butler.specialist == "butler"


def test_extra_dirs_dont_shadow_main_configs(
    configs_dir: Path, tmp_path: Path
) -> None:
    """If a profile exists in both, the main configs/*.yaml wins."""
    extra = tmp_path / "extras"
    extra.mkdir()
    (extra / "default.yaml").write_text(
        "specialist: hijacked\ntools: []\n", encoding="utf-8"
    )
    registry = FileAgentRegistry(
        configs_dir=str(configs_dir),
        extra_dirs_provider=lambda: [extra],
    )
    default = registry.get_agent("default")
    assert default is not None
    assert default.specialist == "default"  # not hijacked


def test_no_extra_dirs_provider_is_safe(configs_dir: Path) -> None:
    """Default behaviour (no provider) keeps the legacy code-path intact."""
    registry = FileAgentRegistry(configs_dir=str(configs_dir))
    profiles = {a.profile for a in registry.list_agents() if hasattr(a, "profile")}
    assert "default" in profiles
    assert "butler" not in profiles
