"""
Skill Manager for Plugin-based Agents

This module provides skill management for plugin agents, including:
- Skill loading from plugin directories
- Intent-based skill activation
- Automatic skill switching based on tool outputs
- System prompt enhancement with skill instructions

Usage:
    manager = SkillManager(skills_path="/path/to/plugin/skills")
    manager.activate_by_intent("INVOICE_PROCESSING")
    enhanced_prompt = manager.enhance_prompt(base_prompt)

    # After tool execution
    switch_info = manager.check_skill_switch(tool_name, tool_output)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from taskforce.core.domain.skill import Skill, SkillContext
from taskforce.infrastructure.skills.skill_registry import FileSkillRegistry


logger = logging.getLogger(__name__)


@dataclass
class SkillSwitchCondition:
    """
    Defines conditions for automatic skill switching.

    Attributes:
        from_skill: Name of the source skill
        to_skill: Name of the target skill
        trigger_tool: Name of the tool that can trigger this switch
        condition_key: Key in tool output to check
        condition_check: Function to evaluate the condition
    """

    from_skill: str
    to_skill: str
    trigger_tool: str
    condition_key: str
    condition_check: Callable[[Any], bool]


@dataclass
class SkillSwitchResult:
    """Result of a skill switch check."""

    switched: bool
    from_skill: str | None = None
    to_skill: str | None = None
    trigger_tool: str | None = None
    reason: str | None = None
    new_instructions: str | None = None


@dataclass
class SkillConfig:
    """Configuration for skill activation."""

    name: str
    trigger: str  # Intent or "AUTO_SWITCH"
    description: str = ""


class SkillManager:
    """
    Manages skills for plugin-based agents.

    Handles skill loading, activation, and switching based on
    tool outputs. Designed to work with any plugin that has
    a skills/ directory.

    Skills are loaded from multiple sources (in priority order):
    1. Plugin-specific skills (from plugin's skills/ directory)
    2. Project skills (from .taskforce/skills)
    3. User skills (from ~/.taskforce/skills)

    Attributes:
        skills_path: Path to the plugin skills directory
        skill_context: Current execution context with active skills
        switch_conditions: List of conditions for automatic switching
    """

    def __init__(
        self,
        skills_path: str | Path | None = None,
        skill_configs: list[dict[str, Any]] | None = None,
        switch_conditions: list[SkillSwitchCondition] | None = None,
        include_global_skills: bool = True,
    ):
        """
        Initialize the skill manager.

        Args:
            skills_path: Path to plugin directory containing skills
            skill_configs: Optional list of skill configurations from plugin config
            switch_conditions: Optional list of switch conditions
            include_global_skills: If True, include skills from ~/.taskforce/skills
                                  and .taskforce/skills (default: True)
        """
        self._skills_path = Path(skills_path) if skills_path else None
        self._skill_configs = self._parse_skill_configs(skill_configs or [])
        self._switch_conditions = switch_conditions or []
        self._active_skill_name: str | None = None
        self._previous_skill_name: str | None = None
        self._context_data: dict[str, Any] = {}
        self._include_global_skills = include_global_skills

        # Build list of skill directories
        skill_directories = self._build_skill_directories()

        # Initialize registry with all skill directories
        if skill_directories:
            self._registry = FileSkillRegistry(
                skill_directories=skill_directories,
                auto_discover=True,
            )
            self._skill_context = SkillContext()
            logger.info(
                f"SkillManager initialized with {self._registry.get_skill_count()} skills "
                f"from {len(skill_directories)} directories"
            )
            if self._registry.get_skill_count() > 0:
                logger.debug(f"Available skills: {self._registry.list_skills()}")
        else:
            self._registry = None
            self._skill_context = SkillContext()
            logger.debug("SkillManager initialized without skills")

    def _build_skill_directories(self) -> list[str]:
        """
        Build the list of skill directories to search.

        Returns:
            List of directory paths, with plugin skills first (highest priority)
        """
        directories: list[str] = []

        # Plugin-specific skills have highest priority
        if self._skills_path and self._skills_path.exists():
            directories.append(str(self._skills_path))

        # Include global skills if enabled
        if self._include_global_skills:
            # Project skills (.taskforce/skills)
            project_skills = Path.cwd() / ".taskforce" / "skills"
            if project_skills.exists():
                directories.append(str(project_skills))

            # User skills (~/.taskforce/skills)
            user_skills = Path.home() / ".taskforce" / "skills"
            if user_skills.exists():
                directories.append(str(user_skills))

        return directories

    def _parse_skill_configs(
        self, configs: list[dict[str, Any]]
    ) -> dict[str, SkillConfig]:
        """Parse skill configurations from plugin config."""
        result: dict[str, SkillConfig] = {}
        for cfg in configs:
            if isinstance(cfg, dict) and "name" in cfg:
                result[cfg["name"]] = SkillConfig(
                    name=cfg["name"],
                    trigger=cfg.get("trigger", ""),
                    description=cfg.get("description", ""),
                )
        return result

    @property
    def active_skill(self) -> Skill | None:
        """Get the currently active skill."""
        if not self._active_skill_name or not self._registry:
            return None
        return self._skill_context.active_skills.get(self._active_skill_name)

    @property
    def active_skill_name(self) -> str | None:
        """Get the name of the currently active skill."""
        return self._active_skill_name

    @property
    def has_skills(self) -> bool:
        """Check if this manager has any skills available."""
        return self._registry is not None and self._registry.get_skill_count() > 0

    def list_skills(self) -> list[str]:
        """List all available skill names."""
        if not self._registry:
            return []
        return self._registry.list_skills()

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name."""
        if not self._registry:
            return None
        return self._registry.get_skill(name)

    def activate_skill(self, skill_name: str) -> Skill | None:
        """
        Activate a skill by name.

        Args:
            skill_name: Name of the skill to activate

        Returns:
            Activated skill, or None if not found
        """
        if not self._registry:
            return None

        skill = self._registry.get_skill(skill_name)
        if not skill:
            logger.warning(f"Skill not found: {skill_name}")
            return None

        # Deactivate current skill if different
        if self._active_skill_name and self._active_skill_name != skill_name:
            self._skill_context.deactivate_skill(self._active_skill_name)
            self._previous_skill_name = self._active_skill_name

        # Activate new skill
        self._skill_context.activate_skill(skill)
        self._active_skill_name = skill_name
        logger.info(f"Activated skill: {skill_name}")

        return skill

    def activate_by_intent(self, intent: str) -> Skill | None:
        """
        Activate a skill based on user intent.

        Looks for a skill configured with a matching trigger.

        Args:
            intent: User intent string (e.g., "INVOICE_PROCESSING")

        Returns:
            Activated skill, or None if no matching skill found
        """
        # Find skill configured for this intent
        for skill_name, config in self._skill_configs.items():
            if config.trigger == intent:
                return self.activate_skill(skill_name)

        # Fallback: try to find skill by convention
        # e.g., INVOICE_PROCESSING -> invoice-processing or smart-booking-auto
        intent_lower = intent.lower().replace("_", "-")
        for skill_name in self.list_skills():
            if intent_lower in skill_name:
                return self.activate_skill(skill_name)

        logger.debug(f"No skill found for intent: {intent}")
        return None

    def deactivate_current(self) -> None:
        """Deactivate the currently active skill."""
        if self._active_skill_name:
            self._skill_context.deactivate_skill(self._active_skill_name)
            self._previous_skill_name = self._active_skill_name
            self._active_skill_name = None

    def add_switch_condition(self, condition: SkillSwitchCondition) -> None:
        """Add a skill switch condition."""
        self._switch_conditions.append(condition)

    def check_skill_switch(
        self,
        tool_name: str,
        tool_output: dict[str, Any],
    ) -> SkillSwitchResult:
        """
        Check if a skill switch is needed based on tool output.

        Args:
            tool_name: Name of the tool that was executed
            tool_output: Output from the tool

        Returns:
            SkillSwitchResult with switch information
        """
        if not self._active_skill_name:
            return SkillSwitchResult(switched=False)

        for condition in self._switch_conditions:
            # Check if this condition applies
            if condition.from_skill != self._active_skill_name:
                continue
            if condition.trigger_tool != tool_name:
                continue

            # Get the value to check
            value = tool_output.get(condition.condition_key)

            # Evaluate condition
            if condition.condition_check(value):
                # Store context data for the new skill
                self._transfer_context(tool_output)

                # Activate new skill
                old_skill = self._active_skill_name
                new_skill = self.activate_skill(condition.to_skill)

                if new_skill:
                    logger.info(
                        f"Skill switched: {old_skill} → {condition.to_skill} "
                        f"(triggered by {tool_name}.{condition.condition_key})"
                    )
                    return SkillSwitchResult(
                        switched=True,
                        from_skill=old_skill,
                        to_skill=condition.to_skill,
                        trigger_tool=tool_name,
                        reason=f"{condition.condition_key} condition met",
                        new_instructions=new_skill.instructions,
                    )

        return SkillSwitchResult(switched=False)

    def _transfer_context(self, tool_output: dict[str, Any]) -> None:
        """Transfer relevant context data when switching skills."""
        # Store common fields that might be needed by the next skill
        context_keys = [
            "overall_confidence",
            "recommendation",
            "triggered_hard_gates",
            "signals",
            "booking_proposal",
            "invoice_data",
            "rule_match",
        ]
        for key in context_keys:
            if key in tool_output:
                self._context_data[key] = tool_output[key]

    def get_context_data(self) -> dict[str, Any]:
        """Get accumulated context data from skill switches."""
        return self._context_data.copy()

    def enhance_prompt(self, base_prompt: str) -> str:
        """
        Enhance a base prompt with active skill instructions.

        Args:
            base_prompt: The base system prompt

        Returns:
            Enhanced prompt with skill instructions
        """
        if not self._active_skill_name:
            return base_prompt

        skill_instructions = self._skill_context.get_combined_instructions()
        if not skill_instructions:
            return base_prompt

        return f"""{base_prompt}

# ACTIVE SKILL: {self._active_skill_name}

{skill_instructions}
"""

    def get_active_instructions(self) -> str:
        """Get instructions from the currently active skill."""
        return self._skill_context.get_combined_instructions()

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
        return self._skill_context.read_skill_resource(
            self._active_skill_name, resource_path
        )

    def get_allowed_tools(self) -> list[str] | None:
        """
        Get allowed tools for the active skill.

        Returns:
            List of tool names, or None if no restrictions
        """
        skill = self.active_skill
        if not skill or not skill.allowed_tools:
            return None
        # Parse space-separated tool list
        return skill.allowed_tools.split()

    def reset(self) -> None:
        """Reset the skill context for a new execution."""
        self._skill_context.clear()
        self._active_skill_name = None
        self._previous_skill_name = None
        self._context_data = {}

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the skill manager state."""
        return {
            "skills_path": str(self._skills_path) if self._skills_path else None,
            "total_skills": len(self.list_skills()),
            "available_skills": self.list_skills(),
            "active_skill": self._active_skill_name,
            "previous_skill": self._previous_skill_name,
            "switch_conditions_count": len(self._switch_conditions),
        }


def create_skill_manager_from_manifest(
    manifest: Any,  # PluginManifest
    skill_configs: list[dict[str, Any]] | None = None,
    include_global_skills: bool = True,
) -> SkillManager | None:
    """
    Create a SkillManager from a plugin manifest.

    Args:
        manifest: PluginManifest with skills_path
        skill_configs: Optional skill configurations from plugin config
        include_global_skills: If True, include skills from ~/.taskforce/skills
                              and .taskforce/skills (default: True)

    Returns:
        SkillManager instance, or None if no skills available
    """
    # Create manager even without plugin skills if global skills are enabled
    # This allows using global skills with any plugin
    if not manifest.skills_path and not include_global_skills:
        return None

    return SkillManager(
        skills_path=manifest.skills_path,
        skill_configs=skill_configs,
        include_global_skills=include_global_skills,
    )


# Default switch conditions for common patterns
DEFAULT_ACCOUNTING_SWITCH_CONDITIONS = [
    SkillSwitchCondition(
        from_skill="smart-booking-auto",
        to_skill="smart-booking-hitl",
        trigger_tool="confidence_evaluator",
        condition_key="recommendation",
        condition_check=lambda v: v == "hitl_review",
    ),
    SkillSwitchCondition(
        from_skill="smart-booking-auto",
        to_skill="smart-booking-hitl",
        trigger_tool="confidence_evaluator",
        condition_key="triggered_hard_gates",
        condition_check=lambda v: bool(v) if isinstance(v, list) else False,
    ),
]
