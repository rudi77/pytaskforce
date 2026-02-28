"""Tests for SpecialistDiscovery service."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.application.specialist_discovery import (
    SpecialistDiscovery,
    SpecialistInfo,
)


@pytest.fixture()
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with custom agents."""
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()

    # Agent with description field
    (custom_dir / "web-agent.yaml").write_text(
        "agent_id: web-agent\n"
        "name: WebAgent\n"
        "description: Search and scrape websites\n"
        "tools:\n"
        "  - web_search\n"
    )

    # Agent with comment-only description
    (custom_dir / "coding_worker.yaml").write_text(
        "# Coding Worker Agent\n"
        "#\n"
        "# Implementation sub-agent for multi-agent coding workflows.\n"
        "\n"
        "agent:\n"
        "  type: custom\n"
        "  max_steps: 120\n"
    )

    # Agent with minimal header
    (custom_dir / "test_engineer.yaml").write_text(
        "# Test Engineer Agent\n"
        "#\n"
        "# Specialist agent for writing comprehensive tests.\n"
        "\n"
        "agent:\n"
        "  type: custom\n"
    )

    return tmp_path


@pytest.fixture()
def empty_config_dir(tmp_path: Path) -> Path:
    """Config directory without custom/ subdirectory."""
    return tmp_path


class TestSpecialistDiscovery:
    """Tests for SpecialistDiscovery."""

    def test_discover_builtin_specialists(self, empty_config_dir: Path) -> None:
        """Built-in specialists (coding, rag, wiki) are always present."""
        discovery = SpecialistDiscovery(empty_config_dir)
        specialists = discovery.discover()

        names = [s.name for s in specialists]
        assert "coding" in names
        assert "rag" in names
        assert "wiki" in names
        assert all(
            s.source == "builtin" for s in specialists if s.name in ("coding", "rag", "wiki")
        )

    def test_discover_custom_agents(self, config_dir: Path) -> None:
        """Custom agents from configs/custom/ are discovered."""
        discovery = SpecialistDiscovery(config_dir)
        specialists = discovery.discover()

        names = [s.name for s in specialists]
        assert "web-agent" in names
        assert "coding_worker" in names
        assert "test_engineer" in names

    def test_description_from_field(self, config_dir: Path) -> None:
        """Description is extracted from YAML description field."""
        discovery = SpecialistDiscovery(config_dir)
        specialists = discovery.discover()

        web_agent = next(s for s in specialists if s.name == "web-agent")
        assert web_agent.description == "Search and scrape websites"

    def test_description_from_comment(self, config_dir: Path) -> None:
        """Description is extracted from header comment when no field exists."""
        discovery = SpecialistDiscovery(config_dir)
        specialists = discovery.discover()

        worker = next(s for s in specialists if s.name == "coding_worker")
        assert "multi-agent coding workflows" in worker.description

    def test_custom_agents_tagged_as_custom(self, config_dir: Path) -> None:
        """Custom agents have source='custom'."""
        discovery = SpecialistDiscovery(config_dir)
        specialists = discovery.discover()

        custom = [s for s in specialists if s.source == "custom"]
        assert len(custom) == 3

    def test_caching(self, config_dir: Path) -> None:
        """Second call returns cached results without re-scanning."""
        discovery = SpecialistDiscovery(config_dir)
        result1 = discovery.discover()
        result2 = discovery.discover()

        assert result1 is result2  # Same object reference = cached

    def test_format_for_prompt_compact(self, config_dir: Path) -> None:
        """Formatted output is compact and contains all specialist names."""
        discovery = SpecialistDiscovery(config_dir)
        output = discovery.format_for_prompt()

        assert isinstance(output, str)
        assert len(output) < 2000  # Compact output
        assert "`coding`" in output
        assert "`rag`" in output
        assert "`wiki`" in output
        assert "`web-agent`" in output
        assert "`coding_worker`" in output

    def test_format_for_prompt_markdown_list(self, config_dir: Path) -> None:
        """Each specialist is a markdown list item."""
        discovery = SpecialistDiscovery(config_dir)
        output = discovery.format_for_prompt()

        lines = output.strip().splitlines()
        assert all(line.startswith("- ") for line in lines)

    def test_empty_custom_dir(self, empty_config_dir: Path) -> None:
        """Gracefully handles missing custom/ directory."""
        discovery = SpecialistDiscovery(empty_config_dir)
        specialists = discovery.discover()

        # Only built-ins should be present
        assert len(specialists) == 3
        assert all(s.source == "builtin" for s in specialists)

    def test_format_no_specialists(self, tmp_path: Path) -> None:
        """format_for_prompt handles case with only builtins."""
        discovery = SpecialistDiscovery(tmp_path)
        output = discovery.format_for_prompt()

        assert "coding" in output
        assert isinstance(output, str)

    def test_specialist_info_frozen(self) -> None:
        """SpecialistInfo is immutable."""
        info = SpecialistInfo(name="test", description="Test agent", source="custom")
        with pytest.raises(AttributeError):
            info.name = "changed"  # type: ignore[misc]


class TestSpecialistDiscoveryEdgeCases:
    """Edge case tests for SpecialistDiscovery."""

    def test_yaml_without_description_or_comments(self, tmp_path: Path) -> None:
        """YAML with no description field and no comments gets fallback."""
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        (custom_dir / "bare_agent.yaml").write_text(
            "agent:\n" "  type: custom\n" "  max_steps: 10\n"
        )

        discovery = SpecialistDiscovery(tmp_path)
        specialists = discovery.discover()

        bare = next(s for s in specialists if s.name == "bare_agent")
        assert bare.description == "Custom agent: bare_agent"

    def test_quoted_description_field(self, tmp_path: Path) -> None:
        """Quoted description field is properly extracted."""
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        (custom_dir / "quoted.yaml").write_text(
            'description: "A quoted description"\n' "agent:\n" "  type: custom\n"
        )

        discovery = SpecialistDiscovery(tmp_path)
        specialists = discovery.discover()

        quoted = next(s for s in specialists if s.name == "quoted")
        assert quoted.description == "A quoted description"

    def test_single_quote_description_field(self, tmp_path: Path) -> None:
        """Single-quoted description field is properly extracted."""
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        (custom_dir / "single_quoted.yaml").write_text(
            "description: 'Single quoted desc'\n" "agent:\n" "  type: custom\n"
        )

        discovery = SpecialistDiscovery(tmp_path)
        specialists = discovery.discover()

        sq = next(s for s in specialists if s.name == "single_quoted")
        assert sq.description == "Single quoted desc"

    def test_plugin_agents_discovered(self, tmp_path: Path) -> None:
        """Plugin agents from plugins/*/configs/agents/ are discovered."""
        # Create plugin structure: taskforce/plugins/my_plugin/configs/agents/
        taskforce_dir = tmp_path / "taskforce"
        taskforce_dir.mkdir()
        configs_dir = taskforce_dir / "configs"
        configs_dir.mkdir()

        plugin_agents_dir = taskforce_dir / "plugins" / "my_plugin" / "configs" / "agents"
        plugin_agents_dir.mkdir(parents=True)
        (plugin_agents_dir / "my_specialist.yaml").write_text(
            "# My Specialist\n"
            "#\n"
            "# Custom plugin specialist for testing.\n"
            "\n"
            "agent:\n"
            "  type: custom\n"
        )

        discovery = SpecialistDiscovery(configs_dir)
        specialists = discovery.discover()

        names = [s.name for s in specialists]
        assert "my_specialist" in names

        plugin_spec = next(s for s in specialists if s.name == "my_specialist")
        assert plugin_spec.source == "plugin"
