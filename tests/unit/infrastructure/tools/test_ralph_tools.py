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

from ralph_plugin.tools.learnings_tool import (  # noqa: E402
    MAX_GUARDRAILS,
    MAX_PROGRESS_ENTRIES,
    RalphLearningsTool,
)
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
        assert "files" in schema["properties"]  # V3
        assert "test_path" in schema["properties"]  # V3
        assert "action" in schema["required"]
        # V3: includes new actions
        assert schema["properties"]["action"]["enum"] == [
            "get_next",
            "mark_complete",
            "get_current_context",
            "verify_and_complete",
        ]

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

    # ==========================================================================
    # V3 Tests: get_current_context
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_get_current_context_returns_minimal_data(self, tool, tmp_path):
        """Test that get_current_context returns minimal context."""
        prd_data = {
            "stories": [
                {"id": 1, "title": "Story 1", "passes": True, "success_criteria": []},
                {"id": 2, "title": "Story 2", "passes": True, "success_criteria": []},
                {"id": 3, "title": "Story 3", "passes": False, "success_criteria": ["Criterion A"]},
                {"id": 4, "title": "Story 4", "passes": False, "success_criteria": []},
            ]
        }
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        result = await tool.execute(action="get_current_context")

        assert result["success"] is True
        assert result["current_story"]["id"] == 3  # First with passes=False
        assert result["progress"] == "2/4"
        assert result["completed_count"] == 2
        assert result["remaining_count"] == 2
        # Only last 3 completed titles
        assert len(result["recent_completed"]) <= 3
        assert "Story 1" in result["recent_completed"] or "Story 2" in result["recent_completed"]

    @pytest.mark.asyncio
    async def test_get_current_context_all_complete(self, tool, tmp_path):
        """Test get_current_context when all stories are complete."""
        prd_data = {
            "stories": [
                {"id": 1, "title": "Story 1", "passes": True, "success_criteria": []},
                {"id": 2, "title": "Story 2", "passes": True, "success_criteria": []},
            ]
        }
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        result = await tool.execute(action="get_current_context")

        assert result["success"] is True
        assert result["current_story"] is None
        assert result["progress"] == "2/2"
        assert "All complete" in result["output"]

    @pytest.mark.asyncio
    async def test_get_current_context_empty_prd(self, tool):
        """Test get_current_context with no PRD file."""
        result = await tool.execute(action="get_current_context")

        assert result["success"] is True
        assert result["current_story"] is None
        assert result["progress"] == "0/0"

    # ==========================================================================
    # V3 Tests: verify_and_complete
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_verify_and_complete_success(self, tool, tmp_path):
        """Test verify_and_complete marks story when verification passes."""
        # Create PRD
        prd_data = {
            "stories": [
                {"id": 1, "title": "Story 1", "passes": False, "success_criteria": []},
            ]
        }
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        # Create valid Python file
        code_file = tmp_path / "app.py"
        code_file.write_text("x = 1\n")

        result = await tool.execute(
            action="verify_and_complete",
            story_id=1,
            files=[str(code_file)],
        )

        assert result["success"] is True
        assert "Verification passed" in result["output"]
        assert result["story_id"] == 1

        # Verify PRD was updated
        updated_data = json.loads(prd_path.read_text(encoding="utf-8"))
        assert updated_data["stories"][0]["passes"] is True

    @pytest.mark.asyncio
    async def test_verify_and_complete_blocks_on_syntax_error(self, tool, tmp_path):
        """Test verify_and_complete blocks when syntax verification fails."""
        # Create PRD
        prd_data = {
            "stories": [
                {"id": 1, "title": "Story 1", "passes": False, "success_criteria": []},
            ]
        }
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        # Create invalid Python file
        code_file = tmp_path / "app.py"
        code_file.write_text("def broken(:\n    pass\n")  # Syntax error

        result = await tool.execute(
            action="verify_and_complete",
            story_id=1,
            files=[str(code_file)],
        )

        assert result["success"] is False
        assert result["stage"] == "syntax"
        assert "Fix syntax errors" in result["output"]

        # Verify PRD was NOT updated
        updated_data = json.loads(prd_path.read_text(encoding="utf-8"))
        assert updated_data["stories"][0]["passes"] is False

    @pytest.mark.asyncio
    async def test_verify_and_complete_blocks_on_test_failure(self, tool, tmp_path):
        """Test verify_and_complete blocks when test verification fails."""
        # Update tool with correct project root for pytest
        tool = RalphPRDTool(
            prd_path=str(tmp_path / "prd.json"),
            project_root=str(tmp_path),
        )

        # Create PRD
        prd_data = {
            "stories": [
                {"id": 1, "title": "Story 1", "passes": False, "success_criteria": []},
            ]
        }
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        # Create valid Python file
        code_file = tmp_path / "app.py"
        code_file.write_text("x = 1\n")

        # Create failing test
        test_file = tmp_path / "test_app.py"
        test_file.write_text("def test_fail():\n    assert False\n")

        result = await tool.execute(
            action="verify_and_complete",
            story_id=1,
            files=[str(code_file)],
            test_path=str(test_file),
        )

        assert result["success"] is False
        assert result["stage"] == "tests"
        assert "Fix failing tests" in result["output"]

        # Verify PRD was NOT updated
        updated_data = json.loads(prd_path.read_text(encoding="utf-8"))
        assert updated_data["stories"][0]["passes"] is False

    @pytest.mark.asyncio
    async def test_verify_and_complete_story_not_found(self, tool, tmp_path):
        """Test verify_and_complete with non-existent story."""
        prd_data = {"stories": [{"id": 1, "title": "Story 1", "passes": False}]}
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        result = await tool.execute(action="verify_and_complete", story_id=999)

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_verify_and_complete_no_files(self, tool, tmp_path):
        """Test verify_and_complete with no files to verify (skip syntax check)."""
        prd_data = {"stories": [{"id": 1, "title": "Story 1", "passes": False}]}
        prd_path = Path(tool.prd_path)
        prd_path.write_text(json.dumps(prd_data, indent=2), encoding="utf-8")

        result = await tool.execute(action="verify_and_complete", story_id=1)

        assert result["success"] is True
        assert result["syntax_files_checked"] == 0


