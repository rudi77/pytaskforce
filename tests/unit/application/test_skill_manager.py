"""
Unit Tests for SkillManager

Tests skill lifecycle management including:
- Initialization with and without skill directories
- Skill activation, deactivation, and switching
- Intent-based activation
- Prompt enhancement
- Context data transfer
- Switch condition evaluation
- Allowed tools retrieval
- Reset and summary
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from taskforce.application.skill_manager import (
    SkillConfig,
    SkillManager,
    SkillSwitchCondition,
    SkillSwitchResult,
    create_skill_manager_from_manifest,
)
from taskforce.core.domain.enums import SkillType
from taskforce.core.domain.skill import Skill

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill(
    name: str = "test-skill",
    instructions: str = "Do the thing.",
    allowed_tools: str | None = None,
    skill_type: SkillType = SkillType.CONTEXT,
) -> Skill:
    """Create a minimal valid Skill for testing."""
    return Skill(
        name=name,
        description=f"Description for {name}",
        instructions=instructions,
        source_path="/tmp/fake-skills/" + name,
        allowed_tools=allowed_tools,
        skill_type=skill_type,
    )


def _make_mock_registry(skills: list[Skill] | None = None) -> MagicMock:
    """Create a mock FileSkillRegistry with predefined skills."""
    registry = MagicMock()
    skill_map: dict[str, Skill] = {}
    if skills:
        for s in skills:
            skill_map[s.name] = s
    registry.get_skill.side_effect = lambda name: skill_map.get(name)
    registry.list_skills.return_value = sorted(skill_map.keys())
    registry.get_skill_count.return_value = len(skill_map)
    return registry


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestSkillManagerInit:
    """Tests for SkillManager initialization."""

    def test_init_without_skills_path(self) -> None:
        """Manager initializes gracefully when no skills_path is provided."""
        with patch(
            "taskforce.application.skill_manager.FileSkillRegistry"
        ) as MockRegistry:
            MockRegistry.return_value = _make_mock_registry()
            # include_global_skills=False ensures no path checking
            manager = SkillManager(
                skills_path=None, include_global_skills=False
            )
        assert manager.has_skills is False
        assert manager.list_skills() == []

    def test_init_with_skills_path_and_existing_dir(self, tmp_path: Path) -> None:
        """Manager discovers skills when a valid directory is provided."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        mock_reg = _make_mock_registry([_make_skill("alpha")])

        with patch(
            "taskforce.application.skill_manager.FileSkillRegistry",
            return_value=mock_reg,
        ):
            manager = SkillManager(
                skills_path=str(skills_dir), include_global_skills=False
            )
        assert manager.has_skills is True
        assert "alpha" in manager.list_skills()

    def test_init_parses_skill_configs(self) -> None:
        """Skill configs are parsed into SkillConfig dataclasses."""
        configs = [
            {"name": "invoice", "trigger": "INVOICE_PROCESSING", "description": "Invoices"},
            {"name": "booking", "trigger": "BOOKING"},
        ]
        with patch(
            "taskforce.application.skill_manager.FileSkillRegistry"
        ):
            manager = SkillManager(
                skills_path=None,
                skill_configs=configs,
                include_global_skills=False,
            )
        assert "invoice" in manager._skill_configs
        assert manager._skill_configs["invoice"].trigger == "INVOICE_PROCESSING"
        assert manager._skill_configs["booking"].description == ""

    def test_init_ignores_invalid_skill_configs(self) -> None:
        """Invalid configs (non-dict, missing name) are silently skipped."""
        configs: list[dict[str, Any]] = [
            "not-a-dict",  # type: ignore[list-item]
            {"trigger": "NO_NAME"},
            {"name": "valid", "trigger": "OK"},
        ]
        with patch("taskforce.application.skill_manager.FileSkillRegistry"):
            manager = SkillManager(
                skills_path=None,
                skill_configs=configs,
                include_global_skills=False,
            )
        assert len(manager._skill_configs) == 1
        assert "valid" in manager._skill_configs


