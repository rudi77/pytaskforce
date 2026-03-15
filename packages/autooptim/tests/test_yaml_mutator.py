"""Tests for the YAML mutator."""

from pathlib import Path

import pytest
import yaml

from autooptim.errors import MutationError
from autooptim.models import ExperimentPlan, FileChange, MutatorConfig
from autooptim.mutators.yaml_mutator import YamlMutator


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a project with a config file."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "settings.yaml"
    config_file.write_text(yaml.dump({
        "agent": {"max_steps": 30, "planning_strategy": "native_react"},
        "context_policy": {"max_items": 10},
        "tools": ["file_read", "python"],
    }))
    return tmp_path


def _make_mutator(project: Path, safe_keys: dict | None = None) -> YamlMutator:
    config = MutatorConfig(
        type="yaml",
        allowed_paths=["config/"],
        safe_keys=safe_keys,
    )
    return YamlMutator(project, config)


def test_apply_config_change(project: Path):
    mutator = _make_mutator(project, safe_keys={"agent": ["max_steps"], "tools": None})
    plan = ExperimentPlan(
        category="config",
        hypothesis="test",
        description="Increase max steps",
        files=[FileChange(
            path="config/settings.yaml",
            action="modify",
            content="agent:\n  max_steps: 50",
        )],
    )
    modified = mutator.apply(plan)
    assert modified == ["config/settings.yaml"]

    # Verify the change was applied
    with open(project / "config" / "settings.yaml") as f:
        result = yaml.safe_load(f)
    assert result["agent"]["max_steps"] == 50
    # Unchanged keys preserved
    assert result["agent"]["planning_strategy"] == "native_react"


def test_reject_unsafe_key(project: Path):
    mutator = _make_mutator(project, safe_keys={"agent": ["max_steps"]})
    plan = ExperimentPlan(
        category="config",
        hypothesis="test",
        description="Change unsafe key",
        files=[FileChange(
            path="config/settings.yaml",
            action="modify",
            content="database:\n  host: evil",
        )],
    )
    with pytest.raises(MutationError, match="not in the safe"):
        mutator.apply(plan)


def test_reject_blocked_path(project: Path):
    config = MutatorConfig(
        type="yaml",
        allowed_paths=["config/"],
        blocked_paths=["config/secret/"],
    )
    mutator = YamlMutator(project, config)

    # Create a file in blocked path
    (project / "config" / "secret").mkdir()
    (project / "config" / "secret" / "db.yaml").write_text("key: value")

    plan = ExperimentPlan(
        category="config",
        hypothesis="test",
        description="Access secret",
        files=[FileChange(path="config/secret/db.yaml", action="modify", content="key: new")],
    )
    with pytest.raises(MutationError, match="not allowed"):
        mutator.apply(plan)


def test_no_safe_keys_allows_all(project: Path):
    """When safe_keys is None, any key is allowed."""
    mutator = _make_mutator(project, safe_keys=None)
    plan = ExperimentPlan(
        category="config",
        hypothesis="test",
        description="Any key",
        files=[FileChange(
            path="config/settings.yaml",
            action="modify",
            content="new_section:\n  key: value",
        )],
    )
    modified = mutator.apply(plan)
    assert "config/settings.yaml" in modified
