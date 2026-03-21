"""Tests for bundled workflow skills (workflow-builder, code-review-pipeline)."""

from pathlib import Path

import pytest

from taskforce.infrastructure.skills.skill_parser import parse_skill_markdown

SKILLS_DIR = Path(__file__).resolve().parents[4] / "src" / "taskforce" / "skills"


class TestWorkflowBuilderSkill:
    """Test the workflow-builder context skill."""

    @pytest.fixture
    def skill_content(self) -> str:
        skill_path = SKILLS_DIR / "workflow-builder" / "SKILL.md"
        return skill_path.read_text()

    def test_parses_successfully(self, skill_content: str):
        skill = parse_skill_markdown(skill_content, str(SKILLS_DIR / "workflow-builder"))
        assert skill.name == "workflow-builder"
        assert skill.skill_type.value == "context"

    def test_has_description(self, skill_content: str):
        skill = parse_skill_markdown(skill_content, str(SKILLS_DIR / "workflow-builder"))
        assert "workflow" in skill.description.lower()

    def test_has_instructions(self, skill_content: str):
        skill = parse_skill_markdown(skill_content, str(SKILLS_DIR / "workflow-builder"))
        assert "SKILL.md" in skill.instructions
        assert "activate_skill" in skill.instructions


class TestCodeReviewPipelineSkill:
    """Test the code-review-pipeline context skill."""

    @pytest.fixture
    def skill_content(self) -> str:
        skill_path = SKILLS_DIR / "code-review-pipeline" / "SKILL.md"
        return skill_path.read_text()

    def test_parses_successfully(self, skill_content: str):
        skill = parse_skill_markdown(skill_content, str(SKILLS_DIR / "code-review-pipeline"))
        assert skill.name == "code-review-pipeline"
        assert skill.skill_type.value == "context"

    def test_has_description(self, skill_content: str):
        skill = parse_skill_markdown(skill_content, str(SKILLS_DIR / "code-review-pipeline"))
        assert "code review" in skill.description.lower()

    def test_has_workflow_steps(self, skill_content: str):
        skill = parse_skill_markdown(skill_content, str(SKILLS_DIR / "code-review-pipeline"))
        assert "Step 1" in skill.instructions
        assert "Step 5" in skill.instructions