# ---------------------------------------------------------------------------
# Skill Activation
# ---------------------------------------------------------------------------


class TestSkillActivation:
    """Tests for skill activation and deactivation."""

    def _make_manager_with_skills(
        self, skills: list[Skill]
    ) -> SkillManager:
        mock_reg = _make_mock_registry(skills)
        with patch(
            "taskforce.application.skill_manager.FileSkillRegistry",
            return_value=mock_reg,
        ):
            manager = SkillManager(
                skills_path="/fake/path",
                include_global_skills=False,
            )
        # Patch _registry directly to our mock
        manager._registry = mock_reg
        return manager

    def test_activate_skill_by_name(self) -> None:
        """Activating a skill by name sets it as active."""
        skill = _make_skill("my-skill")
        manager = self._make_manager_with_skills([skill])

        result = manager.activate_skill("my-skill")
        assert result is not None
        assert result.name == "my-skill"
        assert manager.active_skill_name == "my-skill"

    def test_activate_nonexistent_skill_returns_none(self) -> None:
        """Activating a nonexistent skill returns None."""
        manager = self._make_manager_with_skills([])
        result = manager.activate_skill("ghost-skill")
        assert result is None
        assert manager.active_skill_name is None

    def test_activate_without_registry_returns_none(self) -> None:
        """Activating when registry is None returns None."""
        with patch("taskforce.application.skill_manager.FileSkillRegistry"):
            manager = SkillManager(
                skills_path=None, include_global_skills=False
            )
        manager._registry = None
        assert manager.activate_skill("any") is None

    def test_activate_new_skill_deactivates_previous(self) -> None:
        """Activating a new skill deactivates the previous one."""
        skill_a = _make_skill("skill-a", instructions="A instructions")
        skill_b = _make_skill("skill-b", instructions="B instructions")
        manager = self._make_manager_with_skills([skill_a, skill_b])

        manager.activate_skill("skill-a")
        assert manager.active_skill_name == "skill-a"

        manager.activate_skill("skill-b")
        assert manager.active_skill_name == "skill-b"
        assert manager._previous_skill_name == "skill-a"

    def test_deactivate_current(self) -> None:
        """Deactivating the current skill clears active state."""
        skill = _make_skill("active-skill")
        manager = self._make_manager_with_skills([skill])
        manager.activate_skill("active-skill")

        manager.deactivate_current()
        assert manager.active_skill_name is None
        assert manager._previous_skill_name == "active-skill"

    def test_deactivate_current_noop_when_none_active(self) -> None:
        """Deactivating when nothing is active does nothing."""
        manager = self._make_manager_with_skills([])
        manager.deactivate_current()
        assert manager.active_skill_name is None


# ---------------------------------------------------------------------------
# Intent-Based Activation
# ---------------------------------------------------------------------------


class TestIntentActivation:
    """Tests for activate_by_intent."""

    def _make_manager(
        self, skills: list[Skill], configs: list[dict[str, Any]] | None = None
    ) -> SkillManager:
        mock_reg = _make_mock_registry(skills)
        with patch(
            "taskforce.application.skill_manager.FileSkillRegistry",
            return_value=mock_reg,
        ):
            manager = SkillManager(
                skills_path="/fake",
                skill_configs=configs,
                include_global_skills=False,
            )
        manager._registry = mock_reg
        return manager

    def test_activate_by_intent_from_config(self) -> None:
        """Intent matching via configured trigger activates correct skill."""
        skill = _make_skill("invoice-auto")
        configs = [{"name": "invoice-auto", "trigger": "INVOICE_PROCESSING"}]
        manager = self._make_manager([skill], configs)

        result = manager.activate_by_intent("INVOICE_PROCESSING")
        assert result is not None
        assert result.name == "invoice-auto"

    def test_activate_by_intent_fallback_convention(self) -> None:
        """Intent matches by convention (lowered + hyphenated name contains)."""
        skill = _make_skill("invoice-processing")
        manager = self._make_manager([skill])

        result = manager.activate_by_intent("INVOICE_PROCESSING")
        assert result is not None
        assert result.name == "invoice-processing"

    def test_activate_by_intent_no_match_returns_none(self) -> None:
        """Returns None when no skill matches the intent."""
        manager = self._make_manager([_make_skill("unrelated")])
        result = manager.activate_by_intent("BOOKING")
        assert result is None


