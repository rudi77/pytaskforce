"""
Unit Tests for SkillService

Tests skill discovery, slash-command resolution, activation/deactivation,
prompt preparation, and singleton management.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from taskforce.application.skill_service import (
    SkillService,
    get_skill_service,
    reset_skill_service,
)
from taskforce.core.domain.enums import SkillType
from taskforce.core.domain.skill import Skill, SkillMetadataModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(
    name: str = "test-skill",
    instructions: str = "Do something.",
    skill_type: SkillType = SkillType.CONTEXT,
    slash_name: str | None = None,
    allowed_tools: str | None = None,
) -> Skill:
    """Create a minimal valid Skill."""
    return Skill(
        name=name,
        description=f"Description of {name}",
        instructions=instructions,
        source_path=f"/tmp/skills/{name}",
        skill_type=skill_type,
        slash_name=slash_name,
        allowed_tools=allowed_tools,
    )


def _make_metadata(
    name: str = "test-skill",
    skill_type: SkillType = SkillType.CONTEXT,
    slash_name: str | None = None,
) -> SkillMetadataModel:
    """Create a minimal valid SkillMetadataModel."""
    return SkillMetadataModel(
        name=name,
        description=f"Description of {name}",
        source_path=f"/tmp/skills/{name}",
        skill_type=skill_type,
        slash_name=slash_name,
    )


def _make_mock_registry(
    skills: list[Skill] | None = None,
    metadata_list: list[SkillMetadataModel] | None = None,
) -> MagicMock:
    """Build a mock FileSkillRegistry."""
    registry = MagicMock()
    skill_map: dict[str, Skill] = {}
    meta_map: dict[str, SkillMetadataModel] = {}
    slash_index: dict[str, str] = {}

    if skills:
        for s in skills:
            skill_map[s.name] = s

    if metadata_list:
        for m in metadata_list:
            meta_map[m.name] = m
            slash_index[m.effective_slash_name] = m.name
    elif skills:
        for s in skills:
            m = s.metadata_model
            meta_map[m.name] = m
            slash_index[m.effective_slash_name] = m.name

    registry.get_skill.side_effect = lambda name: skill_map.get(name)
    registry.list_skills.return_value = sorted(skill_map.keys())
    registry.get_skill_count.return_value = len(skill_map)
    registry.has_skill.side_effect = lambda name: name in skill_map
    registry.get_skill_metadata.side_effect = lambda name: meta_map.get(name)
    registry.get_all_metadata.return_value = sorted(meta_map.values(), key=lambda m: m.name)
    registry.get_skills_for_prompt.return_value = "\n".join(
        f"- {m.name}: {m.description}" for m in meta_map.values()
    )
    registry.get_skill_by_slash_name.side_effect = lambda sn: skill_map.get(
        slash_index.get(sn.lower(), "")
    )
    registry.directories = []

    return registry


def _make_service(
    skills: list[Skill] | None = None,
    metadata_list: list[SkillMetadataModel] | None = None,
) -> SkillService:
    """Create a SkillService with a mocked registry."""
    mock_reg = _make_mock_registry(skills, metadata_list)
    return SkillService(registry=mock_reg)


# ---------------------------------------------------------------------------
# Basic Properties
# ---------------------------------------------------------------------------


class TestSkillServiceBasics:
    """Tests for basic SkillService properties and methods."""

    def test_list_skills(self) -> None:
        """list_skills returns names from the registry."""
        svc = _make_service([_make_skill("alpha"), _make_skill("beta")])
        names = svc.list_skills()
        assert "alpha" in names
        assert "beta" in names

    def test_has_skill_true(self) -> None:
        """has_skill returns True for existing skills."""
        svc = _make_service([_make_skill("exists")])
        assert svc.has_skill("exists") is True

    def test_has_skill_false(self) -> None:
        """has_skill returns False for nonexistent skills."""
        svc = _make_service([_make_skill("exists")])
        assert svc.has_skill("ghost") is False

    def test_get_skill_found(self) -> None:
        """get_skill returns the skill when found."""
        skill = _make_skill("my-skill")
        svc = _make_service([skill])
        result = svc.get_skill("my-skill")
        assert result is not None
        assert result.name == "my-skill"

    def test_get_skill_not_found(self) -> None:
        """get_skill returns None for missing skill."""
        svc = _make_service([])
        assert svc.get_skill("nope") is None

    def test_get_skill_metadata(self) -> None:
        """get_skill_metadata returns metadata for the skill."""
        skill = _make_skill("data-skill")
        svc = _make_service([skill])
        meta = svc.get_skill_metadata("data-skill")
        assert meta is not None
        assert meta.name == "data-skill"

    def test_get_all_metadata(self) -> None:
        """get_all_metadata returns metadata for all skills."""
        svc = _make_service([_make_skill("a"), _make_skill("b")])
        all_meta = svc.get_all_metadata()
        assert len(all_meta) == 2

    def test_registry_property(self) -> None:
        """registry property exposes the underlying registry."""
        svc = _make_service([])
        assert svc.registry is not None

    def test_context_property(self) -> None:
        """context property exposes the SkillContext."""
        svc = _make_service([])
        assert svc.context is not None

    def test_refresh_delegates_to_registry(self) -> None:
        """refresh calls registry.refresh."""
        svc = _make_service([])
        svc.refresh()
        svc.registry.refresh.assert_called_once()


# ---------------------------------------------------------------------------
# Slash-Command Skills
# ---------------------------------------------------------------------------


class TestSlashCommandSkills:
    """Tests for slash-command listing and resolution."""

    def test_list_slash_command_skills_filters_prompt_and_agent(self) -> None:
        """list_slash_command_skills returns only PROMPT and AGENT skills."""
        metadata_list = [
            _make_metadata("ctx-skill", skill_type=SkillType.CONTEXT),
            _make_metadata("prompt-skill", skill_type=SkillType.PROMPT),
            _make_metadata("agent-skill", skill_type=SkillType.AGENT),
        ]
        svc = _make_service(metadata_list=metadata_list)
        slash_skills = svc.list_slash_command_skills()
        names = [s.name for s in slash_skills]
        assert "prompt-skill" in names
        assert "agent-skill" in names
        assert "ctx-skill" not in names

    def test_resolve_slash_command_found(self) -> None:
        """resolve_slash_command returns (skill, args) for valid commands."""
        skill = _make_skill("code-review", skill_type=SkillType.PROMPT)
        svc = _make_service([skill])

        result_skill, args = svc.resolve_slash_command("/code-review def foo(): pass")
        assert result_skill is not None
        assert result_skill.name == "code-review"
        assert args == "def foo(): pass"

    def test_resolve_slash_command_no_args(self) -> None:
        """resolve_slash_command returns empty string for no arguments."""
        skill = _make_skill("helper", skill_type=SkillType.PROMPT)
        svc = _make_service([skill])

        result_skill, args = svc.resolve_slash_command("/helper")
        assert result_skill is not None
        assert args == ""

    def test_resolve_slash_command_not_found(self) -> None:
        """resolve_slash_command returns (None, args) for unknown commands."""
        svc = _make_service([])
        result_skill, args = svc.resolve_slash_command("/nonexistent some args")
        assert result_skill is None

    def test_resolve_slash_command_raises_without_slash(self) -> None:
        """resolve_slash_command raises ValueError if input lacks '/'."""
        svc = _make_service([])
        with pytest.raises(ValueError, match="Expected command starting with"):
            svc.resolve_slash_command("no-slash")


# ---------------------------------------------------------------------------
# Prompt Preparation
# ---------------------------------------------------------------------------


class TestPromptPreparation:
    """Tests for prepare_skill_prompt."""

    def test_prepare_prompt_substitutes_arguments(self) -> None:
        """prepare_skill_prompt replaces $ARGUMENTS in instructions."""
        skill = _make_skill(
            "gen-prompt",
            instructions="Review this code: $ARGUMENTS",
            skill_type=SkillType.PROMPT,
        )
        svc = _make_service([skill])

        result = svc.prepare_skill_prompt(skill, "print('hello')")
        assert result == "Review this code: print('hello')"

    def test_prepare_prompt_raises_for_non_prompt_skill(self) -> None:
        """prepare_skill_prompt raises ValueError for non-PROMPT skills."""
        skill = _make_skill("ctx", skill_type=SkillType.CONTEXT)
        svc = _make_service([skill])

        with pytest.raises(ValueError, match="not of type PROMPT"):
            svc.prepare_skill_prompt(skill, "args")

    def test_prepare_prompt_no_arguments_placeholder(self) -> None:
        """Instructions without $ARGUMENTS are returned unchanged."""
        skill = _make_skill(
            "static",
            instructions="Just do this.",
            skill_type=SkillType.PROMPT,
        )
        svc = _make_service([skill])

        result = svc.prepare_skill_prompt(skill, "ignored")
        assert result == "Just do this."


# ---------------------------------------------------------------------------
# Skill Activation and Deactivation
# ---------------------------------------------------------------------------


class TestSkillActivation:
    """Tests for skill activation/deactivation lifecycle."""

    def test_activate_skill_success(self) -> None:
        """Activating a known skill returns True."""
        skill = _make_skill("my-skill")
        svc = _make_service([skill])

        assert svc.activate_skill("my-skill") is True
        assert svc.is_skill_active("my-skill") is True

    def test_activate_skill_not_found(self) -> None:
        """Activating an unknown skill returns False."""
        svc = _make_service([])
        assert svc.activate_skill("ghost") is False

    def test_deactivate_skill(self) -> None:
        """Deactivating a skill removes it from active context."""
        skill = _make_skill("my-skill")
        svc = _make_service([skill])
        svc.activate_skill("my-skill")

        svc.deactivate_skill("my-skill")
        assert svc.is_skill_active("my-skill") is False

    def test_get_active_skills(self) -> None:
        """get_active_skills returns all activated skills."""
        s1 = _make_skill("alpha")
        s2 = _make_skill("beta")
        svc = _make_service([s1, s2])
        svc.activate_skill("alpha")
        svc.activate_skill("beta")

        active = svc.get_active_skills()
        names = [s.name for s in active]
        assert "alpha" in names
        assert "beta" in names

    def test_clear_active_skills(self) -> None:
        """clear_active_skills deactivates all skills."""
        skill = _make_skill("active")
        svc = _make_service([skill])
        svc.activate_skill("active")

        svc.clear_active_skills()
        assert svc.get_active_skills() == []

    def test_get_combined_instructions(self) -> None:
        """get_combined_instructions returns merged text from active skills."""
        skill = _make_skill("helper", instructions="Help the user.")
        svc = _make_service([skill])
        svc.activate_skill("helper")

        instructions = svc.get_combined_instructions()
        assert "Help the user." in instructions

    def test_get_combined_instructions_empty_when_none_active(self) -> None:
        """get_combined_instructions returns empty string when nothing active."""
        svc = _make_service([])
        assert svc.get_combined_instructions() == ""


# ---------------------------------------------------------------------------
# Prompt Sections
# ---------------------------------------------------------------------------


class TestPromptSections:
    """Tests for system prompt generation."""

    def test_get_skill_prompt_section(self) -> None:
        """get_skill_prompt_section delegates to registry.get_skills_for_prompt."""
        svc = _make_service([_make_skill("alpha")])
        section = svc.get_skill_prompt_section()
        assert "alpha" in section

    def test_get_active_skills_prompt_section_with_skills(self) -> None:
        """Returns formatted section for active skills."""
        skill = _make_skill("coder", instructions="Write code.")
        svc = _make_service([skill])
        svc.activate_skill("coder")

        section = svc.get_active_skills_prompt_section()
        assert "# Active Skills" in section
        assert "## coder" in section
        assert "Write code." in section

    def test_get_active_skills_prompt_section_empty(self) -> None:
        """Returns empty string when no skills are active."""
        svc = _make_service([])
        assert svc.get_active_skills_prompt_section() == ""


# ---------------------------------------------------------------------------
# Skills Summary
# ---------------------------------------------------------------------------


class TestSkillsSummary:
    """Tests for get_skills_summary."""

    def test_summary_structure(self) -> None:
        """Summary contains expected keys and counts."""
        ctx = _make_skill("ctx-skill", skill_type=SkillType.CONTEXT)
        prompt = _make_skill("prompt-skill", skill_type=SkillType.PROMPT)
        agent = _make_skill("agent-skill", skill_type=SkillType.AGENT)
        svc = _make_service([ctx, prompt, agent])
        svc.activate_skill("ctx-skill")

        summary = svc.get_skills_summary()
        assert summary["total_skills"] == 3
        assert summary["context_skills"] == 1
        assert summary["prompt_skills"] == 1
        assert summary["agent_skills"] == 1
        assert "ctx-skill" in summary["active_skills"]
        assert "directories" in summary


# ---------------------------------------------------------------------------
# Resource Reading
# ---------------------------------------------------------------------------


class TestResourceReading:
    """Tests for read_skill_resource."""

    def test_read_resource_from_active_skill(self) -> None:
        """Delegates to context.read_skill_resource for active skill."""
        skill = _make_skill("my-skill")
        svc = _make_service([skill])
        svc.activate_skill("my-skill")

        # The real SkillContext.read_skill_resource uses skill.read_resource
        # which hits the filesystem. With our test skill, source_path doesn't
        # exist, so it returns None.
        result = svc.read_skill_resource("my-skill", "config.yaml")
        assert result is None  # No real filesystem

    def test_read_resource_from_inactive_skill(self) -> None:
        """Returns None when skill is not active."""
        svc = _make_service([_make_skill("inactive")])
        result = svc.read_skill_resource("inactive", "config.yaml")
        assert result is None


# ---------------------------------------------------------------------------
# Singleton Management
# ---------------------------------------------------------------------------


class TestSingleton:
    """Tests for get_skill_service and reset_skill_service."""

    def test_get_skill_service_returns_same_instance(self) -> None:
        """get_skill_service returns the same instance on repeated calls."""
        reset_skill_service()
        with patch(
            "taskforce.application.skill_service.create_skill_registry"
        ) as mock_create:
            mock_create.return_value = _make_mock_registry()
            svc1 = get_skill_service()
            svc2 = get_skill_service()
        assert svc1 is svc2

    def test_reset_skill_service_clears_singleton(self) -> None:
        """reset_skill_service causes get_skill_service to create new instance."""
        reset_skill_service()
        with patch(
            "taskforce.application.skill_service.create_skill_registry"
        ) as mock_create:
            mock_create.return_value = _make_mock_registry()
            svc1 = get_skill_service()
            reset_skill_service()
            svc2 = get_skill_service()
        assert svc1 is not svc2

    def teardown_method(self) -> None:
        """Clean up singleton state after each test."""
        reset_skill_service()
