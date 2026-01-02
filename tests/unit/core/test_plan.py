"""
Unit tests for core domain plan module.

Tests TodoItem, TodoList, TaskStatus, and PlanGenerator without actual LLM calls.
Uses mocked LLM provider to verify plan generation logic.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.plan import (
    PlanGenerator,
    TaskStatus,
    TodoItem,
    TodoList,
    parse_task_status,
)
from taskforce.core.interfaces.llm import LLMProviderProtocol


class TestTaskStatus:
    """Test TaskStatus enum and parsing."""

    def test_task_status_values(self):
        """Test TaskStatus enum has expected values."""
        assert TaskStatus.PENDING.value == "PENDING"
        assert TaskStatus.IN_PROGRESS.value == "IN_PROGRESS"
        assert TaskStatus.COMPLETED.value == "COMPLETED"
        assert TaskStatus.FAILED.value == "FAILED"
        assert TaskStatus.SKIPPED.value == "SKIPPED"

    def test_parse_task_status_valid(self):
        """Test parsing valid status strings."""
        assert parse_task_status("PENDING") == TaskStatus.PENDING
        assert parse_task_status("IN_PROGRESS") == TaskStatus.IN_PROGRESS
        assert parse_task_status("COMPLETED") == TaskStatus.COMPLETED
        assert parse_task_status("FAILED") == TaskStatus.FAILED
        assert parse_task_status("SKIPPED") == TaskStatus.SKIPPED

    def test_parse_task_status_aliases(self):
        """Test parsing common status aliases."""
        assert parse_task_status("open") == TaskStatus.PENDING
        assert parse_task_status("TODO") == TaskStatus.PENDING
        assert parse_task_status("inprogress") == TaskStatus.IN_PROGRESS
        assert parse_task_status("in-progress") == TaskStatus.IN_PROGRESS
        assert parse_task_status("done") == TaskStatus.COMPLETED
        assert parse_task_status("complete") == TaskStatus.COMPLETED
        assert parse_task_status("fail") == TaskStatus.FAILED

    def test_parse_task_status_invalid_defaults_to_pending(self):
        """Test invalid status strings default to PENDING."""
        assert parse_task_status("invalid") == TaskStatus.PENDING
        assert parse_task_status("") == TaskStatus.PENDING
        assert parse_task_status(None) == TaskStatus.PENDING


class TestTodoItem:
    """Test TodoItem dataclass."""

    def test_todoitem_creation_minimal(self):
        """Test creating TodoItem with minimal required fields."""
        item = TodoItem(position=1, description="Test task", acceptance_criteria="Task is complete")

        assert item.position == 1
        assert item.description == "Test task"
        assert item.acceptance_criteria == "Task is complete"
        assert item.dependencies == []
        assert item.status == TaskStatus.PENDING
        assert item.chosen_tool is None
        assert item.attempts == 0
        assert item.max_attempts == 3
        assert item.replan_count == 0

    def test_todoitem_creation_full(self):
        """Test creating TodoItem with all fields."""
        item = TodoItem(
            position=2,
            description="Complex task",
            acceptance_criteria="File exists",
            dependencies=[1],
            status=TaskStatus.IN_PROGRESS,
            chosen_tool="file_writer",
            tool_input={"filename": "test.txt"},
            execution_result={"success": True},
            attempts=1,
            max_attempts=5,
            replan_count=1,
        )

        assert item.position == 2
        assert item.dependencies == [1]
        assert item.status == TaskStatus.IN_PROGRESS
        assert item.chosen_tool == "file_writer"
        assert item.tool_input == {"filename": "test.txt"}
        assert item.execution_result == {"success": True}
        assert item.attempts == 1
        assert item.max_attempts == 5
        assert item.replan_count == 1

    def test_todoitem_to_dict(self):
        """Test TodoItem serialization to dict."""
        item = TodoItem(
            position=1,
            description="Test",
            acceptance_criteria="Done",
            dependencies=[],
            status=TaskStatus.COMPLETED,
        )

        result = item.to_dict()

        assert result["position"] == 1
        assert result["description"] == "Test"
        assert result["acceptance_criteria"] == "Done"
        assert result["dependencies"] == []
        assert result["status"] == "COMPLETED"
        assert result["chosen_tool"] is None
        assert result["attempts"] == 0


class TestTodoList:
    """Test TodoList dataclass and methods."""

    def test_todolist_creation_minimal(self):
        """Test creating TodoList with minimal fields."""
        items = [TodoItem(position=1, description="Task 1", acceptance_criteria="Done")]
        todolist = TodoList(mission="Test mission", items=items)

        assert todolist.mission == "Test mission"
        assert len(todolist.items) == 1
        assert todolist.todolist_id is not None
        assert isinstance(todolist.created_at, datetime)
        assert isinstance(todolist.updated_at, datetime)
        assert todolist.open_questions == []
        assert todolist.notes == ""

    def test_todolist_creation_full(self):
        """Test creating TodoList with all fields."""
        items = [
            TodoItem(position=1, description="Task 1", acceptance_criteria="Done"),
            TodoItem(
                position=2, description="Task 2", acceptance_criteria="Complete", dependencies=[1]
            ),
        ]
        todolist = TodoList(
            mission="Complex mission",
            items=items,
            todolist_id="test-id-123",
            open_questions=["What is X?"],
            notes="Some notes",
        )

        assert todolist.mission == "Complex mission"
        assert len(todolist.items) == 2
        assert todolist.todolist_id == "test-id-123"
        assert todolist.open_questions == ["What is X?"]
        assert todolist.notes == "Some notes"

    def test_todolist_get_step_by_position(self):
        """Test getting TodoItem by position."""
        items = [
            TodoItem(position=1, description="Task 1", acceptance_criteria="Done"),
            TodoItem(position=2, description="Task 2", acceptance_criteria="Complete"),
            TodoItem(position=5, description="Task 5", acceptance_criteria="Finish"),
        ]
        todolist = TodoList(mission="Test", items=items)

        assert todolist.get_step_by_position(1).description == "Task 1"
        assert todolist.get_step_by_position(2).description == "Task 2"
        assert todolist.get_step_by_position(5).description == "Task 5"
        assert todolist.get_step_by_position(99) is None

    def test_todolist_insert_step(self):
        """Test inserting a step and renumbering."""
        items = [
            TodoItem(position=1, description="Task 1", acceptance_criteria="Done"),
            TodoItem(position=2, description="Task 2", acceptance_criteria="Complete"),
        ]
        todolist = TodoList(mission="Test", items=items)

        new_step = TodoItem(position=2, description="New Task", acceptance_criteria="Inserted")
        todolist.insert_step(new_step)

        assert len(todolist.items) == 3
        assert todolist.get_step_by_position(1).description == "Task 1"
        assert todolist.get_step_by_position(2).description == "New Task"
        assert todolist.get_step_by_position(3).description == "Task 2"

    def test_todolist_to_dict(self):
        """Test TodoList serialization to dict."""
        items = [TodoItem(position=1, description="Task 1", acceptance_criteria="Done")]
        todolist = TodoList(mission="Test mission", items=items, notes="Test notes")

        result = todolist.to_dict()

        assert result["mission"] == "Test mission"
        assert result["todolist_id"] == todolist.todolist_id
        assert len(result["items"]) == 1
        assert result["items"][0]["description"] == "Task 1"
        assert result["notes"] == "Test notes"
        assert result["open_questions"] == []

    def test_todolist_from_json_string(self):
        """Test creating TodoList from JSON string."""
        json_str = json.dumps(
            {
                "todolist_id": "test-123",
                "mission": "Test mission",
                "items": [
                    {
                        "position": 1,
                        "description": "Task 1",
                        "acceptance_criteria": "Done",
                        "dependencies": [],
                        "status": "PENDING",
                    }
                ],
                "open_questions": [],
                "notes": "Test notes",
            }
        )

        todolist = TodoList.from_json(json_str)

        assert todolist.todolist_id == "test-123"
        assert todolist.mission == "Test mission"
        assert len(todolist.items) == 1
        assert todolist.items[0].description == "Task 1"
        assert todolist.notes == "Test notes"

    def test_todolist_from_json_dict(self):
        """Test creating TodoList from dict."""
        data = {
            "todolist_id": "test-456",
            "mission": "Another mission",
            "items": [
                {
                    "position": 1,
                    "description": "Task A",
                    "acceptance_criteria": "Complete",
                    "dependencies": [],
                    "status": "COMPLETED",
                }
            ],
            "open_questions": ["Question?"],
            "notes": "",
        }

        todolist = TodoList.from_json(data)

        assert todolist.todolist_id == "test-456"
        assert todolist.mission == "Another mission"
        assert len(todolist.items) == 1
        assert todolist.items[0].status == TaskStatus.COMPLETED
        assert todolist.open_questions == ["Question?"]

    def test_todolist_from_json_with_fallbacks(self):
        """Test TodoList.from_json handles missing/invalid data gracefully."""
        data = {
            "items": [
                {
                    "description": "Task without position",
                    "acceptance_criteria": "Done",
                }
            ]
        }

        todolist = TodoList.from_json(data)

        assert len(todolist.items) == 1
        assert todolist.items[0].position == 1  # Auto-assigned
        assert todolist.items[0].status == TaskStatus.PENDING  # Default
        assert todolist.todolist_id is not None  # Auto-generated


class TestPlanGenerator:
    """Test PlanGenerator with mocked LLM."""

    @pytest.fixture
    def mock_llm_provider(self):
        """Create a mock LLM provider."""
        mock = AsyncMock(spec=LLMProviderProtocol)
        return mock

    @pytest.fixture
    def plan_generator(self, mock_llm_provider):
        """Create PlanGenerator with mocked LLM."""
        return PlanGenerator(llm_provider=mock_llm_provider)

    @pytest.mark.asyncio
    async def test_extract_clarification_questions_success(self, plan_generator, mock_llm_provider):
        """Test extracting clarification questions successfully."""
        mock_llm_provider.complete.return_value = {
            "success": True,
            "content": json.dumps(
                [
                    {"key": "file_writer.filename", "question": "What filename?"},
                    {"key": "project_name", "question": "What is the project name?"},
                ]
            ),
            "usage": {"total_tokens": 100},
        }

        questions = await plan_generator.extract_clarification_questions(
            mission="Create a file", tools_desc="file_writer tool"
        )

        assert len(questions) == 2
        assert questions[0]["key"] == "file_writer.filename"
        assert questions[1]["key"] == "project_name"
        mock_llm_provider.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_clarification_questions_llm_failure(
        self, plan_generator, mock_llm_provider
    ):
        """Test handling LLM failure during clarification."""
        mock_llm_provider.complete.return_value = {"success": False, "error": "API timeout"}

        with pytest.raises(RuntimeError, match="Failed to extract questions"):
            await plan_generator.extract_clarification_questions(mission="Test", tools_desc="tools")

    @pytest.mark.asyncio
    async def test_extract_clarification_questions_invalid_json(
        self, plan_generator, mock_llm_provider
    ):
        """Test handling invalid JSON from LLM."""
        mock_llm_provider.complete.return_value = {
            "success": True,
            "content": "Not valid JSON",
            "usage": {"total_tokens": 50},
        }

        with pytest.raises(ValueError, match="Invalid JSON from model"):
            await plan_generator.extract_clarification_questions(mission="Test", tools_desc="tools")

    @pytest.mark.asyncio
    async def test_generate_plan_success(self, plan_generator, mock_llm_provider):
        """Test generating a plan successfully."""
        mock_llm_provider.complete.return_value = {
            "success": True,
            "content": json.dumps(
                {
                    "items": [
                        {
                            "position": 1,
                            "description": "Create file",
                            "acceptance_criteria": "File exists",
                            "dependencies": [],
                            "status": "PENDING",
                        },
                        {
                            "position": 2,
                            "description": "Verify file",
                            "acceptance_criteria": "File has content",
                            "dependencies": [1],
                            "status": "PENDING",
                        },
                    ],
                    "open_questions": [],
                    "notes": "Simple plan",
                }
            ),
            "usage": {"total_tokens": 200},
        }

        plan = await plan_generator.generate_plan(
            mission="Create and verify a file",
            tools_desc="file tools",
            answers={"filename": "test.txt"},
        )

        assert isinstance(plan, TodoList)
        assert plan.mission == "Create and verify a file"
        assert len(plan.items) == 2
        assert plan.items[0].description == "Create file"
        assert plan.items[1].dependencies == [1]
        assert all(item.status == TaskStatus.PENDING for item in plan.items)
        mock_llm_provider.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_plan_llm_failure(self, plan_generator, mock_llm_provider):
        """Test handling LLM failure during plan generation."""
        mock_llm_provider.complete.return_value = {"success": False, "error": "Rate limit exceeded"}

        with pytest.raises(RuntimeError, match="Failed to create todolist"):
            await plan_generator.generate_plan(mission="Test", tools_desc="tools")

    @pytest.mark.asyncio
    async def test_generate_plan_invalid_json(self, plan_generator, mock_llm_provider):
        """Test handling invalid JSON during plan generation."""
        mock_llm_provider.complete.return_value = {
            "success": True,
            "content": "Invalid JSON response",
            "usage": {"total_tokens": 100},
        }

        with pytest.raises(ValueError, match="Invalid JSON from model"):
            await plan_generator.generate_plan(mission="Test", tools_desc="tools")

    def test_validate_dependencies_valid_plan(self, plan_generator):
        """Test validating a plan with valid dependencies."""
        items = [
            TodoItem(position=1, description="Task 1", acceptance_criteria="Done", dependencies=[]),
            TodoItem(
                position=2, description="Task 2", acceptance_criteria="Done", dependencies=[1]
            ),
            TodoItem(
                position=3, description="Task 3", acceptance_criteria="Done", dependencies=[1, 2]
            ),
        ]
        plan = TodoList(mission="Test", items=items)

        assert plan_generator.validate_dependencies(plan) is True

    def test_validate_dependencies_invalid_position(self, plan_generator):
        """Test validating a plan with invalid dependency position."""
        items = [
            TodoItem(position=1, description="Task 1", acceptance_criteria="Done", dependencies=[]),
            TodoItem(
                position=2, description="Task 2", acceptance_criteria="Done", dependencies=[99]
            ),
        ]
        plan = TodoList(mission="Test", items=items)

        assert plan_generator.validate_dependencies(plan) is False

    def test_validate_dependencies_circular(self, plan_generator):
        """Test detecting circular dependencies."""
        items = [
            TodoItem(
                position=1, description="Task 1", acceptance_criteria="Done", dependencies=[2]
            ),
            TodoItem(
                position=2, description="Task 2", acceptance_criteria="Done", dependencies=[1]
            ),
        ]
        plan = TodoList(mission="Test", items=items)

        assert plan_generator.validate_dependencies(plan) is False

    def test_validate_dependencies_skipped_items_ignored(self, plan_generator):
        """Test that skipped items are excluded from validation."""
        items = [
            TodoItem(position=1, description="Task 1", acceptance_criteria="Done", dependencies=[]),
            TodoItem(
                position=2,
                description="Task 2",
                acceptance_criteria="Done",
                dependencies=[99],
                status=TaskStatus.SKIPPED,
            ),
            TodoItem(
                position=3, description="Task 3", acceptance_criteria="Done", dependencies=[1]
            ),
        ]
        plan = TodoList(mission="Test", items=items)

        # Should be valid because Task 2 is skipped (invalid dep doesn't matter)
        assert plan_generator.validate_dependencies(plan) is True

    def test_validate_dependencies_empty_plan(self, plan_generator):
        """Test validating an empty plan."""
        plan = TodoList(mission="Empty", items=[])

        assert plan_generator.validate_dependencies(plan) is True

    def test_validate_dependencies_complex_valid(self, plan_generator):
        """Test validating a complex plan with multiple dependencies."""
        items = [
            TodoItem(position=1, description="Task 1", acceptance_criteria="Done", dependencies=[]),
            TodoItem(position=2, description="Task 2", acceptance_criteria="Done", dependencies=[]),
            TodoItem(
                position=3, description="Task 3", acceptance_criteria="Done", dependencies=[1]
            ),
            TodoItem(
                position=4, description="Task 4", acceptance_criteria="Done", dependencies=[2]
            ),
            TodoItem(
                position=5, description="Task 5", acceptance_criteria="Done", dependencies=[3, 4]
            ),
        ]
        plan = TodoList(mission="Test", items=items)

        assert plan_generator.validate_dependencies(plan) is True


class TestPlanGeneratorPrompts:
    """Test prompt generation methods."""

    @pytest.fixture
    def plan_generator(self):
        """Create PlanGenerator with mocked LLM."""
        mock_llm = AsyncMock(spec=LLMProviderProtocol)
        return PlanGenerator(llm_provider=mock_llm)

    def test_create_clarification_questions_prompts(self, plan_generator):
        """Test clarification questions prompt generation."""
        user_prompt, system_prompt = plan_generator._create_clarification_questions_prompts(
            mission="Create a web app", tools_desc="file_writer, git_tool"
        )

        assert "Create a web app" in system_prompt
        assert "file_writer, git_tool" in system_prompt
        assert "JSON array" in user_prompt
        assert "Clarification-Mining Agent" in system_prompt

    def test_create_final_todolist_prompts(self, plan_generator):
        """Test final todolist prompt generation."""
        user_prompt, system_prompt = plan_generator._create_final_todolist_prompts(
            mission="Build API", tools_desc="python_tool", answers={"framework": "FastAPI"}
        )

        assert "Build API" in system_prompt
        assert "python_tool" in system_prompt
        assert "FastAPI" in system_prompt
        assert "planning agent" in system_prompt
        assert "Generate the plan" in user_prompt


class TestIntegrationScenarios:
    """Integration-style tests for realistic scenarios."""

    @pytest.mark.asyncio
    async def test_full_planning_workflow(self):
        """Test complete planning workflow from mission to validated plan."""
        # Setup mock LLM
        mock_llm = AsyncMock(spec=LLMProviderProtocol)
        mock_llm.complete.return_value = {
            "success": True,
            "content": json.dumps(
                {
                    "items": [
                        {
                            "position": 1,
                            "description": "Research AI advancements",
                            "acceptance_criteria": "List of 5 recent AI papers collected",
                            "dependencies": [],
                            "status": "PENDING",
                        },
                        {
                            "position": 2,
                            "description": "Write summary report",
                            "acceptance_criteria": "report.txt exists with summary",
                            "dependencies": [1],
                            "status": "PENDING",
                        },
                        {
                            "position": 3,
                            "description": "Send email to manager",
                            "acceptance_criteria": "Email sent successfully",
                            "dependencies": [2],
                            "status": "PENDING",
                        },
                    ],
                    "open_questions": [],
                    "notes": "Multi-step research and reporting task",
                }
            ),
            "usage": {"total_tokens": 300},
        }

        generator = PlanGenerator(llm_provider=mock_llm)

        # Generate plan
        plan = await generator.generate_plan(
            mission="Research AI and email summary to manager",
            tools_desc="web_search, file_writer, email_sender",
            answers={"recipient": "manager@example.com"},
        )

        # Verify plan structure
        assert len(plan.items) == 3
        assert plan.items[0].dependencies == []
        assert plan.items[1].dependencies == [1]
        assert plan.items[2].dependencies == [2]

        # Validate dependencies
        assert generator.validate_dependencies(plan) is True

    def test_plan_serialization_roundtrip(self):
        """Test that TodoList can be serialized and deserialized without data loss."""
        original = TodoList(
            mission="Test mission",
            items=[
                TodoItem(
                    position=1,
                    description="Task 1",
                    acceptance_criteria="Done",
                    dependencies=[],
                    status=TaskStatus.COMPLETED,
                    chosen_tool="test_tool",
                    attempts=2,
                )
            ],
            todolist_id="test-123",
            open_questions=["Q1"],
            notes="Test notes",
        )

        # Serialize to dict then JSON
        as_dict = original.to_dict()
        as_json = json.dumps(as_dict)

        # Deserialize
        restored = TodoList.from_json(as_json)

        # Verify all fields match
        assert restored.mission == original.mission
        assert restored.todolist_id == original.todolist_id
        assert len(restored.items) == len(original.items)
        assert restored.items[0].position == original.items[0].position
        assert restored.items[0].description == original.items[0].description
        assert restored.items[0].status == original.items[0].status
        assert restored.items[0].chosen_tool == original.items[0].chosen_tool
        assert restored.items[0].attempts == original.items[0].attempts
        assert restored.open_questions == original.open_questions
        assert restored.notes == original.notes