# ---------------------------------------------------------------------------
# Prompt Enhancement
# ---------------------------------------------------------------------------


class TestPromptEnhancement:
    """Tests for enhance_prompt."""

    def _make_manager(self, skill: Skill) -> SkillManager:
        mock_reg = _make_mock_registry([skill])
        with patch(
            "taskforce.application.skill_manager.FileSkillRegistry",
            return_value=mock_reg,
        ):
            manager = SkillManager(
                skills_path="/fake", include_global_skills=False
            )
        manager._registry = mock_reg
        return manager

    def test_enhance_prompt_with_active_skill(self) -> None:
        """Active skill instructions are appended to the base prompt."""
        skill = _make_skill("coder", instructions="Write clean code.")
        manager = self._make_manager(skill)
        manager.activate_skill("coder")

        enhanced = manager.enhance_prompt("Base prompt.")
        assert "Base prompt." in enhanced
        assert "ACTIVE SKILL: coder" in enhanced
        assert "Write clean code." in enhanced

    def test_enhance_prompt_without_active_skill(self) -> None:
        """Returns unmodified prompt when no skill is active."""
        skill = _make_skill("coder")
        manager = self._make_manager(skill)

        result = manager.enhance_prompt("Base prompt.")
        assert result == "Base prompt."


# ---------------------------------------------------------------------------
# Skill Switch Conditions
# ---------------------------------------------------------------------------


class TestSkillSwitch:
    """Tests for check_skill_switch."""

    def _make_manager(self, skills: list[Skill]) -> SkillManager:
        mock_reg = _make_mock_registry(skills)
        with patch(
            "taskforce.application.skill_manager.FileSkillRegistry",
            return_value=mock_reg,
        ):
            manager = SkillManager(
                skills_path="/fake", include_global_skills=False
            )
        manager._registry = mock_reg
        return manager

    def test_switch_triggered_when_condition_met(self) -> None:
        """Switch fires when all conditions match."""
        auto = _make_skill("auto-skill", instructions="auto instructions")
        hitl = _make_skill("hitl-skill", instructions="hitl instructions")
        manager = self._make_manager([auto, hitl])
        manager.activate_skill("auto-skill")

        condition = SkillSwitchCondition(
            from_skill="auto-skill",
            to_skill="hitl-skill",
            trigger_tool="evaluator",
            condition_key="recommendation",
            condition_check=lambda v: v == "hitl_review",
        )
        manager.add_switch_condition(condition)

        result = manager.check_skill_switch(
            "evaluator", {"recommendation": "hitl_review"}
        )
        assert result.switched is True
        assert result.from_skill == "auto-skill"
        assert result.to_skill == "hitl-skill"
        assert result.trigger_tool == "evaluator"
        assert result.new_instructions == "hitl instructions"
        assert manager.active_skill_name == "hitl-skill"

    def test_switch_not_triggered_wrong_tool(self) -> None:
        """Switch does not fire when tool name does not match."""
        auto = _make_skill("auto-skill")
        hitl = _make_skill("hitl-skill")
        manager = self._make_manager([auto, hitl])
        manager.activate_skill("auto-skill")

        condition = SkillSwitchCondition(
            from_skill="auto-skill",
            to_skill="hitl-skill",
            trigger_tool="evaluator",
            condition_key="recommendation",
            condition_check=lambda v: v == "hitl_review",
        )
        manager.add_switch_condition(condition)

        result = manager.check_skill_switch(
            "wrong_tool", {"recommendation": "hitl_review"}
        )
        assert result.switched is False

    def test_switch_not_triggered_condition_false(self) -> None:
        """Switch does not fire when condition_check returns False."""
        auto = _make_skill("auto-skill")
        hitl = _make_skill("hitl-skill")
        manager = self._make_manager([auto, hitl])
        manager.activate_skill("auto-skill")

        condition = SkillSwitchCondition(
            from_skill="auto-skill",
            to_skill="hitl-skill",
            trigger_tool="evaluator",
            condition_key="recommendation",
            condition_check=lambda v: v == "hitl_review",
        )
        manager.add_switch_condition(condition)

        result = manager.check_skill_switch(
            "evaluator", {"recommendation": "auto_approve"}
        )
        assert result.switched is False

    def test_switch_not_triggered_no_active_skill(self) -> None:
        """Switch does not fire when no skill is active."""
        manager = self._make_manager([])
        result = manager.check_skill_switch("evaluator", {"key": "val"})
        assert result.switched is False


