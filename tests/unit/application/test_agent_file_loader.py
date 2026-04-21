"""Tests for the .agent.md loader and preset/extends resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from taskforce.application.agent_file_loader import (
    agent_file_to_config,
    load_agent_md,
)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestLoadAgentMd:
    """Frontmatter + body parsing."""

    def test_parses_frontmatter_and_body(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "foo.agent.md",
            "---\n"
            "id: foo\n"
            "tools: [web_fetch]\n"
            "---\n"
            "\n"
            "# Foo Agent\n"
            "\n"
            "Be helpful.\n",
        )
        af = load_agent_md(path)
        assert af.frontmatter == {"id": "foo", "tools": ["web_fetch"]}
        assert af.body.lstrip().startswith("# Foo Agent")
        assert "Be helpful." in af.body

    def test_missing_frontmatter_raises(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "bad.agent.md", "no frontmatter here\n")
        with pytest.raises(ValueError, match="missing frontmatter"):
            load_agent_md(path)

    def test_unterminated_frontmatter_raises(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "bad.agent.md", "---\nid: foo\n")
        with pytest.raises(ValueError, match="not terminated"):
            load_agent_md(path)

    def test_non_mapping_frontmatter_raises(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "bad.agent.md", "---\n- 1\n- 2\n---\nbody\n")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_agent_md(path)


class TestAgentFileToConfig:
    """Frontmatter → flat config conversion."""

    def test_body_becomes_system_prompt(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "foo.agent.md",
            "---\nid: foo\n---\n\n# Foo\n\nDo things.\n",
        )
        cfg = agent_file_to_config(load_agent_md(path))
        # Body is wrapped with leading/trailing newlines for triple-quote parity.
        assert cfg["system_prompt"].startswith("\n# Foo")
        assert cfg["system_prompt"].endswith("\n")

    def test_inline_system_prompt_wins_over_body(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "foo.agent.md",
            "---\nid: foo\nsystem_prompt: INLINE\n---\n\n# Body\n",
        )
        cfg = agent_file_to_config(load_agent_md(path))
        assert cfg["system_prompt"] == "INLINE"

    def test_technical_block_flattened_onto_top_level(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "foo.agent.md",
            "---\n"
            "id: foo\n"
            "tools: [file_read]\n"
            "technical:\n"
            "  agent:\n"
            "    max_steps: 42\n"
            "  logging:\n"
            "    level: DEBUG\n"
            "---\n"
            "body\n",
        )
        cfg = agent_file_to_config(load_agent_md(path))
        assert cfg["agent"]["max_steps"] == 42
        assert cfg["logging"]["level"] == "DEBUG"
        assert cfg["tools"] == ["file_read"]
        assert "technical" not in cfg

    def test_defaults_applied_first(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "foo.agent.md",
            "---\nid: foo\n---\nbody\n",
        )
        defaults = {"llm": {"default_model": "main"}, "agent": {"max_steps": 30}}
        cfg = agent_file_to_config(load_agent_md(path), defaults=defaults)
        assert cfg["llm"]["default_model"] == "main"
        assert cfg["agent"]["max_steps"] == 30

    def test_frontmatter_overrides_defaults(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "foo.agent.md",
            "---\n" "id: foo\n" "technical:\n" "  agent:\n" "    max_steps: 99\n" "---\nbody\n",
        )
        defaults = {"agent": {"max_steps": 30, "planning_strategy": "x"}}
        cfg = agent_file_to_config(load_agent_md(path), defaults=defaults)
        assert cfg["agent"]["max_steps"] == 99
        # Deep merge preserves the sibling key from defaults.
        assert cfg["agent"]["planning_strategy"] == "x"

    def test_extends_single_preset(self, tmp_path: Path) -> None:
        preset_dir = tmp_path / "presets"
        _write(
            preset_dir / "mybase.yaml",
            yaml.dump({"agent": {"max_steps": 50}, "logging": {"level": "INFO"}}),
        )
        path = _write(
            tmp_path / "foo.agent.md",
            "---\nid: foo\nextends: mybase\n---\nbody\n",
        )
        cfg = agent_file_to_config(load_agent_md(path), preset_dirs=[preset_dir])
        assert cfg["agent"]["max_steps"] == 50
        assert cfg["logging"]["level"] == "INFO"

    def test_extends_list_applies_in_order(self, tmp_path: Path) -> None:
        preset_dir = tmp_path / "presets"
        _write(preset_dir / "a.yaml", yaml.dump({"logging": {"level": "INFO"}}))
        _write(preset_dir / "b.yaml", yaml.dump({"logging": {"level": "DEBUG"}}))
        path = _write(
            tmp_path / "foo.agent.md",
            "---\nid: foo\nextends: [a, b]\n---\nbody\n",
        )
        cfg = agent_file_to_config(load_agent_md(path), preset_dirs=[preset_dir])
        # 'b' came second, so it wins.
        assert cfg["logging"]["level"] == "DEBUG"

    def test_list_concat_for_tools(self, tmp_path: Path) -> None:
        preset_dir = tmp_path / "presets"
        _write(preset_dir / "base.yaml", yaml.dump({"tools": ["memory"]}))
        path = _write(
            tmp_path / "foo.agent.md",
            "---\nid: foo\nextends: base\ntools: [web_fetch]\n---\nbody\n",
        )
        cfg = agent_file_to_config(load_agent_md(path), preset_dirs=[preset_dir])
        assert cfg["tools"] == ["memory", "web_fetch"]

    def test_extends_missing_raises(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "foo.agent.md",
            "---\nid: foo\nextends: nope\n---\nbody\n",
        )
        with pytest.raises(FileNotFoundError, match="Preset 'nope'"):
            agent_file_to_config(load_agent_md(path), preset_dirs=[tmp_path / "presets"])
