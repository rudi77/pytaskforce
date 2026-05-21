"""Tests for the `taskforce skills` CLI command.

Spec: docs/spec/skills.md — covers the `--type` filter on `skills list`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("typer")

from typer.testing import CliRunner

from taskforce.api.cli.commands import skills as skills_cmd
from taskforce.application.skill_service import SkillService
from taskforce.infrastructure.skills.skill_registry import FileSkillRegistry

runner = CliRunner()


def _write_skill(root: Path, name: str, skill_type: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: A {skill_type} demo skill.\n"
        f"type: {skill_type}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


@pytest.mark.spec("skills.cli_list_filters_by_type")
def test_skills_list_filters_by_type(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`skills list --type prompt` shows only PROMPT skills."""
    _write_skill(tmp_path, "ctx-demo", "context")
    _write_skill(tmp_path, "prompt-demo", "prompt")
    _write_skill(tmp_path, "agent-demo", "agent")

    service = SkillService(
        registry=FileSkillRegistry([str(tmp_path)], auto_discover=True)
    )
    monkeypatch.setattr(skills_cmd, "_get_skill_service", lambda: service)

    result = runner.invoke(skills_cmd.app, ["list", "--type", "prompt"])

    assert result.exit_code == 0
    assert "prompt-demo" in result.output
    # The context and agent skills are filtered out.
    assert "ctx-demo" not in result.output
    assert "agent-demo" not in result.output


@pytest.mark.spec("skills.cli_list_filters_by_type")
def test_skills_list_invalid_type_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unknown `--type` value fails with a non-zero exit code."""
    _write_skill(tmp_path, "ctx-demo", "context")
    service = SkillService(
        registry=FileSkillRegistry([str(tmp_path)], auto_discover=True)
    )
    monkeypatch.setattr(skills_cmd, "_get_skill_service", lambda: service)

    result = runner.invoke(skills_cmd.app, ["list", "--type", "bogus"])

    assert result.exit_code == 1
    assert "Invalid skill type" in result.output
