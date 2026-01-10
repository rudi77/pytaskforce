"""
Unit tests for Ralph Plugin Tools

Tests RalphPRDTool and RalphLearningsTool functionality.
"""

import json
import sys
from pathlib import Path

import pytest

# Add ralph_plugin directory to path for plugin imports
# Path: tests/unit/infrastructure/tools/test_ralph_tools.py
# Need to go up to project root, then into examples/ralph_plugin
project_root = Path(__file__).parent.parent.parent.parent.parent
ralph_plugin_dir = project_root / "examples" / "ralph_plugin"
if str(ralph_plugin_dir) not in sys.path:
    sys.path.insert(0, str(ralph_plugin_dir))

from ralph_plugin.tools.learnings_tool import RalphLearningsTool  # noqa: E402
from ralph_plugin.tools.prd_tool import RalphPRDTool  # noqa: E402


class TestRalphPRDTool:
    """Test suite for RalphPRDTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a RalphPRDTool instance with temporary PRD path."""
        prd_path = tmp_path / "prd.json"
        return RalphPRDTool(prd_path=str(prd_path))

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "ralph_prd"
        assert "PRD tracking" in tool.description
        assert tool.requires_approval is True
        assert tool.approval_risk_level.value == "medium"
        assert tool.supports_parallelism is False

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "action" in schema["properties"]
        assert "story_id" in schema["properties"]
        assert "action" in schema["required"]
        assert schema["properties"]["action"]["enum"] == ["get_next", "mark_complete"]

    def test_validate_params_get_next(self, tool):
        """Test parameter validation for get_next action."""
        valid, error = tool.validate_params(action="get_next")
        assert valid is True
        assert error is None

    def test_validate_params_mark_complete_valid(self, tool):
        """Test parameter validation for mark_complete with valid story_id."""
        valid, error = tool.validate_params(action="mark_complete", story_id=1)
        assert valid is True
        assert error is None

    def test_validate_params_mark_complete_missing_id(self, tool):
        """Test parameter validation for mark_complete without story_id."""
        valid, error = tool.validate_params(action="mark_complete")
        assert valid is False
        assert "story_id" in error

    def test_validate_params_invalid_action(self, tool):
        """Test parameter validation with invalid action."""
        valid, error = tool.validate_params(action="invalid_action")
        assert valid is False
        assert "Invalid action" in error

    @pytest.mark.asyncio
    async def test_get_next_story_exists(self, tool, tmp_path):
        """Test getting next pending story when one exists."""
        prd_data = {
            "stories": [
                {"id": 1, "title": "Story 1", "passes": True, "success_criteria": []},
                {"id": 2, "title": "Story 2", "passes": False, "success_criteria": []},
                {"id": 3, "title": "Story 3", "passes": False, "success_criteria": []},
            ]
        }
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        result = await tool.execute(action="get_next")

        assert result["success"] is True
        assert result["story"]["id"] == 2
        assert result["story"]["title"] == "Story 2"
        assert "Found next pending story" in result["output"]

    @pytest.mark.asyncio
    async def test_get_next_story_none_pending(self, tool, tmp_path):
        """Test getting next story when all are complete."""
        prd_data = {
            "stories": [
                {"id": 1, "title": "Story 1", "passes": True, "success_criteria": []},
                {"id": 2, "title": "Story 2", "passes": True, "success_criteria": []},
            ]
        }
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        result = await tool.execute(action="get_next")

        assert result["success"] is True
        assert result["story"] is None
        assert "No pending stories" in result["output"]

    @pytest.mark.asyncio
    async def test_get_next_story_file_not_exists(self, tool):
        """Test getting next story when prd.json doesn't exist."""
        result = await tool.execute(action="get_next")

        assert result["success"] is True
        assert result["story"] is None
        assert "No pending stories" in result["output"]

    @pytest.mark.asyncio
    async def test_get_next_story_missing_passes_field(self, tool, tmp_path):
        """Test getting next story when passes field is missing (should be treated as False)."""
        prd_data = {
            "stories": [
                {"id": 1, "title": "Story 1", "success_criteria": []},  # passes missing
            ]
        }
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        result = await tool.execute(action="get_next")

        assert result["success"] is True
        assert result["story"]["id"] == 1

    @pytest.mark.asyncio
    async def test_mark_story_complete(self, tool, tmp_path):
        """Test marking a story as complete."""
        prd_data = {
            "stories": [
                {"id": 1, "title": "Story 1", "passes": False, "success_criteria": []},
                {"id": 2, "title": "Story 2", "passes": False, "success_criteria": []},
            ]
        }
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        result = await tool.execute(action="mark_complete", story_id=1)

        assert result["success"] is True
        assert result["story_id"] == 1
        assert "marked as complete" in result["output"]

        # Verify file was updated
        updated_data = json.loads(prd_path.read_text(encoding="utf-8"))
        assert updated_data["stories"][0]["passes"] is True
        assert updated_data["stories"][1]["passes"] is False  # Other story unchanged

    @pytest.mark.asyncio
    async def test_mark_story_complete_not_found(self, tool, tmp_path):
        """Test marking a non-existent story as complete."""
        prd_data = {
            "stories": [
                {"id": 1, "title": "Story 1", "passes": False, "success_criteria": []},
            ]
        }
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        result = await tool.execute(action="mark_complete", story_id=999)

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_mark_story_complete_atomic_write(self, tool, tmp_path):
        """Test that file writes are atomic (temp file + rename)."""
        prd_data = {
            "stories": [
                {"id": 1, "title": "Story 1", "passes": False, "success_criteria": []},
            ]
        }
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        # Mark complete
        result = await tool.execute(action="mark_complete", story_id=1)
        assert result["success"] is True

        # Verify temp file was cleaned up
        temp_file = prd_path.with_suffix(".tmp")
        assert not temp_file.exists()

    @pytest.mark.asyncio
    async def test_get_next_story_invalid_json(self, tool, tmp_path):
        """Test handling of invalid JSON in prd.json."""
        prd_path = Path(tool.prd_path)
        prd_path.write_text("invalid json content", encoding="utf-8")

        result = await tool.execute(action="get_next")

        assert result["success"] is False
        assert "error" in result


