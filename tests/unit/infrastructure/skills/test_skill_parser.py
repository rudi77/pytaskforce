"""Unit tests for workflow parsing in skill parser."""

import pytest

from taskforce.infrastructure.skills.skill_parser import (
    SkillParseError,
    parse_skill_markdown,
)


def test_parse_skill_with_external_workflow_engine(tmp_path):
    """Parser should accept workflow engine + callable_path format."""
    skill_dir = tmp_path / "smart-booking-auto"
    skill_dir.mkdir()
    content = """---
name: smart-booking-auto
description: Auto booking skill.
workflow:
  engine: langgraph
  callable_path: scripts/langgraph_workflow.py:run_smart_booking_auto_workflow
---

# Skill
"""

    parsed = parse_skill_markdown(content, str(skill_dir))

    assert parsed.workflow is not None
    assert parsed.workflow["engine"] == "langgraph"
    assert parsed.workflow["callable_path"].endswith(
        "run_smart_booking_auto_workflow"
    )


def test_parse_skill_workflow_requires_steps_or_engine(tmp_path):
    """Parser should reject empty workflow definitions."""
    skill_dir = tmp_path / "smart-booking-auto"
    skill_dir.mkdir()
    content = """---
name: smart-booking-auto
description: Auto booking skill.
workflow:
  description: missing execution details
---

# Skill
"""

    with pytest.raises(SkillParseError, match="steps"):
        parse_skill_markdown(content, str(skill_dir))