class TestRalphLearningsTool:
    """Test suite for RalphLearningsTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a RalphLearningsTool instance with temporary paths."""
        progress_path = tmp_path / "progress.txt"
        agents_path = tmp_path / "AGENTS.md"
        archive_path = tmp_path / "AGENTS_ARCHIVE.md"
        return RalphLearningsTool(
            progress_path=str(progress_path),
            agents_path=str(agents_path),
            archive_path=str(archive_path),
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

    # ==========================================================================
    # V3 Tests: Rolling Log and Guardrail Limits
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_rolling_log_keeps_max_entries(self, tmp_path):
        """Test that progress.txt keeps only max entries (rolling log)."""
        tool = RalphLearningsTool(
            progress_path=str(tmp_path / "progress.txt"),
            agents_path=str(tmp_path / "AGENTS.md"),
            max_progress_entries=5,  # Small limit for testing
        )

        # Add more than max entries
        for i in range(10):
            await tool.execute(lesson=f"Lesson {i}")

        progress_path = Path(tool.progress_path)
        content = progress_path.read_text(encoding="utf-8")

        # Should only have last 5 entries
        assert "Lesson 9" in content
        assert "Lesson 8" in content
        assert "Lesson 5" in content
        # Older entries should be gone
        assert "Lesson 0" not in content
        assert "Lesson 1" not in content
        assert "Lesson 2" not in content
        assert "Lesson 3" not in content
        assert "Lesson 4" not in content

    @pytest.mark.asyncio
    async def test_guardrail_limit_archives_old(self, tmp_path):
        """Test that guardrails exceeding limit are archived."""
        tool = RalphLearningsTool(
            progress_path=str(tmp_path / "progress.txt"),
            agents_path=str(tmp_path / "AGENTS.md"),
            archive_path=str(tmp_path / "AGENTS_ARCHIVE.md"),
            max_guardrails=3,  # Small limit for testing
        )

        # Add more than max guardrails
        for i in range(5):
            await tool.execute(lesson=f"Lesson {i}", guardrail=f"Guardrail {i}")

        # Check AGENTS.md - should have max 3 guardrails (most recent)
        agents_path = Path(tool.agents_path)
        content = agents_path.read_text(encoding="utf-8")
        assert "Guardrail 4" in content
        assert "Guardrail 3" in content
        assert "Guardrail 2" in content
        # Older guardrails should NOT be in main file
        assert "Guardrail 0" not in content
        assert "Guardrail 1" not in content

        # Check archive file - should have older guardrails
        archive_path = Path(tool.archive_path)
        assert archive_path.exists()
        archive_content = archive_path.read_text(encoding="utf-8")
        assert "Guardrail 0" in archive_content or "Guardrail 1" in archive_content

    @pytest.mark.asyncio
    async def test_default_limits(self, tmp_path):
        """Test that default limits are applied."""
        tool = RalphLearningsTool(
            progress_path=str(tmp_path / "progress.txt"),
            agents_path=str(tmp_path / "AGENTS.md"),
        )

        assert tool.max_progress_entries == MAX_PROGRESS_ENTRIES
        assert tool.max_guardrails == MAX_GUARDRAILS

    @pytest.mark.asyncio
    async def test_archive_path_configurable(self, tmp_path):
        """Test that archive path is configurable."""
        custom_archive = tmp_path / "custom_archive.md"
        tool = RalphLearningsTool(
            progress_path=str(tmp_path / "progress.txt"),
            agents_path=str(tmp_path / "AGENTS.md"),
            archive_path=str(custom_archive),
            max_guardrails=2,
        )

        # Add guardrails to trigger archiving
        for i in range(4):
            await tool.execute(lesson=f"Lesson {i}", guardrail=f"Guardrail {i}")

        assert custom_archive.exists()
