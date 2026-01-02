"""
Unit tests for core protocol interfaces.

Tests verify that:
- Protocols can be imported without errors
- Mock implementations can be created
- Type hints are correctly defined
- Protocol contracts are enforceable
"""

from typing import Any

from taskforce.core.interfaces import (
    ApprovalRiskLevel,
    LLMProviderProtocol,
    StateManagerProtocol,
    TaskStatus,
    TodoItem,
    TodoList,
    TodoListManagerProtocol,
    ToolProtocol,
)


class TestProtocolImports:
    """Test that all protocols can be imported successfully."""

    def test_import_state_manager_protocol(self):
        """Test StateManagerProtocol can be imported."""
        assert StateManagerProtocol is not None

    def test_import_llm_provider_protocol(self):
        """Test LLMProviderProtocol can be imported."""
        assert LLMProviderProtocol is not None

    def test_import_tool_protocol(self):
        """Test ToolProtocol can be imported."""
        assert ToolProtocol is not None

    def test_import_todolist_manager_protocol(self):
        """Test TodoListManagerProtocol can be imported."""
        assert TodoListManagerProtocol is not None

    def test_import_approval_risk_level(self):
        """Test ApprovalRiskLevel enum can be imported."""
        assert ApprovalRiskLevel is not None
        assert ApprovalRiskLevel.LOW == "low"
        assert ApprovalRiskLevel.MEDIUM == "medium"
        assert ApprovalRiskLevel.HIGH == "high"

    def test_import_task_status(self):
        """Test TaskStatus enum can be imported."""
        assert TaskStatus is not None
        assert TaskStatus.PENDING == "PENDING"
        assert TaskStatus.IN_PROGRESS == "IN_PROGRESS"
        assert TaskStatus.COMPLETED == "COMPLETED"
        assert TaskStatus.FAILED == "FAILED"
        assert TaskStatus.SKIPPED == "SKIPPED"


class TestMockImplementations:
    """Test that mock implementations can be created for protocols."""

    def test_mock_state_manager(self):
        """Test creating a mock StateManager implementation."""

        class MockStateManager:
            async def save_state(
                self, session_id: str, state_data: dict[str, Any]
            ) -> bool:
                return True

            async def load_state(self, session_id: str) -> dict[str, Any] | None:
                return {}

            async def delete_state(self, session_id: str) -> None:
                pass

            async def list_sessions(self) -> list[str]:
                return []

        mock: StateManagerProtocol = MockStateManager()
        assert mock is not None

    def test_mock_llm_provider(self):
        """Test creating a mock LLM provider implementation."""

        class MockLLMProvider:
            async def complete(
                self,
                messages: list[dict[str, Any]],
                model: str | None = None,
                **kwargs: Any,
            ) -> dict[str, Any]:
                return {
                    "success": True,
                    "content": "Test response",
                    "usage": {"total_tokens": 10},
                    "model": "test-model",
                    "latency_ms": 100,
                }

            async def generate(
                self,
                prompt: str,
                context: dict[str, Any] | None = None,
                model: str | None = None,
                **kwargs: Any,
            ) -> dict[str, Any]:
                return {
                    "success": True,
                    "content": "Generated text",
                    "generated_text": "Generated text",
                    "usage": {"total_tokens": 10},
                    "model": "test-model",
                    "latency_ms": 100,
                }

        mock: LLMProviderProtocol = MockLLMProvider()
        assert mock is not None

    def test_mock_tool(self):
        """Test creating a mock Tool implementation."""

        class MockTool:
            @property
            def name(self) -> str:
                return "mock_tool"

            @property
            def description(self) -> str:
                return "A mock tool for testing"

            @property
            def parameters_schema(self) -> dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "Test parameter"}
                    },
                    "required": ["param1"],
                }

            @property
            def requires_approval(self) -> bool:
                return False

            @property
            def approval_risk_level(self) -> ApprovalRiskLevel:
                return ApprovalRiskLevel.LOW

            def get_approval_preview(self, **kwargs: Any) -> str:
                return "Mock tool preview"

            async def execute(self, **kwargs: Any) -> dict[str, Any]:
                return {"success": True, "output": "Mock output"}

            def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
                return True, None

        mock: ToolProtocol = MockTool()
        assert mock is not None
        assert mock.name == "mock_tool"
        assert mock.requires_approval is False

    def test_mock_todolist_manager(self):
        """Test creating a mock TodoListManager implementation."""

        class MockTodoListManager:
            async def extract_clarification_questions(
                self, mission: str, tools_desc: str, model: str = "main"
            ) -> list[dict[str, Any]]:
                return []

            async def create_todolist(
                self,
                mission: str,
                tools_desc: str,
                answers: dict[str, Any] | None = None,
                model: str = "fast",
                memory_manager: Any | None = None,
            ) -> TodoList:
                return TodoList(
                    todolist_id="test-123",
                    items=[],
                    open_questions=[],
                    notes="Test notes",
                )

            async def load_todolist(self, todolist_id: str) -> TodoList:
                return TodoList(
                    todolist_id=todolist_id,
                    items=[],
                    open_questions=[],
                    notes="",
                )

            async def update_todolist(self, todolist: TodoList) -> TodoList:
                return todolist

            async def get_todolist(self, todolist_id: str) -> TodoList:
                return TodoList(
                    todolist_id=todolist_id,
                    items=[],
                    open_questions=[],
                    notes="",
                )

            async def delete_todolist(self, todolist_id: str) -> bool:
                return True

            async def modify_step(
                self,
                todolist_id: str,
                step_position: int,
                modifications: dict[str, Any],
            ) -> tuple[bool, str | None]:
                return True, None

            async def decompose_step(
                self,
                todolist_id: str,
                step_position: int,
                subtasks: list[dict[str, Any]],
            ) -> tuple[bool, list[int]]:
                return True, [1, 2]

            async def replace_step(
                self,
                todolist_id: str,
                step_position: int,
                new_step_data: dict[str, Any],
            ) -> tuple[bool, int | None]:
                return True, 1

        mock: TodoListManagerProtocol = MockTodoListManager()
        assert mock is not None