class TestRalphLearningsTool:
    """Test suite for RalphLearningsTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a RalphLearningsTool instance with temporary paths."""
        progress_path = tmp_path / "progress.txt"
        agents_path = tmp_path / "AGENTS.md"
        return RalphLearningsTool(
            progress_path=str(progress_path),
            agents_path=str(agents_path),
        )

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "ralph_learnings"
        assert "learnings" in tool.description.lower()
        assert tool.requires_approval is True
        assert tool.approval_risk_level.value == "medium"
        assert tool.supports_parallelism is False

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "lesson" in schema["properties"]
        assert "guardrail" in schema["properties"]
        assert "lesson" in schema["required"]

    def test_validate_params_valid(self, tool):
        """Test parameter validation with valid params."""
        valid, error = tool.validate_params(lesson="Test lesson")
        assert valid is True
        assert error is None

    def test_validate_params_with_guardrail(self, tool):
        """Test parameter validation with guardrail."""
        valid, error = tool.validate_params(lesson="Test lesson", guardrail="Test guardrail")
        assert valid is True
        assert error is None

    def test_validate_params_missing_lesson(self, tool):
        """Test parameter validation without lesson."""
        valid, error = tool.validate_params()
        assert valid is False
        assert "lesson" in error

    def test_validate_params_empty_lesson(self, tool):
        """Test parameter validation with empty lesson."""
        valid, error = tool.validate_params(lesson="")
        assert valid is False
        assert "non-empty" in error

    @pytest.mark.asyncio
    async def test_append_progress_new_file(self, tool, tmp_path):
        """Test appending lesson to new progress.txt file."""
        lesson = "Test lesson learned"

        result = await tool.execute(lesson=lesson)

        assert result["success"] is True
        assert "appended" in result["output"].lower()

        # Verify file was created with header
        progress_path = Path(tool.progress_path)
        assert progress_path.exists()
        content = progress_path.read_text(encoding="utf-8")
        assert "# Progress Log" in content
        assert "# Lessons Learned" in content
        assert lesson in content

    @pytest.mark.asyncio
    async def test_append_progress_existing_file(self, tool, tmp_path):
        """Test appending lesson to existing progress.txt file."""
        progress_path = Path(tool.progress_path)
        progress_path.write_text("# Progress Log\n\n", encoding="utf-8")

        lesson = "New lesson learned"
        result = await tool.execute(lesson=lesson)

        assert result["success"] is True

        # Verify lesson was appended
        content = progress_path.read_text(encoding="utf-8")
        assert lesson in content
        assert content.count(lesson) == 1  # Not duplicated

    @pytest.mark.asyncio
    async def test_update_agents_md_new_file(self, tool, tmp_path):
        """Test updating AGENTS.md when file doesn't exist."""
        guardrail = "Always check X before Y"

        result = await tool.execute(lesson="Test lesson", guardrail=guardrail)

        assert result["success"] is True

        # Verify file was created with guardrail
        agents_path = Path(tool.agents_path)
        assert agents_path.exists()
        content = agents_path.read_text(encoding="utf-8")
        assert "Self-Maintaining Documentation" in content
        assert "## Guardrails" in content
        assert guardrail in content

    @pytest.mark.asyncio
    async def test_update_agents_md_existing_section(self, tool, tmp_path):
        """Test updating AGENTS.md when Guardrails section exists."""
        agents_path = Path(tool.agents_path)
        initial_content = "# Self-Maintaining Documentation\n\n## Guardrails\n\n- Old guardrail\n"
        agents_path.write_text(initial_content, encoding="utf-8")

        guardrail = "New guardrail"
        result = await tool.execute(lesson="Test lesson", guardrail=guardrail)

        assert result["success"] is True

        # Verify guardrail was added
        content = agents_path.read_text(encoding="utf-8")
        assert guardrail in content
        assert "Old guardrail" in content  # Existing content preserved

    @pytest.mark.asyncio
    async def test_update_agents_md_no_guardrail(self, tool, tmp_path):
        """Test that AGENTS.md is not updated when guardrail is not provided."""
        agents_path = Path(tool.agents_path)

        result = await tool.execute(lesson="Test lesson")

        assert result["success"] is True

        # AGENTS.md should not exist if guardrail not provided
        assert not agents_path.exists()

    @pytest.mark.asyncio
    async def test_execute_with_both_lesson_and_guardrail(self, tool, tmp_path):
        """Test executing with both lesson and guardrail."""
        lesson = "Test lesson"
        guardrail = "Test guardrail"

        result = await tool.execute(lesson=lesson, guardrail=guardrail)

        assert result["success"] is True
        assert "progress.txt" in result["output"]
        assert "AGENTS.md" in result["output"]

        # Verify both files were updated
        progress_path = Path(tool.progress_path)
        agents_path = Path(tool.agents_path)

        assert progress_path.exists()
        assert agents_path.exists()

        assert lesson in progress_path.read_text(encoding="utf-8")
        assert guardrail in agents_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_timestamp_in_progress(self, tool, tmp_path):
        """Test that timestamps are added to progress entries."""
        lesson = "Test lesson"
        await tool.execute(lesson=lesson)

        progress_path = Path(tool.progress_path)
        content = progress_path.read_text(encoding="utf-8")

        # Check for timestamp format [YYYY-MM-DD HH:MM:SS]
        import re

        timestamp_pattern = r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]"
        assert re.search(timestamp_pattern, content) is not None
