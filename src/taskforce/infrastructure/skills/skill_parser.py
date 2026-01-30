"""
Skill Markdown Parser

Parses SKILL.md files with YAML frontmatter:
- Required: name, description in frontmatter
- Body: Instructions and documentation
"""

import re
from pathlib import Path
from typing import Any

import yaml

from taskforce.core.domain.skill import (
    ALLOWED_TOOLS_PATTERN,
    MAX_COMPATIBILITY_LENGTH,
    Skill,
    SkillMetadataModel,
    SkillValidationError,
)


class SkillParseError(Exception):
    """Raised when skill parsing fails."""

    pass


def parse_skill_markdown(
    content: str,
    source_path: str,
) -> Skill:
    """
    Parse a SKILL.md file into a Skill object.

    Format:
        ---
        name: skill-name
        description: What the skill does and when to use it
        ---

        # Skill Name

        Instructions and documentation...

    Args:
        content: SKILL.md file content
        source_path: Absolute path to skill directory

    Returns:
        Skill instance with full content

    Raises:
        SkillParseError: If parsing fails
        SkillValidationError: If validation fails
    """
    frontmatter, body = _extract_frontmatter(content)

    # Validate required fields
    if "name" not in frontmatter:
        raise SkillParseError("SKILL.md missing required 'name' in frontmatter")

    if "description" not in frontmatter:
        raise SkillParseError("SKILL.md missing required 'description' in frontmatter")

    name = str(frontmatter["name"]).strip()
    description = str(frontmatter["description"]).strip()
    _validate_name_matches_directory(name, source_path)
    license_text = _parse_optional_string(frontmatter, "license")
    compatibility = _parse_optional_string(
        frontmatter,
        "compatibility",
        max_length=MAX_COMPATIBILITY_LENGTH,
    )
    metadata = _parse_metadata_dict(frontmatter)
    allowed_tools = _parse_allowed_tools(frontmatter)
    instructions = body.strip()

    # Create and return skill (validation happens in __post_init__)
    try:
        return Skill(
            name=name,
            description=description,
            instructions=instructions,
            source_path=source_path,
            license=license_text,
            compatibility=compatibility,
            metadata=metadata,
            allowed_tools=allowed_tools,
        )
    except SkillValidationError as e:
        raise SkillParseError(f"Skill validation failed: {e}") from e


def parse_skill_metadata(
    content: str,
    source_path: str,
) -> SkillMetadataModel:
    """
    Parse only the metadata from a SKILL.md file.

    This is a lightweight parse that doesn't load the full instructions,
    suitable for skill discovery.

    Args:
        content: SKILL.md file content
        source_path: Absolute path to skill directory

    Returns:
        SkillMetadataModel with name and description

    Raises:
        SkillParseError: If parsing fails
    """
    frontmatter, _ = _extract_frontmatter(content)

    if "name" not in frontmatter:
        raise SkillParseError("SKILL.md missing required 'name' in frontmatter")

    if "description" not in frontmatter:
        raise SkillParseError("SKILL.md missing required 'description' in frontmatter")

    name = str(frontmatter["name"]).strip()
    description = str(frontmatter["description"]).strip()
    _validate_name_matches_directory(name, source_path)
    license_text = _parse_optional_string(frontmatter, "license")
    compatibility = _parse_optional_string(
        frontmatter,
        "compatibility",
        max_length=MAX_COMPATIBILITY_LENGTH,
    )
    metadata = _parse_metadata_dict(frontmatter)
    allowed_tools = _parse_allowed_tools(frontmatter)

    try:
        return SkillMetadataModel(
            name=name,
            description=description,
            source_path=source_path,
            license=license_text,
            compatibility=compatibility,
            metadata=metadata,
            allowed_tools=allowed_tools,
        )
    except SkillValidationError as e:
        raise SkillParseError(f"Skill metadata validation failed: {e}") from e


def _extract_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Extract YAML frontmatter from Markdown content.

    The frontmatter is delimited by --- at the start and end.

    Args:
        content: Full markdown content

    Returns:
        Tuple of (frontmatter_dict, body_content)

    Raises:
        SkillParseError: If frontmatter is missing or invalid
    """
    # Match frontmatter pattern: starts with ---, ends with ---
    # The content must start with --- (allowing for leading whitespace)
    content = content.strip()

    pattern = r"^---\s*\n(.*?)\n---\s*\n?(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        raise SkillParseError(
            "SKILL.md must start with YAML frontmatter (--- delimited)"
        )

    frontmatter_yaml = match.group(1)
    body = match.group(2)

    try:
        frontmatter = yaml.safe_load(frontmatter_yaml)
        if frontmatter is None:
            frontmatter = {}
        if not isinstance(frontmatter, dict):
            raise SkillParseError("Frontmatter must be a YAML dictionary")
    except yaml.YAMLError as e:
        raise SkillParseError(f"Invalid YAML in frontmatter: {e}") from e

    return frontmatter, body


def _parse_optional_string(
    frontmatter: dict[str, Any],
    field_name: str,
    max_length: int | None = None,
) -> str | None:
    if field_name not in frontmatter or frontmatter[field_name] is None:
        return None
    value = frontmatter[field_name]
    if not isinstance(value, str):
        raise SkillParseError(f"Frontmatter '{field_name}' must be a string")
    cleaned = value.strip()
    if not cleaned:
        return None
    if max_length is not None and len(cleaned) > max_length:
        raise SkillParseError(
            f"Frontmatter '{field_name}' exceeds {max_length} characters"
        )
    return cleaned


def _parse_metadata_dict(frontmatter: dict[str, Any]) -> dict[str, str] | None:
    if "metadata" not in frontmatter or frontmatter["metadata"] is None:
        return None
    value = frontmatter["metadata"]
    if not isinstance(value, dict):
        raise SkillParseError("Frontmatter 'metadata' must be a dictionary")
    metadata: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise SkillParseError("Frontmatter 'metadata' must map strings to strings")
        metadata[key] = item
    return metadata


def _parse_allowed_tools(frontmatter: dict[str, Any]) -> str | None:
    allowed_tools = None
    if "allowed-tools" in frontmatter:
        allowed_tools = _parse_optional_string(frontmatter, "allowed-tools")
    elif "allowed_tools" in frontmatter:
        allowed_tools = _parse_optional_string(frontmatter, "allowed_tools")
    if allowed_tools is None:
        return None
    if not ALLOWED_TOOLS_PATTERN.match(allowed_tools):
        raise SkillParseError("Frontmatter 'allowed-tools' must be space-delimited")
    return allowed_tools


def _validate_name_matches_directory(name: str, source_path: str) -> None:
    if not source_path:
        return
    directory_name = Path(source_path).name
    if directory_name != name:
        raise SkillParseError(
            f"Skill name '{name}' does not match directory name '{directory_name}'"
        )


def validate_skill_file(skill_path: str) -> tuple[bool, str | None]:
    """
    Validate a SKILL.md file without fully parsing it.

    Args:
        skill_path: Path to SKILL.md file

    Returns:
        Tuple of (is_valid, error_message)
    """
    from pathlib import Path

    path = Path(skill_path)

    if not path.exists():
        return False, f"File not found: {skill_path}"

    if not path.is_file():
        return False, f"Not a file: {skill_path}"

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return False, f"Cannot read file: {e}"

    try:
        parse_skill_metadata(content, str(path.parent))
        return True, None
    except (SkillParseError, SkillValidationError) as e:
        return False, str(e)