class TestDataclasses:
    """Test TodoItem and TodoList dataclasses."""

    def test_todo_item_creation(self):
        """Test creating a TodoItem."""
        item = TodoItem(
            position=1,
            description="Test task",
            acceptance_criteria="Task is complete",
            dependencies=[],
            status=TaskStatus.PENDING,
        )
        assert item.position == 1
        assert item.description == "Test task"
        assert item.status == TaskStatus.PENDING
        assert item.chosen_tool is None
        assert item.attempts == 0

    def test_todo_item_with_execution_data(self):
        """Test TodoItem with execution data."""
        item = TodoItem(
            position=1,
            description="Test task",
            acceptance_criteria="Task is complete",
            dependencies=[],
            status=TaskStatus.COMPLETED,
            chosen_tool="test_tool",
            tool_input={"param": "value"},
            execution_result={"success": True},
            attempts=1,
        )
        assert item.chosen_tool == "test_tool"
        assert item.tool_input == {"param": "value"}
        assert item.execution_result == {"success": True}
        assert item.attempts == 1

    def test_todolist_creation(self):
        """Test creating a TodoList."""
        items = [
            TodoItem(
                position=1,
                description="Task 1",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
            ),
            TodoItem(
                position=2,
                description="Task 2",
                acceptance_criteria="Done",
                dependencies=[1],
                status=TaskStatus.PENDING,
            ),
        ]
        todolist = TodoList(
            todolist_id="test-123",
            items=items,
            open_questions=["Question 1"],
            notes="Test notes",
        )
        assert todolist.todolist_id == "test-123"
        assert len(todolist.items) == 2
        assert len(todolist.open_questions) == 1
        assert todolist.notes == "Test notes"

    def test_todolist_empty(self):
        """Test creating an empty TodoList."""
        todolist = TodoList(
            todolist_id="empty-123", items=[], open_questions=[], notes=""
        )
        assert todolist.todolist_id == "empty-123"
        assert len(todolist.items) == 0
        assert len(todolist.open_questions) == 0
        assert todolist.notes == ""


class TestProtocolContracts:
    """Test that protocol contracts are properly defined."""

    def test_protocols_are_importable(self):
        """Test that all protocols can be used in type hints."""
        # This test verifies protocols can be used as types
        def accepts_state_manager(sm: StateManagerProtocol) -> None:
            pass

        def accepts_llm_provider(llm: LLMProviderProtocol) -> None:
            pass

        def accepts_tool(tool: ToolProtocol) -> None:
            pass

        def accepts_todolist_manager(tm: TodoListManagerProtocol) -> None:
            pass

        # If we get here without import errors, protocols are properly defined
        assert True

