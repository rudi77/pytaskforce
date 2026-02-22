"""
Tests for Skill Registry

Tests the FileSkillRegistry implementation.
"""


import pytest

from taskforce.core.domain.skill import Skill, SkillMetadataModel
from taskforce.infrastructure.skills.skill_registry import (
    FileSkillRegistry,
    create_skill_registry,
)


@pytest.fixture
def skill_directory(tmp_path):
    """Create a temporary directory structure with skills."""
    # Create skill 1
    skill1_dir = tmp_path / "code-review"
    skill1_dir.mkdir()
    (skill1_dir / "SKILL.md").write_text("""---
name: code-review
description: Review code for bugs and improvements.
---

# Code Review

Review instructions here.
""")

    # Create skill 2
    skill2_dir = tmp_path / "data-analysis"
    skill2_dir.mkdir()
    (skill2_dir / "SKILL.md").write_text("""---
name: data-analysis
description: Analyze data and create visualizations.
---

# Data Analysis

Analysis instructions here.
""")

    return tmp_path


class TestFileSkillRegistry:
    """Tests for FileSkillRegistry class."""

    def test_init_discovers_skills(self, skill_directory):
        """Registry should discover skills on init."""
        registry = FileSkillRegistry(
            skill_directories=[str(skill_directory)],
            auto_discover=True,
        )

        assert registry.get_skill_count() == 2

    def test_init_no_auto_discover(self, skill_directory):
        """Registry without auto_discover should be empty initially."""
        registry = FileSkillRegistry(
            skill_directories=[str(skill_directory)],
            auto_discover=False,
        )

        assert registry.get_skill_count() == 0

    def test_refresh(self, skill_directory):
        """Refresh should re-discover skills."""
        registry = FileSkillRegistry(
            skill_directories=[str(skill_directory)],
            auto_discover=False,
        )

        assert registry.get_skill_count() == 0

        registry.refresh()

        assert registry.get_skill_count() == 2

    def test_list_skills(self, skill_directory):
        """List skills should return sorted skill names."""
        registry = FileSkillRegistry([str(skill_directory)])

        skills = registry.list_skills()

        assert skills == ["code-review", "data-analysis"]

    def test_has_skill(self, skill_directory):
        """has_skill should check skill existence."""
        registry = FileSkillRegistry([str(skill_directory)])

        assert registry.has_skill("code-review")
        assert registry.has_skill("data-analysis")
        assert not registry.has_skill("nonexistent")

    def test_get_skill_metadata(self, skill_directory):
        """get_skill_metadata should return metadata without loading full skill."""
        registry = FileSkillRegistry([str(skill_directory)])

        metadata = registry.get_skill_metadata("code-review")

        assert metadata is not None
        assert isinstance(metadata, SkillMetadataModel)
        assert metadata.name == "code-review"
        assert "bugs" in metadata.description.lower()

    def test_get_skill_metadata_not_found(self, skill_directory):
        """get_skill_metadata should return None for unknown skill."""
        registry = FileSkillRegistry([str(skill_directory)])

        metadata = registry.get_skill_metadata("nonexistent")

        assert metadata is None

    def test_get_skill(self, skill_directory):
        """get_skill should return full skill with instructions."""
        registry = FileSkillRegistry([str(skill_directory)])

        skill = registry.get_skill("code-review")

        assert skill is not None
        assert isinstance(skill, Skill)
        assert skill.name == "code-review"
        assert "Review instructions" in skill.instructions

    def test_get_skill_caches(self, skill_directory):
        """get_skill should cache loaded skills."""
        registry = FileSkillRegistry([str(skill_directory)])

        skill1 = registry.get_skill("code-review")
        skill2 = registry.get_skill("code-review")

        # Should be the same object (cached)
        assert skill1 is skill2

    def test_get_skill_not_found(self, skill_directory):
        """get_skill should return None for unknown skill."""
        registry = FileSkillRegistry([str(skill_directory)])

        skill = registry.get_skill("nonexistent")

        assert skill is None

    def test_get_all_metadata(self, skill_directory):
        """get_all_metadata should return sorted metadata list."""
        registry = FileSkillRegistry([str(skill_directory)])

        metadata_list = registry.get_all_metadata()

        assert len(metadata_list) == 2
        assert metadata_list[0].name == "code-review"  # Sorted alphabetically
        assert metadata_list[1].name == "data-analysis"

    def test_iter_skills(self, skill_directory):
        """iter_skills should iterate over all skills."""
        registry = FileSkillRegistry([str(skill_directory)])

        skills = list(registry.iter_skills())

        assert len(skills) == 2
        assert all(isinstance(s, Skill) for s in skills)

    def test_get_skills_for_prompt(self, skill_directory):
        """get_skills_for_prompt should return formatted skill list."""
        registry = FileSkillRegistry([str(skill_directory)])

        prompt_section = registry.get_skills_for_prompt()

        assert "Available Skills:" in prompt_section
        assert "code-review:" in prompt_section
        assert "data-analysis:" in prompt_section

    def test_get_skills_for_prompt_empty(self, tmp_path):
        """get_skills_for_prompt should return empty string when no skills."""
        registry = FileSkillRegistry([str(tmp_path)])

        prompt_section = registry.get_skills_for_prompt()

        assert prompt_section == ""

    def test_add_directory(self, skill_directory, tmp_path):
        """add_directory should add new directory and discover skills."""
        # Create a new skill in different directory
        new_dir = tmp_path / "new-skills"
        new_dir.mkdir()
        new_skill_dir = new_dir / "new-skill"
        new_skill_dir.mkdir()
        (new_skill_dir / "SKILL.md").write_text("""---
name: new-skill
description: A new skill.
---

New skill instructions.
""")

        registry = FileSkillRegistry([str(skill_directory)])
        assert registry.get_skill_count() == 2

        registry.add_directory(new_dir)

        assert registry.get_skill_count() == 3
        assert registry.has_skill("new-skill")

    def test_clear_skill_cache(self, skill_directory):
        """clear_skill_cache should remove cached skills."""
        registry = FileSkillRegistry([str(skill_directory)])

        # Load skill to cache it
        skill = registry.get_skill("code-review")
        assert skill is not None

        # Clear specific skill cache
        registry.clear_skill_cache("code-review")

        # Loading again should create new object
        skill2 = registry.get_skill("code-review")
        assert skill is not skill2  # Different object

    def test_clear_all_skill_cache(self, skill_directory):
        """clear_skill_cache without name should clear all caches."""
        registry = FileSkillRegistry([str(skill_directory)])

        # Load skills to cache them
        registry.get_skill("code-review")
        registry.get_skill("data-analysis")

        registry.clear_skill_cache()

        # Internal cache should be empty
        # (Note: this tests internal state, which is not ideal but useful here)
        assert len(registry._skill_cache) == 0


class TestCreateSkillRegistry:
    """Tests for create_skill_registry function."""

    def test_create_with_defaults(self):
        """create_skill_registry with defaults should work."""
        registry = create_skill_registry()

        # Just verify the registry is created properly
        # Default directories may not exist on the test system
        assert isinstance(registry, FileSkillRegistry)

    def test_create_with_additional_directories(self, skill_directory):
        """create_skill_registry should include additional directories."""
        registry = create_skill_registry(
            additional_directories=[str(skill_directory)],
            include_defaults=False,  # Don't include defaults to avoid non-existent dirs
        )

        assert skill_directory in registry.directories

    def test_create_without_defaults(self, skill_directory):
        """create_skill_registry without defaults should only use provided dirs."""
        registry = create_skill_registry(
            additional_directories=[str(skill_directory)],
            include_defaults=False,
        )

        # Only the provided directory should be included
        assert len(registry.directories) == 1
        assert registry.directories[0] == skill_directory
