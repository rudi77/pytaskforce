"""
Skill Domain Models

This module defines the core domain models for skills - modular capabilities
that extend agent functionality with domain-specific expertise.

Skills follow a progressive loading pattern:
- Level 1: Metadata (name, description) - always loaded
- Level 2: Instructions (SKILL.md body) - loaded when triggered
- Level 3: Resources (additional files) - loaded as needed
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Validation constants
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_COMPATIBILITY_LENGTH = 500
RESERVED_WORDS = {"anthropic", "claude"}
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
ALLOWED_TOOLS_PATTERN = re.compile(r"^[^\\s]+(\\s+[^\\s]+)*$")


class SkillValidationError(ValueError):
    """Raised when skill validation fails."""

    pass


def validate_skill_name(name: str) -> tuple[bool, str | None]:
    """
    Validate a skill name.

    Requirements:
    - Lowercase with hyphens only (kebab-case)
    - Does not start or end with a hyphen
    - Does not contain consecutive hyphens
    - Maximum 64 characters
    - No reserved words

    Args:
        name: The skill name to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Skill name cannot be empty"

    if len(name) > MAX_NAME_LENGTH:
        return False, f"Skill name exceeds {MAX_NAME_LENGTH} characters"

    if name.startswith("-"):
        return False, "Skill name cannot start with a hyphen"

    if not NAME_PATTERN.match(name):
        return (
            False,
            "Skill name must contain only lowercase letters, numbers, and hyphens",
        )

    if name.endswith("-"):
        return False, "Skill name cannot end with a hyphen"

    if "--" in name:
        return False, "Skill name cannot contain consecutive hyphens"

    # Check for reserved words
    name_lower = name.lower()
    for word in RESERVED_WORDS:
        if word in name_lower:
            return False, f"Skill name cannot contain reserved word: {word}"

    return True, None


