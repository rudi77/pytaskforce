"""
Integration tests for Fast-Path Router (Story 4.3).

Tests verify that:
- Fast-path is activated for follow-up queries
- Full planning path is used for new missions
- Router decision is logged correctly
- Execution history shows fast_path flag
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from taskforce.core.domain.agent import Agent
from taskforce.core.domain.events import Action, ActionType, Thought
from taskforce.core.domain.router import QueryRouter, RouteDecision, RouterContext, RouterResult
from taskforce.core.interfaces.todolist import TaskStatus, TodoItem, TodoList


@pytest.fixture
def mock_state_manager():
    """Create mock state manager."""
    manager = MagicMock()
    manager.load_state = AsyncMock(return_value={})
    manager.save_state = AsyncMock()
    return manager


@pytest.fixture
def mock_llm_provider():
    """Create mock LLM provider."""
    provider = MagicMock()
    return provider


@pytest.fixture
def mock_todolist_manager():
    """Create mock todolist manager."""
    manager = MagicMock()
    manager.update_todolist = AsyncMock()
    manager.create_todolist = AsyncMock()
    manager.load_todolist = AsyncMock()
    return manager


@pytest.fixture
def mock_tool():
    """Create mock tool."""
    tool = MagicMock()
    tool.name = "test_tool"
    tool.description = "Test tool"
    tool.parameters_schema = {"type": "object", "properties": {}}
    tool.execute = AsyncMock(
        return_value={
            "success": True,
            "result": "Tool result",
        }
    )
    return tool


@pytest.fixture
def router():
    """Create QueryRouter without LLM."""
    return QueryRouter(use_llm_classification=False)


@pytest.fixture
def completed_todolist():
    """Create a completed todolist for testing follow-ups."""
    return TodoList(
        todolist_id="test-todolist-123",
        items=[
            TodoItem(
                position=1,
                description="Read wiki page",
                acceptance_criteria="Page content retrieved",
                dependencies=[],
                status=TaskStatus.COMPLETED,
                chosen_tool="wiki_get_page",
                execution_result={"success": True, "content": "Wiki page content here"},
            )
        ],
        open_questions=[],
        notes="Test todolist",
    )


class TestFastPathActivation:
    """Test fast-path activation for follow-up queries."""

    @pytest.mark.asyncio
    async def test_fast_path_activated_for_short_question(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
        mock_tool,
        router,
        completed_todolist,
    ):
        """
        Given: Completed mission with results
        When: User asks short follow-up question
        Then: Fast path is activated
        """
        # Setup state with existing completed todolist
        mock_state_manager.load_state = AsyncMock(
            return_value={"todolist_id": "test-todolist-123"}
        )
        mock_todolist_manager.load_todolist = AsyncMock(
            return_value=completed_todolist
        )

        # Mock LLM to return a COMPLETE action (answering directly)
        mock_llm_provider.complete = AsyncMock(
            return_value={
                "success": True,
                "content": '{"step_ref": 1, "rationale": "Answering from context", "action": {"type": "complete", "summary": "The wiki page contains documentation."}, "expected_outcome": "User question answered"}',
            }
        )

        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            todolist_manager=mock_todolist_manager,
            system_prompt="You are a helpful assistant.",
            router=router,
            enable_fast_path=True,
        )

        result = await agent.execute(
            mission="Was steht da drin?",  # German: "What does it say?"
            session_id="test-session",
        )

        # Verify fast path was used
        assert result.status == "completed"
        assert any(
            entry.get("fast_path") for entry in result.execution_history
        ), "Fast path should have been used"

        # Verify todolist creation was NOT called (bypassed)
        mock_todolist_manager.create_todolist.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_path_used_for_new_mission(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
        mock_tool,
        router,
        completed_todolist,
    ):
        """
        Given: Previous mission completed
        When: User starts completely new mission
        Then: Full planning path is used
        """
        # Setup state with existing completed todolist
        mock_state_manager.load_state = AsyncMock(
            return_value={"todolist_id": "test-todolist-123"}
        )
        mock_todolist_manager.load_todolist = AsyncMock(
            return_value=completed_todolist
        )

        # Mock create_todolist to return a new plan
        new_todolist = TodoList(
            todolist_id="new-todolist-456",
            items=[
                TodoItem(
                    position=1,
                    description="Create FastAPI project",
                    acceptance_criteria="Project structure exists",
                    dependencies=[],
                    status=TaskStatus.PENDING,
                )
            ],
            open_questions=[],
            notes="New project plan",
        )
        mock_todolist_manager.create_todolist = AsyncMock(return_value=new_todolist)

        # Mock LLM for thought generation
        mock_llm_provider.complete = AsyncMock(
            return_value={
                "success": True,
                "content": '{"step_ref": 1, "rationale": "Starting new project", "action": {"type": "complete", "summary": "Project created successfully."}, "expected_outcome": "Project structure ready"}',
            }
        )

        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            todolist_manager=mock_todolist_manager,
            system_prompt="You are a helpful assistant.",
            router=router,
            enable_fast_path=True,
        )

        result = await agent.execute(
            mission="Create a new Python project with FastAPI and PostgreSQL",
            session_id="test-session",
        )

        # Verify full path was used (no fast_path flag in history)
        assert not any(
            entry.get("fast_path") for entry in result.execution_history
        ), "New mission should use full planning path"

    @pytest.mark.asyncio
    async def test_fast_path_disabled(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
        mock_tool,
        router,
        completed_todolist,
    ):
        """
        Given: Fast path is disabled in config
        When: User asks follow-up question
        Then: Full planning path is used
        """
        mock_state_manager.load_state = AsyncMock(
            return_value={"todolist_id": "test-todolist-123"}
        )
        mock_todolist_manager.load_todolist = AsyncMock(
            return_value=completed_todolist
        )

        # Create new todolist for the follow-up (since fast path is disabled)
        new_todolist = TodoList(
            todolist_id="new-todolist-789",
            items=[
                TodoItem(
                    position=1,
                    description="Answer user question",
                    acceptance_criteria="Question answered",
                    dependencies=[],
                    status=TaskStatus.PENDING,
                )
            ],
            open_questions=[],
            notes="Follow-up plan",
        )
        mock_todolist_manager.create_todolist = AsyncMock(return_value=new_todolist)

        mock_llm_provider.complete = AsyncMock(
            return_value={
                "success": True,
                "content": '{"step_ref": 1, "rationale": "Answering question", "action": {"type": "complete", "summary": "Answer provided."}, "expected_outcome": "Question answered"}',
            }
        )

        # Create agent with fast path DISABLED
        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            todolist_manager=mock_todolist_manager,
            system_prompt="You are a helpful assistant.",
            router=router,
            enable_fast_path=False,  # Disabled!
        )

        result = await agent.execute(
            mission="Was steht da drin?",
            session_id="test-session",
        )

        # Verify fast path was NOT used
        assert not any(
            entry.get("fast_path") for entry in result.execution_history
        ), "Fast path should not be used when disabled"


class TestFastPathWithToolCall:
    """Test fast-path behavior when tools need to be called."""

    @pytest.mark.asyncio
    async def test_fast_path_with_tool_call(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
        mock_tool,
        router,
        completed_todolist,
    ):
        """
        Given: Follow-up query that needs a tool call
        When: Fast path executes tool
        Then: Result is returned correctly
        """
        mock_state_manager.load_state = AsyncMock(
            return_value={"todolist_id": "test-todolist-123"}
        )
        mock_todolist_manager.load_todolist = AsyncMock(
            return_value=completed_todolist
        )

        # First LLM call: decide to call tool
        # Second LLM call: generate final response
        call_count = [0]

        async def mock_complete(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "success": True,
                    "content": '{"step_ref": 1, "rationale": "Need to fetch more data", "action": {"type": "tool_call", "tool": "test_tool", "tool_input": {}}, "expected_outcome": "Data retrieved"}',
                }
            else:
                return {
                    "success": True,
                    "content": '{"step_ref": 1, "rationale": "Generating answer", "action": {"type": "complete", "summary": "Here is the result from the tool."}, "expected_outcome": "Answer provided"}',
                }

        mock_llm_provider.complete = AsyncMock(side_effect=mock_complete)

        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            todolist_manager=mock_todolist_manager,
            system_prompt="You are a helpful assistant.",
            router=router,
            enable_fast_path=True,
        )

        result = await agent.execute(
            mission="Show me more details",
            session_id="test-session",
        )

        assert result.status == "completed"
        assert any(
            entry.get("fast_path") for entry in result.execution_history
        ), "Fast path should have been used"

        # Verify tool was called
        mock_tool.execute.assert_called_once()


class TestRouterDecisionLogging:
    """Test that router decisions are logged correctly."""

    @pytest.mark.asyncio
    async def test_route_decision_logged(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
        mock_tool,
        router,
        completed_todolist,
    ):
        """
        Given: Fast path is enabled
        When: Query is classified
        Then: Route decision is logged
        """
        mock_state_manager.load_state = AsyncMock(
            return_value={"todolist_id": "test-todolist-123"}
        )
        mock_todolist_manager.load_todolist = AsyncMock(
            return_value=completed_todolist
        )

        mock_llm_provider.complete = AsyncMock(
            return_value={
                "success": True,
                "content": '{"step_ref": 1, "rationale": "Direct answer", "action": {"type": "complete", "summary": "Answer."}, "expected_outcome": "Done"}',
            }
        )

        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            todolist_manager=mock_todolist_manager,
            system_prompt="You are a helpful assistant.",
            router=router,
            enable_fast_path=True,
        )

        with patch.object(agent.logger, "info") as mock_log:
            await agent.execute(
                mission="What is that?",
                session_id="test-session",
            )

            # Check that route_decision was logged
            route_decision_calls = [
                call for call in mock_log.call_args_list
                if call[0][0] == "route_decision"
            ]
            assert len(route_decision_calls) >= 1, "route_decision should be logged"


class TestFastPathFallback:
    """Test fallback to full path when fast path fails."""

    @pytest.mark.asyncio
    async def test_fallback_to_full_path_on_tool_failure(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
        mock_tool,
        router,
        completed_todolist,
    ):
        """
        Given: Fast path tool call fails
        When: Fallback is triggered
        Then: Full path is executed
        """
        mock_state_manager.load_state = AsyncMock(
            return_value={"todolist_id": "test-todolist-123"}
        )
        mock_todolist_manager.load_todolist = AsyncMock(
            return_value=completed_todolist
        )

        # Mock tool to fail
        mock_tool.execute = AsyncMock(
            return_value={
                "success": False,
                "error": "Tool failed",
            }
        )

        # Create fallback todolist
        fallback_todolist = TodoList(
            todolist_id="fallback-todolist",
            items=[
                TodoItem(
                    position=1,
                    description="Handle query",
                    acceptance_criteria="Query handled",
                    dependencies=[],
                    status=TaskStatus.PENDING,
                )
            ],
            open_questions=[],
            notes="Fallback plan",
        )
        mock_todolist_manager.create_todolist = AsyncMock(return_value=fallback_todolist)

        # LLM calls for fast path (tool call) and then full path
        call_count = [0]

        async def mock_complete(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: fast path decides to call tool
                return {
                    "success": True,
                    "content": '{"step_ref": 1, "rationale": "Need tool", "action": {"type": "tool_call", "tool": "test_tool", "tool_input": {}}, "expected_outcome": "Data"}',
                }
            else:
                # Subsequent calls: full path
                return {
                    "success": True,
                    "content": '{"step_ref": 1, "rationale": "Full path", "action": {"type": "complete", "summary": "Done via full path."}, "expected_outcome": "Done"}',
                }

        mock_llm_provider.complete = AsyncMock(side_effect=mock_complete)

        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            todolist_manager=mock_todolist_manager,
            system_prompt="You are a helpful assistant.",
            router=router,
            enable_fast_path=True,
        )

        result = await agent.execute(
            mission="Tell me about this",
            session_id="test-session",
        )

        assert result.status == "completed"
        # Should have both fast_path entries and non-fast_path entries
        # due to fallback

