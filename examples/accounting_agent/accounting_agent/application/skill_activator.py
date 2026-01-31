"""
Skill Activator for Accounting Agent

This module provides intent-based skill activation for the accounting agent.
It manages the lifecycle of booking skills and handles automatic skill switching
based on tool outputs (e.g., confidence evaluation results).

Usage:
    activator = AccountingSkillActivator(skill_directories=["./skills"])

    # Activate skill based on intent
    skill = activator.activate_by_intent("INVOICE_PROCESSING")

    # Check if skill switch is needed based on tool output
    new_skill = activator.check_skill_switch(confidence_result)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from taskforce.core.domain.skill import Skill, SkillContext
from taskforce.infrastructure.skills.skill_registry import FileSkillRegistry


logger = logging.getLogger(__name__)


class AccountingIntent(Enum):
    """User intent classifications for accounting agent."""

    INVOICE_QUESTION = "INVOICE_QUESTION"
    INVOICE_PROCESSING = "INVOICE_PROCESSING"


@dataclass
class SkillSwitchCondition:
    """
    Defines conditions for automatic skill switching.

    Attributes:
        from_skill: Name of the source skill
        to_skill: Name of the target skill
        condition: Function that evaluates tool output
    """

    from_skill: str
    to_skill: str
    condition_key: str  # Key in tool output to check
    condition_value: Any  # Expected value or callable


class AccountingSkillActivator:
    """
    Manages skill activation and switching for the accounting agent.

    This class implements intent-based skill activation with automatic
    skill switching based on deterministic conditions (e.g., confidence
    evaluation results).

    Attributes:
        skill_registry: Registry for skill discovery and loading
        skill_context: Current execution context with active skills
    """

    # Mapping of intents to skill names
    INTENT_SKILL_MAP: dict[AccountingIntent, str] = {
        AccountingIntent.INVOICE_QUESTION: "invoice-explanation",
        AccountingIntent.INVOICE_PROCESSING: "smart-booking-auto",
    }

    # Skill switch conditions (deterministic, based on tool output)
    SWITCH_CONDITIONS: list[SkillSwitchCondition] = [
        SkillSwitchCondition(
            from_skill="smart-booking-auto",
            to_skill="smart-booking-hitl",
            condition_key="recommendation",
            condition_value="hitl_review",
        ),
        SkillSwitchCondition(
            from_skill="smart-booking-auto",
            to_skill="smart-booking-hitl",
            condition_key="triggered_hard_gates",
            condition_value=lambda gates: len(gates) > 0 if gates else False,
        ),
    ]

    def __init__(
        self,
        skill_directories: list[str] | None = None,
        auto_discover: bool = True,
    ):
        """
        Initialize the skill activator.

        Args:
            skill_directories: Directories to search for skills
            auto_discover: If True, discover skills on initialization
        """
        self.skill_registry = FileSkillRegistry(
            skill_directories=skill_directories,
            auto_discover=auto_discover,
        )
        self.skill_context = SkillContext()
        self._active_skill_name: str | None = None

        logger.info(
            f"AccountingSkillActivator initialized with "
            f"{self.skill_registry.get_skill_count()} skills"
        )

    @property
    def active_skill(self) -> Skill | None:
        """Get the currently active skill."""
        if not self._active_skill_name:
            return None
        return self.skill_context.active_skills.get(self._active_skill_name)

    @property
    def active_skill_name(self) -> str | None:
        """Get the name of the currently active skill."""
        return self._active_skill_name

    def add_skill_directory(self, directory: str | Path) -> bool:
        """
        Add a directory to search for skills.

        Args:
            directory: Path to skill directory

        Returns:
            True if directory was added successfully
        """
        result = self.skill_registry.add_directory(directory)
        if result:
            logger.info(f"Added skill directory: {directory}")
        return result

    def activate_by_intent(self, intent: str | AccountingIntent) -> Skill | None:
        """
        Activate the appropriate skill based on user intent.

        Args:
            intent: User intent (INVOICE_QUESTION or INVOICE_PROCESSING)

        Returns:
            Activated skill, or None if not found
        """
        # Convert string to enum if needed
        if isinstance(intent, str):
            try:
                intent = AccountingIntent(intent)
            except ValueError:
                logger.warning(f"Unknown intent: {intent}")
                return None

        # Get skill name for intent
        skill_name = self.INTENT_SKILL_MAP.get(intent)
        if not skill_name:
            logger.warning(f"No skill mapped for intent: {intent}")
            return None

        return self._activate_skill(skill_name)

    def activate_skill(self, skill_name: str) -> Skill | None:
        """
        Directly activate a skill by name.

        Args:
            skill_name: Name of the skill to activate

        Returns:
            Activated skill, or None if not found
        """
        return self._activate_skill(skill_name)

    def _activate_skill(self, skill_name: str) -> Skill | None:
        """
        Internal method to activate a skill.

        Deactivates any currently active skill before activating the new one.

        Args:
            skill_name: Name of the skill to activate

        Returns:
            Activated skill, or None if not found
        """
        # Load skill from registry
        skill = self.skill_registry.get_skill(skill_name)
        if not skill:
            logger.warning(f"Skill not found: {skill_name}")
            return None

        # Deactivate current skill if different
        if self._active_skill_name and self._active_skill_name != skill_name:
            self.skill_context.deactivate_skill(self._active_skill_name)
            logger.debug(f"Deactivated skill: {self._active_skill_name}")

        # Activate new skill
        self.skill_context.activate_skill(skill)
        self._active_skill_name = skill_name
        logger.info(f"Activated skill: {skill_name}")

        return skill

    def check_skill_switch(
        self,
        tool_output: dict[str, Any],
        tool_name: str | None = None,
    ) -> Skill | None:
        """
        Check if a skill switch is needed based on tool output.

        This method implements deterministic skill switching based on
        predefined conditions. For example, switching from smart-booking-auto
        to smart-booking-hitl when confidence is below threshold.

        Args:
            tool_output: Output from a tool execution
            tool_name: Optional name of the tool that produced the output

        Returns:
            New skill if switched, None if no switch needed
        """
        if not self._active_skill_name:
            return None

        # Check each switch condition
        for condition in self.SWITCH_CONDITIONS:
            if condition.from_skill != self._active_skill_name:
                continue

            # Get the value from tool output
            value = tool_output.get(condition.condition_key)

            # Evaluate condition
            should_switch = False
            if callable(condition.condition_value):
                should_switch = condition.condition_value(value)
            else:
                should_switch = value == condition.condition_value

            if should_switch:
                logger.info(
                    f"Skill switch triggered: {condition.from_skill} → "
                    f"{condition.to_skill} (condition: {condition.condition_key})"
                )
                return self._activate_skill(condition.to_skill)

        return None

    def get_active_instructions(self) -> str:
        """
        Get instructions from the currently active skill.

        Returns:
            Skill instructions, or empty string if no skill active
        """
        return self.skill_context.get_combined_instructions()

    def get_skill_resource(self, resource_path: str) -> str | None:
        """
        Read a resource from the currently active skill.

        Args:
            resource_path: Relative path to the resource

        Returns:
            Resource content, or None if not found
        """
        if not self._active_skill_name:
            return None
        return self.skill_context.read_skill_resource(
            self._active_skill_name, resource_path
        )

    def deactivate_current(self) -> None:
        """Deactivate the currently active skill."""
        if self._active_skill_name:
            self.skill_context.deactivate_skill(self._active_skill_name)
            logger.debug(f"Deactivated skill: {self._active_skill_name}")
            self._active_skill_name = None

    def reset(self) -> None:
        """Reset the skill context, deactivating all skills."""
        self.skill_context.clear()
        self._active_skill_name = None
        logger.debug("Skill context reset")

    def list_available_skills(self) -> list[str]:
        """
        List all available skill names.

        Returns:
            List of skill names
        """
        return self.skill_registry.list_skills()

    def get_skill_metadata_for_prompt(self) -> str:
        """
        Get formatted skill information for system prompt.

        Returns:
            Formatted string with skill descriptions
        """
        return self.skill_registry.get_skills_for_prompt()

    def get_allowed_tools(self) -> list[str] | None:
        """
        Get the list of allowed tools for the active skill.

        Returns:
            List of tool names, or None if no restrictions
        """
        skill = self.active_skill
        if not skill or not skill.allowed_tools:
            return None
        return skill.allowed_tools.split()


def create_accounting_skill_activator(
    plugin_path: str | Path | None = None,
) -> AccountingSkillActivator:
    """
    Factory function to create an AccountingSkillActivator.

    Args:
        plugin_path: Path to the accounting_agent plugin directory.
                    If None, uses current directory.

    Returns:
        Configured AccountingSkillActivator instance
    """
    if plugin_path is None:
        plugin_path = Path(__file__).parent.parent

    plugin_path = Path(plugin_path)
    skills_dir = plugin_path / "skills"

    if not skills_dir.exists():
        logger.warning(f"Skills directory not found: {skills_dir}")
        return AccountingSkillActivator(skill_directories=[], auto_discover=False)

    return AccountingSkillActivator(
        skill_directories=[str(skills_dir)],
        auto_discover=True,
    )