def validate_skill_description(description: str) -> tuple[bool, str | None]:
    """
    Validate a skill description.

    Requirements:
    - Non-empty
    - Maximum 1024 characters
    - No XML tags

    Args:
        description: The skill description to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not description or not description.strip():
        return False, "Skill description cannot be empty"

    if len(description) > MAX_DESCRIPTION_LENGTH:
        return False, f"Skill description exceeds {MAX_DESCRIPTION_LENGTH} characters"

    # Check for XML tags
    if re.search(r"<[^>]+>", description):
        return False, "Skill description cannot contain XML tags"

    return True, None


def _validate_optional_string(
    field_name: str,
    value: str | None,
    max_length: int | None = None,
) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise SkillValidationError(f"{field_name} must be a string")
    if not value.strip():
        raise SkillValidationError(f"{field_name} cannot be empty")
    if max_length is not None and len(value) > max_length:
        raise SkillValidationError(f"{field_name} exceeds {max_length} characters")


def _validate_metadata_dict(metadata: dict[str, str] | None) -> None:
    if metadata is None:
        return
    if not isinstance(metadata, dict):
        raise SkillValidationError("metadata must be a dictionary of strings")
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise SkillValidationError("metadata must map strings to strings")


def _validate_allowed_tools(allowed_tools: str | None) -> None:
    if allowed_tools is None:
        return
    if not isinstance(allowed_tools, str):
        raise SkillValidationError("allowed_tools must be a string")
    if not allowed_tools.strip():
        raise SkillValidationError("allowed_tools cannot be empty")
    if not ALLOWED_TOOLS_PATTERN.match(allowed_tools):
        raise SkillValidationError("allowed_tools must be space-delimited")


def _normalize_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


@dataclass(frozen=True)
class SkillMetadataModel:
    """
    Lightweight metadata for skill discovery.

    This model contains only the information needed for skill
    matching without loading the full instructions. Used for
    Level 1 (metadata) loading.

    Attributes:
        name: Unique identifier (lowercase, hyphenated)
        description: What the skill does and when to use it
        source_path: Path to the skill directory
        license: Optional skill license identifier
        compatibility: Optional compatibility notes (max 500 chars)
        metadata: Optional freeform metadata map
        allowed_tools: Optional space-delimited tool allowlist
    """

    name: str
    description: str
    source_path: str
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] | None = None
    allowed_tools: str | None = None

    def __post_init__(self) -> None:
        """Validate metadata after initialization."""
        valid, error = validate_skill_name(self.name)
        if not valid:
            raise SkillValidationError(f"Invalid skill name: {error}")

        valid, error = validate_skill_description(self.description)
        if not valid:
            raise SkillValidationError(f"Invalid skill description: {error}")

        _validate_optional_string("license", self.license)
        _validate_optional_string(
            "compatibility",
            self.compatibility,
            max_length=MAX_COMPATIBILITY_LENGTH,
        )
        _validate_metadata_dict(self.metadata)
        _validate_allowed_tools(self.allowed_tools)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "source_path": self.source_path,
            "license": self.license,
            "compatibility": self.compatibility,
            "metadata": self.metadata,
            "allowed_tools": self.allowed_tools,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillMetadataModel:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            source_path=data.get("source_path", ""),
            license=_normalize_optional_str(data.get("license")),
            compatibility=_normalize_optional_str(data.get("compatibility")),
            metadata=data.get("metadata"),
            allowed_tools=_normalize_optional_str(data.get("allowed_tools")),
        )


@dataclass
class Skill:
    """
    Full skill model with instructions and resource access.

    This is the complete skill representation used when a skill
    is activated. Includes:
    - Metadata (name, description)
    - Instructions (SKILL.md body)
    - Resource access methods

    Attributes:
        name: Unique identifier (lowercase, hyphenated)
        description: What the skill does and when to use it
        instructions: Main instructional content from SKILL.md
        source_path: Path to the skill directory
        license: Optional skill license identifier
        compatibility: Optional compatibility notes (max 500 chars)
        metadata: Optional freeform metadata map
        allowed_tools: Optional space-delimited tool allowlist
        _resources_cache: Cached resource paths (internal)
    """

    name: str
    description: str
    instructions: str
    source_path: str
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] | None = None
    allowed_tools: str | None = None
    _resources_cache: dict[str, str] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Validate skill after initialization."""
        valid, error = validate_skill_name(self.name)
        if not valid:
            raise SkillValidationError(f"Invalid skill name: {error}")

        valid, error = validate_skill_description(self.description)
        if not valid:
            raise SkillValidationError(f"Invalid skill description: {error}")

        _validate_optional_string("license", self.license)
        _validate_optional_string(
            "compatibility",
            self.compatibility,
            max_length=MAX_COMPATIBILITY_LENGTH,
        )
        _validate_metadata_dict(self.metadata)
        _validate_allowed_tools(self.allowed_tools)

    @property
    def metadata_model(self) -> SkillMetadataModel:
        """Get lightweight metadata object."""
        return SkillMetadataModel(
            name=self.name,
            description=self.description,
            source_path=self.source_path,
            license=self.license,
            compatibility=self.compatibility,
            metadata=self.metadata,
            allowed_tools=self.allowed_tools,
        )

    def get_resources(self) -> dict[str, str]:
        """
        List available resource files in the skill directory.

        Returns a mapping of relative file paths to their full paths.
        Does not include SKILL.md itself. Results are cached.

        Returns:
            Dictionary mapping relative paths to absolute paths
        """
        if self._resources_cache is not None:
            return self._resources_cache

        resources: dict[str, str] = {}
        skill_dir = Path(self.source_path)

        if not skill_dir.exists():
            self._resources_cache = resources
            return resources

        # Walk the skill directory
        for path in skill_dir.rglob("*"):
            if path.is_file() and path.name.upper() != "SKILL.MD":
                relative = str(path.relative_to(skill_dir))
                resources[relative] = str(path)

        self._resources_cache = resources
        return resources

    def read_resource(self, relative_path: str) -> str | None:
        """
        Read content of a bundled resource file.

        Args:
            relative_path: Path relative to skill directory

        Returns:
            File content as string, or None if file not found
        """
        resources = self.get_resources()

        # Normalize path separators
        normalized_path = relative_path.replace("\\", "/")

        if normalized_path not in resources:
            # Try with original path
            if relative_path in resources:
                normalized_path = relative_path
            else:
                return None

        try:
            full_path = Path(resources[normalized_path])
            return full_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def has_resource(self, relative_path: str) -> bool:
        """
        Check if a resource exists.

        Args:
            relative_path: Path relative to skill directory

        Returns:
            True if resource exists
        """
        resources = self.get_resources()
        normalized_path = relative_path.replace("\\", "/")
        return normalized_path in resources or relative_path in resources

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "source_path": self.source_path,
            "license": self.license,
            "compatibility": self.compatibility,
            "metadata": self.metadata,
            "allowed_tools": self.allowed_tools,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Skill:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            instructions=data.get("instructions", ""),
            source_path=data.get("source_path", ""),
            license=_normalize_optional_str(data.get("license")),
            compatibility=_normalize_optional_str(data.get("compatibility")),
            metadata=data.get("metadata"),
            allowed_tools=_normalize_optional_str(data.get("allowed_tools")),
        )

    @classmethod
    def from_metadata(cls, metadata: SkillMetadataModel, instructions: str) -> Skill:
        """
        Create a full skill from metadata and instructions.

        Args:
            metadata: Skill metadata object
            instructions: SKILL.md body content

        Returns:
            Full Skill object
        """
        return cls(
            name=metadata.name,
            description=metadata.description,
            instructions=instructions,
            source_path=metadata.source_path,
            license=metadata.license,
            compatibility=metadata.compatibility,
            metadata=metadata.metadata,
            allowed_tools=metadata.allowed_tools,
        )


