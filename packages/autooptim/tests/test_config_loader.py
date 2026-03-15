"""Tests for the YAML config loader."""

from pathlib import Path

import pytest

from autooptim.config_loader import load_config
from autooptim.errors import ConfigError


def test_load_minimal_config(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""\
name: test
project_root: "."
categories:
  config:
    weight: 1.0
    mutator:
      type: yaml
      allowed_paths: ["config/"]
evaluator:
  type: command
  command: 'echo {"score": 0.5}'
metric:
  scores:
    - name: score
      range: [0.0, 1.0]
  composite:
    quality:
      weight: 1.0
      components:
        score: 1.0
""")
    config = load_config(config_file)
    assert config.name == "test"
    assert "config" in config.categories
    assert config.categories["config"].weight == 1.0
    assert config.categories["config"].mutator.type == "yaml"
    assert config.evaluator.command == 'echo {"score": 0.5}'
    assert len(config.metric.scores) == 1


def test_load_config_with_runner_overrides(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""\
name: test
categories:
  code:
    mutator:
      type: code
      allowed_paths: ["src/"]
      blocked_paths: ["tests/"]
      preflight:
        - "python -m pytest tests/"
evaluator:
  type: script
  script: "print('{}')"
runner:
  max_iterations: 10
  max_cost_usd: 5.0
  tolerance: 0.05
  eval_runs: 3
""")
    config = load_config(config_file)
    assert config.max_iterations == 10
    assert config.max_cost_usd == 5.0
    assert config.tolerance == 0.05
    assert config.eval_runs == 3
    assert config.categories["code"].mutator.blocked_paths == ["tests/"]
    assert len(config.categories["code"].mutator.preflight_commands) == 1


def test_load_config_file_not_found():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/config.yaml")


def test_load_config_invalid_yaml(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("not a dict")
    with pytest.raises(ConfigError, match="must be a YAML dict"):
        load_config(config_file)


def test_load_config_with_proposer(tmp_path: Path):
    system_prompt = tmp_path / "system.md"
    system_prompt.write_text("You are a test assistant.")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""\
name: test
categories:
  refactor:
    mutator:
      type: text
proposer:
  model: "gpt-4"
  temperature: 0.5
  system_prompt_file: "system.md"
""")
    config = load_config(config_file)
    assert config.proposer.model == "gpt-4"
    assert config.proposer.temperature == 0.5
    assert config.proposer.system_prompt_file == str(system_prompt)
