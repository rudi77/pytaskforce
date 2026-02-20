"""
File-based Skill Registry

Implements SkillRegistryProtocol for filesystem-based skill management.
Discovers, caches, and provides access to skills from configured directories.

Extended to support:
- Slash-name index for /name-style invocation
- Filtering by skill type (context, prompt, agent)
"""

import logging
from pathlib import Path
from typing import Iterator

from taskforce.core.domain.enums import SkillType
from taskforce.core.domain.skill import Skill, SkillMetadataModel
from taskforce.infrastructure.skills.skill_loader import (
    SkillLoader,
    get_default_skill_directories,
)


logger = logging.getLogger(__name__)


class FileSkillRegistry:
    """
    File-based implementation of SkillRegistryProtocol.

    Manages skill discovery and loading from filesystem directories.
    Caches metadata for efficient repeated access.

    Usage:
        >>> registry = FileSkillRegistry()
        >>> registry.refresh()  # Discover skills
        >>> skills = registry.list_skills()
        >>> skill = registry.get_skill("pdf-processing")
        >>> skill = registry.get_skill_by_slash_name("review")  # /review
    """

    def __init__(
        self,
        skill_directories: list[str] | None = None,
        auto_discover: bool = True,
    ):
        """
        Initialize the skill registry.

        Args:
            skill_directories: List of directories to search for skills.
                              If None, uses default locations.
            auto_discover: If True, discover skills on initialization.
        """
        directories = skill_directories or get_default_skill_directories()
        self._loader = SkillLoader(directories)

        # Metadata cache: canonical_name -> SkillMetadataModel
        self._metadata_cache: dict[str, SkillMetadataModel] = {}

        # Full skill cache: canonical_name -> Skill (loaded on demand)
        self._skill_cache: dict[str, Skill] = {}

        # Slash-name index: effective_slash_name -> canonical_name
        self._slash_name_index: dict[str, str] = {}

        if auto_discover:
            self.refresh()

    @property
    def directories(self) -> list[Path]:
        """Get the list of configured skill directories."""
        return self._loader.directories

    def add_directory(self, directory: str | Path) -> bool:
        """
        Add a directory to the skill search path.

        Args:
            directory: Directory path to add

        Returns:
            True if directory was added, False if it doesn't exist
        """
        result = self._loader.add_directory(directory)
        if result:
            self._discover_from_directory(Path(directory))
        return result

    def _discover_from_directory(self, directory: Path) -> None:
        """Discover skills from a specific directory."""
        path = directory.expanduser().resolve()
        if not path.exists():
            return

        skill_file = path / SkillLoader.SKILL_FILE
        if skill_file.exists():
            self._try_load_metadata(path)
            return

        for subdir in path.iterdir():
            if subdir.is_dir():
                skill_file = subdir / SkillLoader.SKILL_FILE
                if skill_file.exists():
                    self._try_load_metadata(subdir)

    def _try_load_metadata(self, skill_dir: Path) -> None:
        """Try to load metadata from a skill directory and update indexes."""
        from taskforce.infrastructure.skills.skill_parser import (
            SkillParseError,
            parse_skill_metadata,
        )

        skill_file = skill_dir / SkillLoader.SKILL_FILE
        try:
            content = skill_file.read_text(encoding="utf-8")
            metadata = parse_skill_metadata(content, str(skill_dir))
            self._metadata_cache[metadata.name] = metadata
            self._slash_name_index[metadata.effective_slash_name.lower()] = metadata.name
            logger.debug(f"Discovered skill: {metadata.name}")
        except (OSError, UnicodeDecodeError, SkillParseError) as e:
            logger.warning(f"Failed to load skill from {skill_dir}: {e}")

    def discover_skills(self) -> list[SkillMetadataModel]:
        """Discover all available skills and return their metadata."""
        return list(self._metadata_cache.values())

    def refresh(self) -> None:
        """Re-scan skill directories and refresh the registry."""
        self._metadata_cache.clear()
        self._skill_cache.clear()
        self._slash_name_index.clear()

        metadata_list = self._loader.discover_metadata()
        for metadata in metadata_list:
            self._metadata_cache[metadata.name] = metadata
            self._slash_name_index[metadata.effective_slash_name.lower()] = metadata.name

        logger.info(f"Discovered {len(self._metadata_cache)} skills")

    def get_skill(self, name: str) -> Skill | None:
        """
        Load a complete skill by canonical name.

        Args:
            name: Skill identifier

        Returns:
            Full skill object, or None if not found
        """
        if name in self._skill_cache:
            return self._skill_cache[name]

        if name not in self._metadata_cache:
            return None

        metadata = self._metadata_cache[name]
        skill = self._loader.load_skill(metadata.source_path)

        if skill:
            self._skill_cache[name] = skill

        return skill

    def get_skill_by_slash_name(self, slash_name: str) -> Skill | None:
        """
        Find a skill by its effective slash name.

        Used for /name-style invocation from the chat interface.
        Checks the slash-name index first, then falls back to direct
        canonical name lookup.

        Args:
            slash_name: The slash-command name (without leading /)

        Returns:
            Full skill object, or None if not found
        """
        canonical = self._slash_name_index.get(slash_name.lower())
        if canonical:
            return self.get_skill(canonical)
        # Fallback: try as canonical name directly
        return self.get_skill(slash_name.lower())

    def list_skills(self) -> list[str]:
        """List names of all discovered skills, sorted alphabetically."""
        return sorted(self._metadata_cache.keys())

    def list_slash_command_skills(self) -> list[str]:
        """
        List names of skills directly invokable via /name (PROMPT or AGENT type).

        Returns:
            List of skill names, sorted alphabetically
        """
        return sorted(
            name
            for name, meta in self._metadata_cache.items()
            if meta.skill_type in (SkillType.PROMPT, SkillType.AGENT)
        )

    def get_skill_metadata(self, name: str) -> SkillMetadataModel | None:
        """Get metadata for a specific skill without loading instructions."""
        return self._metadata_cache.get(name)

    def get_all_metadata(self) -> list[SkillMetadataModel]:
        """Get metadata for all discovered skills, sorted by name."""
        return sorted(self._metadata_cache.values(), key=lambda m: m.name)

    def iter_skills(self) -> Iterator[Skill]:
        """Iterate over all skills, loading each one."""
        for name in self.list_skills():
            skill = self.get_skill(name)
            if skill:
                yield skill

    def has_skill(self, name: str) -> bool:
        """Check if a skill exists in the registry."""
        return name in self._metadata_cache

    def get_skills_for_prompt(self) -> str:
        """Generate skill metadata section for system prompt."""
        if not self._metadata_cache:
            return ""

        lines = ["Available Skills:"]
        for metadata in self.get_all_metadata():
            lines.append(f"- {metadata.name}: {metadata.description}")

        return "\n".join(lines)

    def get_skill_count(self) -> int:
        """Get the number of discovered skills."""
        return len(self._metadata_cache)

    def clear_skill_cache(self, name: str | None = None) -> None:
        """
        Clear cached skill data.

        Args:
            name: If provided, only clear cache for this skill.
                  If None, clear all skill caches.
        """
        if name:
            self._skill_cache.pop(name, None)
        else:
            self._skill_cache.clear()


def create_skill_registry(
    additional_directories: list[str] | None = None,
    include_defaults: bool = True,
) -> FileSkillRegistry:
    """
    Create a skill registry with configured directories.

    Args:
        additional_directories: Extra directories to include
        include_defaults: If True, include default skill directories

    Returns:
        Configured FileSkillRegistry instance
    """
    directories: list[str] = []

    if include_defaults:
        directories.extend(get_default_skill_directories())

    if additional_directories:
        directories.extend(additional_directories)

    return FileSkillRegistry(directories)
