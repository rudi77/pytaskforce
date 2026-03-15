"""Tests for the code mutator."""

from pathlib import Path

import pytest

from autooptim.errors import MutationError
from autooptim.models import ExperimentPlan, FileChange, MutatorConfig
from autooptim.mutators.code_mutator import CodeMutator


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a project with source files."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "core.py").write_text("def hello():\n    return 'hello'\n")
    return tmp_path


def _make_mutator(project: Path) -> CodeMutator:
    config = MutatorConfig(
        type="code",
        allowed_paths=["src/"],
        blocked_paths=["tests/", "src/secret/"],
    )
    return CodeMutator(project, config)


def test_apply_code_change(project: Path):
    mutator = _make_mutator(project)
    plan = ExperimentPlan(
        category="code",
        hypothesis="test",
        description="Modify core",
        files=[FileChange(
            path="src/core.py",
            action="modify",
            content="def hello():\n    return 'world'\n",
        )],
    )
    modified = mutator.apply(plan)
    assert "src/core.py" in modified
    assert (project / "src" / "core.py").read_text() == "def hello():\n    return 'world'\n"


def test_reject_blocked_path(project: Path):
    mutator = _make_mutator(project)
    plan = ExperimentPlan(
        category="code",
        hypothesis="test",
        description="Access blocked",
        files=[FileChange(path="tests/test.py", action="modify", content="pass")],
    )
    with pytest.raises(MutationError, match="not allowed"):
        mutator.apply(plan)


def test_reject_syntax_error(project: Path):
    mutator = _make_mutator(project)
    plan = ExperimentPlan(
        category="code",
        hypothesis="test",
        description="Bad syntax",
        files=[FileChange(
            path="src/core.py",
            action="modify",
            content="def broken(\n",
        )],
    )
    with pytest.raises(MutationError, match="Syntax error"):
        mutator.apply(plan)


def test_reject_empty_content(project: Path):
    mutator = _make_mutator(project)
    plan = ExperimentPlan(
        category="code",
        hypothesis="test",
        description="Empty",
        files=[FileChange(path="src/core.py", action="modify", content="   ")],
    )
    with pytest.raises(MutationError, match="Empty content"):
        mutator.apply(plan)


def test_create_new_file(project: Path):
    mutator = _make_mutator(project)
    plan = ExperimentPlan(
        category="code",
        hypothesis="test",
        description="New file",
        files=[FileChange(
            path="src/new_module.py",
            action="create",
            content="x = 42\n",
        )],
    )
    modified = mutator.apply(plan)
    assert "src/new_module.py" in modified
    assert (project / "src" / "new_module.py").read_text() == "x = 42\n"


def test_delete_file(project: Path):
    mutator = _make_mutator(project)
    assert (project / "src" / "core.py").exists()

    plan = ExperimentPlan(
        category="code",
        hypothesis="test",
        description="Delete file",
        files=[FileChange(path="src/core.py", action="delete", content="")],
    )
    modified = mutator.apply(plan)
    assert "src/core.py" in modified
    assert not (project / "src" / "core.py").exists()