# ---------------------------------------------------------------------------
# Context Data Transfer
# ---------------------------------------------------------------------------


class TestContextDataTransfer:
    """Tests for context data management during switches."""

    def test_transfer_context_stores_known_keys(self) -> None:
        """Context transfer stores recognized keys from tool output."""
        with patch("taskforce.application.skill_manager.FileSkillRegistry"):
            manager = SkillManager(skills_path=None, include_global_skills=False)

        tool_output = {
            "overall_confidence": 0.85,
            "recommendation": "auto_approve",
            "unknown_key": "ignored",
        }
        manager._transfer_context(tool_output)

        context = manager.get_context_data()
        assert context["overall_confidence"] == 0.85
        assert context["recommendation"] == "auto_approve"
        assert "unknown_key" not in context

    def test_get_context_data_returns_copy(self) -> None:
        """get_context_data returns a copy, not the original dict."""
        with patch("taskforce.application.skill_manager.FileSkillRegistry"):
            manager = SkillManager(skills_path=None, include_global_skills=False)

        manager._transfer_context({"overall_confidence": 0.5})
        data = manager.get_context_data()
        data["overall_confidence"] = 999

        assert manager.get_context_data()["overall_confidence"] == 0.5


# ---------------------------------------------------------------------------
# Allowed Tools
# ---------------------------------------------------------------------------


class TestAllowedTools:
    """Tests for get_allowed_tools."""

    def _make_manager(self, skill: Skill) -> SkillManager:
        mock_reg = _make_mock_registry([skill])
        with patch(
            "taskforce.application.skill_manager.FileSkillRegistry",
            return_value=mock_reg,
        ):
            manager = SkillManager(
                skills_path="/fake", include_global_skills=False
            )
        manager._registry = mock_reg
        return manager

    def test_returns_tools_list_when_skill_has_allowlist(self) -> None:
        """Returns parsed tool names when active skill has allowed_tools."""
        skill = _make_skill("gated", allowed_tools="python file_read shell")
        manager = self._make_manager(skill)
        manager.activate_skill("gated")

        tools = manager.get_allowed_tools()
        assert tools == ["python", "file_read", "shell"]

    def test_returns_none_when_no_restrictions(self) -> None:
        """Returns None when active skill has no allowed_tools."""
        skill = _make_skill("open", allowed_tools=None)
        manager = self._make_manager(skill)
        manager.activate_skill("open")

        assert manager.get_allowed_tools() is None

    def test_returns_none_when_no_active_skill(self) -> None:
        """Returns None when no skill is active."""
        with patch("taskforce.application.skill_manager.FileSkillRegistry"):
            manager = SkillManager(skills_path=None, include_global_skills=False)
        assert manager.get_allowed_tools() is None


# ---------------------------------------------------------------------------
# Reset and Summary
# ---------------------------------------------------------------------------