@dataclass
class SkillContext:
    """
    Manages active skill context during execution.

    Tracks which skills are currently active and provides
    combined instructions from all active skills.

    Attributes:
        active_skills: Dictionary of active skills by name
    """

    active_skills: dict[str, Skill] = field(default_factory=dict)

    def activate_skill(self, skill: Skill) -> None:
        """
        Activate a skill for the current execution context.

        Args:
            skill: The skill to activate
        """
        self.active_skills[skill.name] = skill

    def deactivate_skill(self, name: str) -> None:
        """
        Deactivate a skill from the current context.

        Args:
            name: Name of the skill to deactivate
        """
        self.active_skills.pop(name, None)

    def get_active_skills(self) -> list[Skill]:
        """
        Get list of currently active skills.

        Returns:
            List of active skill objects
        """
        return list(self.active_skills.values())

    def is_active(self, name: str) -> bool:
        """
        Check if a skill is currently active.

        Args:
            name: Skill name

        Returns:
            True if skill is active
        """
        return name in self.active_skills

    def get_combined_instructions(self) -> str:
        """
        Get combined instructions from all active skills.

        Returns:
            Concatenated instructions from all active skills,
            separated by skill headers.
        """
        if not self.active_skills:
            return ""

        parts = []
        for skill in self.active_skills.values():
            parts.append(f"## Skill: {skill.name}\n\n{skill.instructions}")

        return "\n\n---\n\n".join(parts)

    def read_skill_resource(self, skill_name: str, resource_path: str) -> str | None:
        """
        Read a resource from an active skill.

        Args:
            skill_name: Name of the skill
            resource_path: Relative path to the resource

        Returns:
            Resource content, or None if skill not active or resource not found
        """
        skill = self.active_skills.get(skill_name)
        if not skill:
            return None
        return skill.read_resource(resource_path)

    def clear(self) -> None:
        """Deactivate all skills."""
        self.active_skills.clear()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "active_skills": [skill.name for skill in self.active_skills.values()]
        }
