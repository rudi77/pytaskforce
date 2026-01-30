"""
Tests for Skill Parser

Tests the SKILL.md parsing functionality.
"""

import pytest

from taskforce.core.domain.skill import Skill, SkillMetadataModel, SkillValidationError
from taskforce.infrastructure.skills.skill_parser import (
    SkillParseError,
    parse_skill_markdown,
    parse_skill_metadata,
    validate_skill_file,
)


class TestParseSkillMarkdown:
    """Tests for parse_skill_markdown function."""

    def test_parse_valid_skill(self):
        """Valid SKILL.md content should parse correctly."""
        content = """---
name: test-skill
description: This is a test skill for unit testing.
---

# Test Skill

This is the instructions section.

## Section 1

More instructions here.
"""
        skill = parse_skill_markdown(content, "/path/to/test-skill")

        assert skill.name == "test-skill"
        assert skill.description == "This is a test skill for unit testing."
        assert "# Test Skill" in skill.instructions
        assert "## Section 1" in skill.instructions
        assert skill.source_path == "/path/to/test-skill"

    def test_parse_minimal_skill(self):
        """Minimal valid SKILL.md should parse correctly."""
        content = """---
name: minimal
description: Minimal skill.
---

Instructions.
"""
        skill = parse_skill_markdown(content, "/path/minimal")

        assert skill.name == "minimal"
        assert skill.description == "Minimal skill."
        assert skill.instructions == "Instructions."

    def test_parse_missing_name_raises(self):
        """Missing name field should raise SkillParseError."""
        content = """---
description: No name field.
---

Instructions.
"""
        with pytest.raises(SkillParseError) as exc_info:
            parse_skill_markdown(content, "/path/test-skill")

        assert "name" in str(exc_info.value).lower()

    def test_parse_missing_description_raises(self):
        """Missing description field should raise SkillParseError."""
        content = """---
name: test-skill
---

Instructions.
"""
        with pytest.raises(SkillParseError) as exc_info:
            parse_skill_markdown(content, "/path/test-skill")

        assert "description" in str(exc_info.value).lower()

    def test_parse_missing_frontmatter_raises(self):
        """Content without frontmatter should raise SkillParseError."""
        content = """# Just a Markdown file

No frontmatter here.
"""
        with pytest.raises(SkillParseError) as exc_info:
            parse_skill_markdown(content, "/path/test-skill")

        assert "frontmatter" in str(exc_info.value).lower()

    def test_parse_invalid_yaml_raises(self):
        """Invalid YAML in frontmatter should raise SkillParseError."""
        content = """---
name: test
description: test
invalid yaml: [unclosed bracket
---

Instructions.
"""
        with pytest.raises(SkillParseError) as exc_info:
            parse_skill_markdown(content, "/path/test")

        assert "yaml" in str(exc_info.value).lower()

    def test_parse_invalid_name_raises(self):
        """Invalid skill name should raise SkillParseError."""
        content = """---
name: invalid--name
description: Description.
---

Instructions.
"""
        with pytest.raises(SkillParseError) as exc_info:
            parse_skill_markdown(content, "/path/invalid--name")

        assert "validation" in str(exc_info.value).lower()

    def test_parse_empty_body_allowed(self):
        """Empty body (instructions) should be allowed."""
        content = """---
name: empty-body
description: A skill with no instructions.
---
"""
        skill = parse_skill_markdown(content, "/path/empty-body")

        assert skill.name == "empty-body"
        assert skill.instructions == ""

    def test_parse_preserves_internal_whitespace(self):
        """Internal whitespace in instructions should be preserved."""
        content = """---
name: whitespace
description: Test whitespace preservation.
---

First line.

    Indented text.

        More indented.
"""
        skill = parse_skill_markdown(content, "/path/whitespace")

        # Body is stripped of leading/trailing whitespace, but internal whitespace preserved
        assert "First line." in skill.instructions
        assert "    Indented text." in skill.instructions
        assert "        More indented." in skill.instructions

    def test_parse_name_mismatch_raises(self):
        """Mismatched directory name should raise SkillParseError."""
        content = """---
name: mismatched
description: Mismatch test.
---

Instructions.
"""
        with pytest.raises(SkillParseError) as exc_info:
            parse_skill_markdown(content, "/path/expected-name")

        assert "directory name" in str(exc_info.value).lower()


class TestParseSkillMetadata:
    """Tests for parse_skill_metadata function."""

    def test_parse_metadata_valid(self):
        """Valid content should return metadata without loading body."""
        content = """---
name: test-skill
description: Test description.
---

# Instructions that should not be loaded
"""
        metadata = parse_skill_metadata(content, "/path/test-skill")

        assert isinstance(metadata, SkillMetadataModel)
        assert metadata.name == "test-skill"
        assert metadata.description == "Test description."
        assert metadata.source_path == "/path/test-skill"

    def test_parse_metadata_missing_name(self):
        """Missing name should raise SkillParseError."""
        content = """---
description: No name.
---

Content.
"""
        with pytest.raises(SkillParseError):
            parse_skill_metadata(content, "/path/test")

    def test_parse_metadata_missing_description(self):
        """Missing description should raise SkillParseError."""
        content = """---
name: test
---

Content.
"""
        with pytest.raises(SkillParseError):
            parse_skill_metadata(content, "/path/test")

    def test_parse_metadata_name_mismatch(self):
        """Mismatched directory name should raise SkillParseError."""
        content = """---
name: mismatched
description: Mismatch.
---
"""
        with pytest.raises(SkillParseError) as exc_info:
            parse_skill_metadata(content, "/path/expected-name")

        assert "directory name" in str(exc_info.value).lower()


class TestValidateSkillFile:
    """Tests for validate_skill_file function."""

    def test_validate_nonexistent_file(self):
        """Non-existent file should fail validation."""
        is_valid, error = validate_skill_file("/nonexistent/path/SKILL.md")

        assert not is_valid
        assert "not found" in error.lower()

    def test_validate_valid_file(self, tmp_path):
        """Valid SKILL.md file should pass validation."""
        skill_dir = tmp_path / "valid-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("""---
name: valid-skill
description: Valid skill description.
---

Instructions.
""")
        is_valid, error = validate_skill_file(str(skill_file))

        assert is_valid
        assert error is None

    def test_validate_invalid_content(self, tmp_path):
        """Invalid content should fail validation."""
        skill_dir = tmp_path / "invalid-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("Just plain text, no frontmatter.")

        is_valid, error = validate_skill_file(str(skill_file))

        assert not is_valid
        assert error is not None
