"""Unit tests for workflow parsing in skill parser."""

import pytest

from taskforce.core.domain.enums import SkillType
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


@pytest.mark.spec("skills.invalid_name_rejected")
def test_parse_rejects_invalid_name(tmp_path):
    """A name that is not valid kebab-case (here: uppercase) is rejected."""
    skill_dir = tmp_path / "Bad-Skill"
    skill_dir.mkdir()
    content = """---
name: Bad-Skill
description: A skill with an invalid name.
---

# Skill
"""
    with pytest.raises(SkillParseError):
        parse_skill_markdown(content, str(skill_dir))


@pytest.mark.spec("skills.directory_name_mismatch_rejected")
def test_parse_rejects_directory_name_mismatch(tmp_path):
    """The last `:`-segment of the name must equal the containing directory."""
    skill_dir = tmp_path / "actual-dir"
    skill_dir.mkdir()
    content = """---
name: different-name
description: Name does not match its directory.
---

# Skill
"""
    with pytest.raises(SkillParseError):
        parse_skill_markdown(content, str(skill_dir))


@pytest.mark.spec("skills.missing_description_rejected")
def test_parse_rejects_missing_description(tmp_path):
    """A SKILL.md without a description fails to parse."""
    skill_dir = tmp_path / "no-desc"
    skill_dir.mkdir()
    content = """---
name: no-desc
---

# Skill
"""
    with pytest.raises(SkillParseError, match="description"):
        parse_skill_markdown(content, str(skill_dir))


@pytest.mark.spec("skills.agent_skill_overrides_profile")
def test_parse_agent_skill_collects_profile_override(tmp_path):
    """An AGENT-type skill collects profile / tools into ``agent_config``."""
    skill_dir = tmp_path / "deep-review"
    skill_dir.mkdir()
    content = """---
name: deep-review
description: Switch to a coding profile for deep reviews.
type: agent
profile: coding_agent
tools: [file_read, grep]
---

# Deep Review
"""
    parsed = parse_skill_markdown(content, str(skill_dir))

    assert parsed.skill_type == SkillType.AGENT
    assert parsed.agent_config is not None
    assert parsed.agent_config["profile"] == "coding_agent"
    assert parsed.agent_config["tools"] == ["file_read", "grep"]
