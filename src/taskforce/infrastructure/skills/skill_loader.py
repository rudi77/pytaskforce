"""
Skill Loader

Loads skills from filesystem directories. Each skill is a directory
containing a SKILL.md file with optional additional resources.

Skill Directory Structure:
    skill-name/
    ├── SKILL.md           # Required: Metadata and instructions
    ├── REFERENCE.md       # Optional: Additional documentation
    ├── scripts/           # Optional: Executable scripts
    │   └── process.py
    └── templates/         # Optional: Template files
        └── report.html
"""

from collections.abc import Iterator
from pathlib import Path

import structlog

from taskforce.core.domain.skill import Skill, SkillMetadataModel
from taskforce.infrastructure.skills.skill_parser import (
    SkillParseError,
    parse_skill_markdown,
    parse_skill_metadata,
)

logger = structlog.get_logger(__name__)


class SkillLoader:
    """
    Loads skills from filesystem directories.

    Searches configured directories for valid skill folders and
    provides methods to discover and load skills.
    """

    SKILL_FILE = "SKILL.md"

    def __init__(self, skill_directories: list[str] | None = None):
        """
        Initialize the skill loader.

        Args:
            skill_directories: List of directories to search for skills.
                              If None, uses default locations.
        """
        self._directories: list[Path] = []

        if skill_directories:
            for directory in skill_directories:
                path = Path(directory).expanduser().resolve()
                if path.exists() and path.is_dir():
                    self._directories.append(path)
                else:
                    logger.warning("skill.directory_not_found", directory=directory)

    @property
    def directories(self) -> list[Path]:
        """Get the list of configured skill directories."""
        return self._directories.copy()

    def add_directory(self, directory: str | Path) -> bool:
        """
        Add a directory to the skill search path.

        Args:
            directory: Directory path to add

        Returns:
            True if directory was added, False if it doesn't exist
        """
        path = Path(directory).expanduser().resolve()
        if path.exists() and path.is_dir():
            if path not in self._directories:
                self._directories.append(path)
            return True
        return False

    def discover_skill_directories(self) -> Iterator[Path]:
        """
        Iterate over all directories containing valid SKILL.md files.

        Yields:
            Paths to skill directories (containing SKILL.md)
        """
        for base_dir in self._directories:
            # Check for skills directly in the base directory
            skill_file = base_dir / self.SKILL_FILE
            if skill_file.exists() and skill_file.is_file():
                yield base_dir

            # Check subdirectories
            for subdir in base_dir.iterdir():
                if subdir.is_dir():
                    skill_file = subdir / self.SKILL_FILE
                    if skill_file.exists() and skill_file.is_file():
                        yield subdir

    def discover_metadata(self) -> list[SkillMetadataModel]:
        """
        Discover all skills and return their metadata.

        This is a lightweight operation that only parses frontmatter.

        Returns:
            List of skill metadata objects
        """
        metadata_list: list[SkillMetadataModel] = []

        for skill_dir in self.discover_skill_directories():
            skill_file = skill_dir / self.SKILL_FILE

            try:
                content = skill_file.read_text(encoding="utf-8")
                metadata = parse_skill_metadata(content, str(skill_dir))
                metadata_list.append(metadata)
                logger.debug("skill.discovered", skill_name=metadata.name, path=str(skill_dir))
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("skill.file_read_error", skill_file=str(skill_file), error=str(e))
            except SkillParseError as e:
                logger.warning("skill.parse_error", path=str(skill_dir), error=str(e))

        return metadata_list

    def load_skill(self, skill_dir: str | Path) -> Skill | None:
        """
        Load a complete skill from a directory.

        Args:
            skill_dir: Path to the skill directory

        Returns:
            Skill object, or None if loading fails
        """
        path = Path(skill_dir).expanduser().resolve()
        skill_file = path / self.SKILL_FILE

        if not skill_file.exists():
            logger.warning("skill.missing_skill_md", path=str(path))
            return None

        try:
            content = skill_file.read_text(encoding="utf-8")
            skill = parse_skill_markdown(content, str(path))
            logger.debug("skill.loaded", skill_name=skill.name, path=str(path))
            return skill
        except (OSError, UnicodeDecodeError) as e:
            logger.error("skill.file_read_error", skill_file=str(skill_file), error=str(e))
            return None
        except SkillParseError as e:
            logger.error("skill.parse_failed", path=str(path), error=str(e))
            return None

    def load_skill_by_name(self, name: str) -> Skill | None:
        """
        Load a skill by its name.

        Searches all configured directories for a skill with the
        given name and loads it.

        Args:
            name: Skill name to find

        Returns:
            Skill object, or None if not found
        """
        for skill_dir in self.discover_skill_directories():
            skill_file = skill_dir / self.SKILL_FILE

            try:
                content = skill_file.read_text(encoding="utf-8")
                metadata = parse_skill_metadata(content, str(skill_dir))

                if metadata.name == name:
                    return self.load_skill(skill_dir)
            except (OSError, UnicodeDecodeError, SkillParseError):
                continue

        return None

    def load_all_skills(self) -> list[Skill]:
        """
        Load all valid skills from configured directories.

        Returns:
            List of loaded Skill objects
        """
        skills: list[Skill] = []

        for skill_dir in self.discover_skill_directories():
            skill = self.load_skill(skill_dir)
            if skill:
                skills.append(skill)

        return skills

    def get_skill_path(self, name: str) -> Path | None:
        """
        Find the directory path for a skill by name.

        Args:
            name: Skill name to find

        Returns:
            Path to skill directory, or None if not found
        """
        for skill_dir in self.discover_skill_directories():
            skill_file = skill_dir / self.SKILL_FILE

            try:
                content = skill_file.read_text(encoding="utf-8")
                metadata = parse_skill_metadata(content, str(skill_dir))

                if metadata.name == name:
                    return skill_dir
            except (OSError, UnicodeDecodeError, SkillParseError):
                continue

        return None


def get_default_skill_directories() -> list[str]:
    """
    Get the default skill directory locations.

    Returns:
        List of default skill directory paths:
        - ~/.taskforce/skills (user skills)
        - .taskforce/skills (project skills)
    """
    from pathlib import Path

    directories = []

    # User skills directory
    user_dir = Path.home() / ".taskforce" / "skills"
    directories.append(str(user_dir))

    # Project skills directory (current working directory)
    project_dir = Path.cwd() / ".taskforce" / "skills"
    directories.append(str(project_dir))

    return directories
