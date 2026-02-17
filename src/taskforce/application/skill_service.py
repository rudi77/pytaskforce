"""
Skill Service
=============

Application layer service for skill discovery and management.

Provides:
- Skill discovery and listing (for CLI/API)
- Skill activation based on relevance
- Skill context management
- System prompt generation with skill metadata

Note:
    For **agent-internal** skill lifecycle (intent-based activation,
    automatic switching, prompt enhancement) use
    :class:`~taskforce.application.skill_manager.SkillManager` instead.
    ``SkillService`` is designed for the **API / CLI layer** where
    global skill discovery and browsing is needed.
"""

import logging
from typing import Any

from taskforce.core.domain.skill import Skill, SkillContext, SkillMetadataModel
from taskforce.infrastructure.skills.skill_registry import (
    FileSkillRegistry,
    create_skill_registry,
)

logger = logging.getLogger(__name__)


class SkillService:
    """
    Application service for skill discovery and management.

    Provides a high-level interface for working with skills,
    including discovery, activation, and context management.

    For agent execution-time skill management (switching, intent-based
    activation), use :class:`~taskforce.application.skill_manager.SkillManager`.
    """

    def __init__(
        self,
        skill_directories: list[str] | None = None,
        extension_directories: list[str] | None = None,
        registry: FileSkillRegistry | None = None,
    ):
        """
        Initialize the skill service.

        Args:
            skill_directories: Custom skill directories to include
            extension_directories: Extension skill directories (e.g., taskforce_extensions/skills)
            registry: Optional pre-existing registry to share (avoids duplicate
                      file-system discovery when a :class:`SkillManager` is
                      already initialised).
        """
        if registry is not None:
            self._registry = registry
        else:
            directories: list[str] = []
            if skill_directories:
                directories.extend(skill_directories)
            if extension_directories:
                directories.extend(extension_directories)

            self._registry = create_skill_registry(
                additional_directories=directories,
                include_defaults=True,
            )
        self._context = SkillContext()

    @property
    def registry(self) -> FileSkillRegistry:
        """Get the underlying skill registry."""
        return self._registry

    @property
    def context(self) -> SkillContext:
        """Get the current skill context."""
        return self._context

    def refresh(self) -> None:
        """Refresh skill discovery from all directories."""
        self._registry.refresh()
        logger.info(f"Refreshed skills, found {self._registry.get_skill_count()}")

    def list_skills(self) -> list[str]:
        """
        List all available skill names.

        Returns:
            Sorted list of skill names
        """
        return self._registry.list_skills()

    def get_skill(self, name: str) -> Skill | None:
        """
        Get a skill by name.

        Args:
            name: Skill identifier

        Returns:
            Skill object or None if not found
        """
        return self._registry.get_skill(name)

    def get_skill_metadata(self, name: str) -> SkillMetadataModel | None:
        """
        Get metadata for a skill without loading full content.

        Args:
            name: Skill identifier

        Returns:
            Skill metadata or None if not found
        """
        return self._registry.get_skill_metadata(name)

    def get_all_metadata(self) -> list[SkillMetadataModel]:
        """
        Get metadata for all available skills.

        Returns:
            List of skill metadata objects
        """
        return self._registry.get_all_metadata()

    def has_skill(self, name: str) -> bool:
        """
        Check if a skill exists.

        Args:
            name: Skill name to check

        Returns:
            True if skill exists
        """
        return self._registry.has_skill(name)

    def activate_skill(self, name: str) -> bool:
        """
        Activate a skill by name.

        Loads the full skill and adds it to the active context.

        Args:
            name: Skill identifier

        Returns:
            True if skill was activated, False if not found
        """
        skill = self._registry.get_skill(name)
        if not skill:
            logger.warning(f"Cannot activate skill '{name}': not found")
            return False

        self._context.activate_skill(skill)
        logger.info(f"Activated skill: {name}")
        return True

    def deactivate_skill(self, name: str) -> None:
        """
        Deactivate a skill.

        Args:
            name: Skill identifier
        """
        self._context.deactivate_skill(name)
        logger.debug(f"Deactivated skill: {name}")

    def get_active_skills(self) -> list[Skill]:
        """
        Get list of currently active skills.

        Returns:
            List of active Skill objects
        """
        return self._context.get_active_skills()

    def is_skill_active(self, name: str) -> bool:
        """
        Check if a skill is currently active.

        Args:
            name: Skill identifier

        Returns:
            True if skill is active
        """
        return self._context.is_active(name)

    def get_combined_instructions(self) -> str:
        """
        Get combined instructions from all active skills.

        Returns:
            Concatenated instructions text
        """
        return self._context.get_combined_instructions()

    def clear_active_skills(self) -> None:
        """Deactivate all skills."""
        self._context.clear()
        logger.debug("Cleared all active skills")

    def get_skill_prompt_section(self) -> str:
        """
        Generate skill metadata section for system prompt.

        This includes only lightweight metadata (name, description)
        for all available skills.

        Returns:
            Formatted string for system prompt
        """
        return self._registry.get_skills_for_prompt()

    def get_active_skills_prompt_section(self) -> str:
        """
        Generate instructions section from active skills.

        Returns:
            Combined instructions from all active skills
        """
        if not self._context.active_skills:
            return ""

        sections = ["# Active Skills\n"]
        for skill in self._context.get_active_skills():
            sections.append(f"## {skill.name}\n\n{skill.instructions}")

        return "\n\n".join(sections)

    def read_skill_resource(self, skill_name: str, resource_path: str) -> str | None:
        """
        Read a resource from an active skill.

        Args:
            skill_name: Name of the skill
            resource_path: Relative path to the resource

        Returns:
            Resource content or None if not found
        """
        return self._context.read_skill_resource(skill_name, resource_path)

    def get_skills_summary(self) -> dict[str, Any]:
        """
        Get a summary of skill status.

        Returns:
            Dictionary with skill counts and names
        """
        return {
            "total_skills": self._registry.get_skill_count(),
            "available_skills": self.list_skills(),
            "active_skills": [s.name for s in self.get_active_skills()],
            "directories": [str(d) for d in self._registry.directories],
        }


# Module-level instance for singleton access
_skill_service: SkillService | None = None


def get_skill_service(
    skill_directories: list[str] | None = None,
    extension_directories: list[str] | None = None,
) -> SkillService:
    """
    Get or create the singleton skill service.

    Args:
        skill_directories: Custom skill directories (only used on first call)
        extension_directories: Extension directories (only used on first call)

    Returns:
        SkillService instance
    """
    global _skill_service
    if _skill_service is None:
        _skill_service = SkillService(
            skill_directories=skill_directories,
            extension_directories=extension_directories,
        )
    return _skill_service


def reset_skill_service() -> None:
    """Reset the singleton skill service (useful for testing)."""
    global _skill_service
    _skill_service = None
