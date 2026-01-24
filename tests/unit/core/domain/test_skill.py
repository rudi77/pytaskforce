"""
Tests for Skill Domain Models

Tests the Skill, SkillMetadataModel, and SkillContext domain models.
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from taskforce.core.domain.skill import (
    Skill,
    SkillContext,
    SkillMetadataModel,
    SkillValidationError,
    validate_skill_name,
    validate_skill_description,
)


class TestSkillValidation:
    """Tests for skill validation functions."""

    def test_validate_skill_name_valid(self):
        """Valid skill names should pass validation."""
        valid_names = [
            "code-review",
            "data-analysis",
            "pdf-processing",
            "a",
            "a-b-c",
            "skill123",
        ]
        for name in valid_names:
            is_valid, error = validate_skill_name(name)
            assert is_valid, f"Expected '{name}' to be valid, got error: {error}"

    def test_validate_skill_name_invalid(self):
        """Invalid skill names should fail validation."""
        invalid_cases = [
            ("", "empty"),
            ("Code-Review", "uppercase"),
            ("code_review", "underscore"),
            ("code review", "space"),
            ("123skill", "starts with number"),
            ("-skill", "starts with hyphen"),
            ("a" * 65, "too long"),
            ("my-anthropic-skill", "reserved word"),
            ("claude-helper", "reserved word"),
        ]
        for name, reason in invalid_cases:
            is_valid, _ = validate_skill_name(name)
            assert not is_valid, f"Expected '{name}' to be invalid ({reason})"

    def test_validate_skill_description_valid(self):
        """Valid descriptions should pass validation."""
        valid_descriptions = [
            "A simple skill description.",
            "This skill does X when Y happens.",
            "a" * 1024,  # Max length
        ]
        for desc in valid_descriptions:
            is_valid, error = validate_skill_description(desc)
            assert is_valid, f"Expected description to be valid, got: {error}"

    def test_validate_skill_description_invalid(self):
        """Invalid descriptions should fail validation."""
        invalid_cases = [
            ("", "empty"),
            ("   ", "whitespace only"),
            ("a" * 1025, "too long"),
            ("<script>alert(1)</script>", "xml tags"),
        ]
        for desc, reason in invalid_cases:
            is_valid, _ = validate_skill_description(desc)
            assert not is_valid, f"Expected description to be invalid ({reason})"


class TestSkillMetadataModel:
    """Tests for SkillMetadataModel."""

    def test_create_valid_metadata(self):
        """Creating metadata with valid inputs should work."""
        metadata = SkillMetadataModel(
            name="code-review",
            description="Review code for issues.",
            source_path="/path/to/skill",
        )
        assert metadata.name == "code-review"
        assert metadata.description == "Review code for issues."
        assert metadata.source_path == "/path/to/skill"

    def test_create_invalid_name_raises(self):
        """Creating metadata with invalid name should raise SkillValidationError."""
        with pytest.raises(SkillValidationError):
            SkillMetadataModel(
                name="Invalid Name",
                description="Valid description.",
                source_path="/path",
            )

    def test_create_invalid_description_raises(self):
        """Creating metadata with invalid description should raise SkillValidationError."""
        with pytest.raises(SkillValidationError):
            SkillMetadataModel(
                name="valid-name",
                description="",
                source_path="/path",
            )

    def test_to_dict(self):
        """Metadata should serialize to dictionary correctly."""
        metadata = SkillMetadataModel(
            name="test-skill",
            description="Test description.",
            source_path="/test/path",
        )
        result = metadata.to_dict()
        assert result == {
            "name": "test-skill",
            "description": "Test description.",
            "source_path": "/test/path",
        }

    def test_from_dict(self):
        """Metadata should deserialize from dictionary correctly."""
        data = {
            "name": "test-skill",
            "description": "Test description.",
            "source_path": "/test/path",
        }
        metadata = SkillMetadataModel.from_dict(data)
        assert metadata.name == "test-skill"
        assert metadata.description == "Test description."


class TestSkill:
    """Tests for Skill domain model."""

    def test_create_valid_skill(self):
        """Creating skill with valid inputs should work."""
        skill = Skill(
            name="code-review",
            description="Review code for issues.",
            instructions="# Code Review\n\nInstructions here...",
            source_path="/path/to/skill",
        )
        assert skill.name == "code-review"
        assert skill.description == "Review code for issues."
        assert skill.instructions.startswith("# Code Review")

    def test_skill_metadata_property(self):
        """Skill should provide metadata property."""
        skill = Skill(
            name="test-skill",
            description="Test description.",
            instructions="Instructions",
            source_path="/path",
        )
        metadata = skill.metadata
        assert isinstance(metadata, SkillMetadataModel)
        assert metadata.name == skill.name
        assert metadata.description == skill.description

    def test_get_resources_with_files(self):
        """Skill should list resource files in directory."""
        with TemporaryDirectory() as tmpdir:
            # Create skill structure
            skill_dir = Path(tmpdir)
            (skill_dir / "SKILL.md").write_text("# Skill")
            (skill_dir / "REFERENCE.md").write_text("# Reference")
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "helper.py").write_text("# Python script")

            skill = Skill(
                name="test-skill",
                description="Test",
                instructions="# Test",
                source_path=str(skill_dir),
            )

            resources = skill.get_resources()
            assert "REFERENCE.md" in resources
            assert "scripts/helper.py" in resources
            assert "SKILL.md" not in resources  # SKILL.md excluded

    def test_read_resource(self):
        """Skill should read resource file content."""
        with TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            (skill_dir / "REFERENCE.md").write_text("# Reference Content")

            skill = Skill(
                name="test-skill",
                description="Test",
                instructions="# Test",
                source_path=str(skill_dir),
            )

            content = skill.read_resource("REFERENCE.md")
            assert content == "# Reference Content"

    def test_read_resource_not_found(self):
        """Reading non-existent resource should return None."""
        skill = Skill(
            name="test-skill",
            description="Test",
            instructions="# Test",
            source_path="/nonexistent",
        )
        result = skill.read_resource("missing.md")
        assert result is None

    def test_has_resource(self):
        """has_resource should check resource existence."""
        with TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            (skill_dir / "EXISTS.md").write_text("content")

            skill = Skill(
                name="test-skill",
                description="Test",
                instructions="# Test",
                source_path=str(skill_dir),
            )

            assert skill.has_resource("EXISTS.md")
            assert not skill.has_resource("MISSING.md")

    def test_to_dict_and_from_dict(self):
        """Skill should serialize and deserialize correctly."""
        original = Skill(
            name="test-skill",
            description="Test description.",
            instructions="# Instructions",
            source_path="/path/to/skill",
        )

        data = original.to_dict()
        restored = Skill.from_dict(data)

        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.instructions == original.instructions
        assert restored.source_path == original.source_path


class TestSkillContext:
    """Tests for SkillContext."""

    def test_activate_skill(self):
        """Activating skill should add it to context."""
        context = SkillContext()
        skill = Skill(
            name="test-skill",
            description="Test",
            instructions="Instructions",
            source_path="/path",
        )

        context.activate_skill(skill)

        assert context.is_active("test-skill")
        assert len(context.get_active_skills()) == 1

    def test_deactivate_skill(self):
        """Deactivating skill should remove it from context."""
        context = SkillContext()
        skill = Skill(
            name="test-skill",
            description="Test",
            instructions="Instructions",
            source_path="/path",
        )

        context.activate_skill(skill)
        context.deactivate_skill("test-skill")

        assert not context.is_active("test-skill")
        assert len(context.get_active_skills()) == 0

    def test_get_combined_instructions(self):
        """Combined instructions should include all active skills."""
        context = SkillContext()

        skill1 = Skill(
            name="skill-one",
            description="First skill",
            instructions="# Skill One Instructions",
            source_path="/path1",
        )
        skill2 = Skill(
            name="skill-two",
            description="Second skill",
            instructions="# Skill Two Instructions",
            source_path="/path2",
        )

        context.activate_skill(skill1)
        context.activate_skill(skill2)

        combined = context.get_combined_instructions()

        assert "## Skill: skill-one" in combined
        assert "# Skill One Instructions" in combined
        assert "## Skill: skill-two" in combined
        assert "# Skill Two Instructions" in combined

    def test_read_skill_resource(self):
        """Context should read resources from active skills."""
        with TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            (skill_dir / "REFERENCE.md").write_text("Resource content")

            context = SkillContext()
            skill = Skill(
                name="test-skill",
                description="Test",
                instructions="# Test",
                source_path=str(skill_dir),
            )
            context.activate_skill(skill)

            content = context.read_skill_resource("test-skill", "REFERENCE.md")
            assert content == "Resource content"

    def test_read_skill_resource_inactive_skill(self):
        """Reading from inactive skill should return None."""
        context = SkillContext()
        result = context.read_skill_resource("nonexistent", "file.md")
        assert result is None

    def test_clear(self):
        """Clear should deactivate all skills."""
        context = SkillContext()
        skill = Skill(
            name="test-skill",
            description="Test",
            instructions="Instructions",
            source_path="/path",
        )

        context.activate_skill(skill)
        context.clear()

        assert len(context.get_active_skills()) == 0

    def test_to_dict(self):
        """Context should serialize active skill names."""
        context = SkillContext()
        skill = Skill(
            name="test-skill",
            description="Test",
            instructions="Instructions",
            source_path="/path",
        )
        context.activate_skill(skill)

        result = context.to_dict()
        assert result == {"active_skills": ["test-skill"]}