class TestResetAndSummary:
    """Tests for reset and get_summary."""

    def _make_manager(self, skills: list[Skill]) -> SkillManager:
        mock_reg = _make_mock_registry(skills)
        with patch(
            "taskforce.application.skill_manager.FileSkillRegistry",
            return_value=mock_reg,
        ):
            manager = SkillManager(
                skills_path="/fake", include_global_skills=False
            )
        manager._registry = mock_reg
        return manager

    def test_reset_clears_all_state(self) -> None:
        """Reset clears active skill, previous skill, and context data."""
        skill = _make_skill("active")
        manager = self._make_manager([skill])
        manager.activate_skill("active")
        manager._context_data = {"key": "val"}

        manager.reset()

        assert manager.active_skill_name is None
        assert manager._previous_skill_name is None
        assert manager._context_data == {}

    def test_get_summary_structure(self) -> None:
        """Summary contains expected keys and values."""
        skill = _make_skill("alpha")
        manager = self._make_manager([skill])
        manager.activate_skill("alpha")

        summary = manager.get_summary()
        assert summary["active_skill"] == "alpha"
        assert "alpha" in summary["available_skills"]
        assert summary["total_skills"] == 1
        assert summary["switch_conditions_count"] == 0


# ---------------------------------------------------------------------------
# create_skill_manager_from_manifest
# ---------------------------------------------------------------------------


class TestCreateSkillManagerFromManifest:
    """Tests for the create_skill_manager_from_manifest factory function."""

    def test_returns_none_when_no_skills_and_no_globals(self) -> None:
        """Returns None when manifest has no skills_path and globals disabled."""
        manifest = MagicMock()
        manifest.skills_path = None

        result = create_skill_manager_from_manifest(
            manifest, include_global_skills=False
        )
        assert result is None

    def test_returns_manager_when_skills_path_present(self) -> None:
        """Returns a SkillManager when manifest has skills_path."""
        manifest = MagicMock()
        manifest.skills_path = "/tmp/fake/skills"

        with patch("taskforce.application.skill_manager.FileSkillRegistry"):
            result = create_skill_manager_from_manifest(
                manifest, include_global_skills=False
            )
        assert isinstance(result, SkillManager)

    def test_returns_manager_when_include_globals(self) -> None:
        """Returns a SkillManager when global skills are enabled (even without skills_path)."""
        manifest = MagicMock()
        manifest.skills_path = None

        with patch("taskforce.application.skill_manager.FileSkillRegistry"):
            result = create_skill_manager_from_manifest(
                manifest, include_global_skills=True
            )
        assert isinstance(result, SkillManager)

    def test_passes_skill_configs_through(self) -> None:
        """Skill configs are forwarded to the SkillManager."""
        manifest = MagicMock()
        manifest.skills_path = None

        configs = [{"name": "my-skill", "trigger": "BOOKING"}]
        with patch("taskforce.application.skill_manager.FileSkillRegistry"):
            result = create_skill_manager_from_manifest(
                manifest, skill_configs=configs, include_global_skills=True
            )
        assert result is not None
        assert "my-skill" in result._skill_configs


# ---------------------------------------------------------------------------
# Dataclass sanity checks
# ---------------------------------------------------------------------------


class TestDataclasses:
    """Sanity tests for supporting dataclasses."""

    def test_skill_switch_result_default(self) -> None:
        """SkillSwitchResult defaults are sensible."""
        result = SkillSwitchResult(switched=False)
        assert result.from_skill is None
        assert result.to_skill is None
        assert result.reason is None

    def test_skill_config_fields(self) -> None:
        """SkillConfig stores its fields correctly."""
        cfg = SkillConfig(name="foo", trigger="BAR", description="Desc")
        assert cfg.name == "foo"
        assert cfg.trigger == "BAR"
        assert cfg.description == "Desc"

    def test_skill_switch_condition_fields(self) -> None:
        """SkillSwitchCondition stores its fields correctly."""
        cond = SkillSwitchCondition(
            from_skill="a",
            to_skill="b",
            trigger_tool="tool",
            condition_key="key",
            condition_check=lambda v: True,
        )
        assert cond.from_skill == "a"
        assert cond.condition_check("anything") is True
