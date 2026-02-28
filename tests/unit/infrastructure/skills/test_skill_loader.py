"""
Tests for Skill Loader

Tests the SkillLoader filesystem-based skill loading.
"""


import pytest

from taskforce.core.domain.skill import Skill
from taskforce.infrastructure.skills.skill_loader import (
    SkillLoader,
    get_default_skill_directories,
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
    (skill1_dir / "REFERENCE.md").write_text("# Reference Documentation")

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

    # Create an invalid skill (missing required field)
    invalid_dir = tmp_path / "invalid-skill"
    invalid_dir.mkdir()
    (invalid_dir / "SKILL.md").write_text("""---
name: invalid
---

Missing description.
""")

    return tmp_path


class TestSkillLoader:
    """Tests for SkillLoader class."""

    def test_init_with_directories(self, skill_directory):
        """Loader should accept directory list."""
        loader = SkillLoader([str(skill_directory)])

        assert len(loader.directories) == 1
        assert loader.directories[0] == skill_directory

    def test_init_with_nonexistent_directory(self, tmp_path):
        """Loader should skip non-existent directories."""
        loader = SkillLoader([str(tmp_path / "nonexistent")])

        assert len(loader.directories) == 0

    def test_add_directory(self, tmp_path):
        """Adding valid directory should work."""
        loader = SkillLoader([])

        result = loader.add_directory(tmp_path)

        assert result is True
        assert tmp_path in loader.directories

    def test_add_nonexistent_directory(self):
        """Adding non-existent directory should return False."""
        loader = SkillLoader([])

        result = loader.add_directory("/nonexistent/path")

        assert result is False
        assert len(loader.directories) == 0

    def test_discover_skill_directories(self, skill_directory):
        """Should discover all directories containing SKILL.md."""
        loader = SkillLoader([str(skill_directory)])

        skill_dirs = list(loader.discover_skill_directories())

        # Should find code-review, data-analysis, and invalid-skill
        assert len(skill_dirs) == 3
        skill_names = {d.name for d in skill_dirs}
        assert "code-review" in skill_names
        assert "data-analysis" in skill_names

    def test_discover_metadata(self, skill_directory):
        """Should discover metadata from valid skills only."""
        loader = SkillLoader([str(skill_directory)])

        metadata_list = loader.discover_metadata()

        # Should only find 2 valid skills (not the invalid one)
        assert len(metadata_list) == 2
        names = {m.name for m in metadata_list}
        assert "code-review" in names
        assert "data-analysis" in names

    def test_load_skill(self, skill_directory):
        """Loading valid skill should return Skill object."""
        loader = SkillLoader([str(skill_directory)])
        skill_dir = skill_directory / "code-review"

        skill = loader.load_skill(skill_dir)

        assert skill is not None
        assert isinstance(skill, Skill)
        assert skill.name == "code-review"
        assert "Review instructions here" in skill.instructions

    def test_load_skill_invalid_directory(self):
        """Loading from invalid directory should return None."""
        loader = SkillLoader([])

        skill = loader.load_skill("/nonexistent/path")

        assert skill is None

    def test_load_skill_by_name(self, skill_directory):
        """Loading skill by name should work."""
        loader = SkillLoader([str(skill_directory)])

        skill = loader.load_skill_by_name("data-analysis")

        assert skill is not None
        assert skill.name == "data-analysis"

    def test_load_skill_by_name_not_found(self, skill_directory):
        """Loading non-existent skill should return None."""
        loader = SkillLoader([str(skill_directory)])

        skill = loader.load_skill_by_name("nonexistent-skill")

        assert skill is None

    def test_load_all_skills(self, skill_directory):
        """Load all skills should return list of valid skills."""
        loader = SkillLoader([str(skill_directory)])

        skills = loader.load_all_skills()

        # Should load 2 valid skills
        assert len(skills) == 2
        names = {s.name for s in skills}
        assert "code-review" in names
        assert "data-analysis" in names

    def test_get_skill_path(self, skill_directory):
        """Getting skill path by name should work."""
        loader = SkillLoader([str(skill_directory)])

        path = loader.get_skill_path("code-review")

        assert path is not None
        assert path.name == "code-review"
        assert (path / "SKILL.md").exists()

    def test_get_skill_path_not_found(self, skill_directory):
        """Getting path for non-existent skill should return None."""
        loader = SkillLoader([str(skill_directory)])

        path = loader.get_skill_path("nonexistent")

        assert path is None


class TestGetDefaultSkillDirectories:
    """Tests for get_default_skill_directories function."""

    def test_returns_list(self):
        """Should return a list of directory paths."""
        directories = get_default_skill_directories()

        assert isinstance(directories, list)
        assert len(directories) >= 2  # User and project directories

    def test_includes_user_directory(self):
        """Should include user skills directory."""
        directories = get_default_skill_directories()

        assert any(
            ".taskforce" in d and "skills" in d
            for d in directories
        )

    def test_includes_project_directory(self):
        """Should include project skills directory."""
        directories = get_default_skill_directories()

        # Project directory is based on cwd
        assert any("skills" in d for d in directories)
