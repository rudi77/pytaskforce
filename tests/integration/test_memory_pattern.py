"""
Integration tests for Memory Pattern (Story 4.2).

Tests verify that:
- Agent uses cached results instead of re-calling tools
- PREVIOUS_RESULTS context includes full history
- Cache statistics are tracked correctly
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from taskforce.core.domain.agent import Agent
from taskforce.core.domain.events import Action, ActionType, Observation
from taskforce.core.interfaces.todolist import TaskStatus, TodoItem, TodoList
from taskforce.infrastructure.cache.tool_cache import ToolResultCache


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
    return manager


@pytest.fixture
def mock_wiki_tool():
    """Create mock wiki tool that returns page tree."""
    tool = MagicMock()
    tool.name = "wiki_get_page_tree"
    tool.description = "Get wiki page tree"
    tool.parameters_schema = {"type": "object", "properties": {}}
    tool.execute = AsyncMock(
        return_value={
            "success": True,
            "pages": [
                {"title": "Home", "id": 1},
                {"title": "Copilot", "id": 42},
            ],
        }
    )
    return tool


@pytest.fixture
def mock_file_tool():
    """Create mock file read tool."""
    tool = MagicMock()
    tool.name = "file_read"
    tool.description = "Read file content"
    tool.parameters_schema = {"type": "object", "properties": {}}
    tool.execute = AsyncMock(
        return_value={
            "success": True,
            "content": "File content here",
        }
    )
    return tool


class TestToolCacheIntegration:
    """Integration tests for tool result caching."""

    @pytest.mark.asyncio
    async def test_cache_hit_prevents_tool_call(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
        mock_wiki_tool,
    ):
        """
        Given: Cache contains result for wiki_get_page_tree
        When: Agent executes tool with same parameters
        Then: Tool is NOT called, cached result is returned
        """
        cache = ToolResultCache()
        cached_result = {
            "success": True,
            "pages": [{"title": "Cached", "id": 99}],
        }
        cache.put("wiki_get_page_tree", {"path": "/wiki"}, cached_result)

        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_wiki_tool],
            todolist_manager=mock_todolist_manager,
            system_prompt="Test prompt",
            tool_cache=cache,
        )

        step = TodoItem(
            position=1,
            description="Get wiki pages",
            acceptance_criteria="Pages retrieved",
            dependencies=[],
            status=TaskStatus.PENDING,
        )

        action = Action(
            type=ActionType.TOOL_CALL,
            tool="wiki_get_page_tree",
            tool_input={"path": "/wiki"},
        )

        observation = await agent._execute_tool(action, step)

        # Tool should NOT have been called
        mock_wiki_tool.execute.assert_not_called()

        # Should return cached result
        assert observation.success is True
        assert observation.data["pages"][0]["title"] == "Cached"

        # Cache stats should show hit
        assert cache.stats["hits"] == 1
        assert cache.stats["misses"] == 0

    @pytest.mark.asyncio
    async def test_cache_miss_calls_tool_and_caches(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
        mock_wiki_tool,
    ):
        """
        Given: Empty cache
        When: Agent executes cacheable tool
        Then: Tool is called and result is cached
        """
        cache = ToolResultCache()

        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_wiki_tool],
            todolist_manager=mock_todolist_manager,
            system_prompt="Test prompt",
            tool_cache=cache,
        )

        step = TodoItem(
            position=1,
            description="Get wiki pages",
            acceptance_criteria="Pages retrieved",
            dependencies=[],
            status=TaskStatus.PENDING,
        )

        action = Action(
            type=ActionType.TOOL_CALL,
            tool="wiki_get_page_tree",
            tool_input={"path": "/wiki"},
        )

        observation = await agent._execute_tool(action, step)

        # Tool should have been called
        mock_wiki_tool.execute.assert_called_once_with(path="/wiki")

        # Should return tool result
        assert observation.success is True
        assert len(observation.data["pages"]) == 2

        # Result should be cached
        cached = cache.get("wiki_get_page_tree", {"path": "/wiki"})
        assert cached is not None
        assert cached["success"] is True

    @pytest.mark.asyncio
    async def test_non_cacheable_tool_not_cached(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
    ):
        """
        Given: A write tool (non-cacheable)
        When: Agent executes the tool
        Then: Result is NOT cached
        """
        # Create a file_write tool (not in CACHEABLE_TOOLS)
        write_tool = MagicMock()
        write_tool.name = "file_write"
        write_tool.description = "Write file"
        write_tool.parameters_schema = {"type": "object", "properties": {}}
        write_tool.execute = AsyncMock(return_value={"success": True})

        cache = ToolResultCache()

        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[write_tool],
            todolist_manager=mock_todolist_manager,
            system_prompt="Test prompt",
            tool_cache=cache,
        )

        step = TodoItem(
            position=1,
            description="Write file",
            acceptance_criteria="File written",
            dependencies=[],
            status=TaskStatus.PENDING,
        )

        action = Action(
            type=ActionType.TOOL_CALL,
            tool="file_write",
            tool_input={"path": "/test.txt", "content": "Hello"},
        )

        await agent._execute_tool(action, step)

        # Tool should have been called
        write_tool.execute.assert_called_once()

        # Result should NOT be cached
        assert cache.size == 0

    @pytest.mark.asyncio
    async def test_agent_without_cache_works_normally(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
        mock_wiki_tool,
    ):
        """
        Given: Agent created without tool_cache
        When: Agent executes tools
        Then: Tools are called normally without caching
        """
        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_wiki_tool],
            todolist_manager=mock_todolist_manager,
            system_prompt="Test prompt",
            tool_cache=None,  # No cache
        )

        step = TodoItem(
            position=1,
            description="Get wiki pages",
            acceptance_criteria="Pages retrieved",
            dependencies=[],
            status=TaskStatus.PENDING,
        )

        action = Action(
            type=ActionType.TOOL_CALL,
            tool="wiki_get_page_tree",
            tool_input={"path": "/wiki"},
        )

        # First call
        await agent._execute_tool(action, step)
        assert mock_wiki_tool.execute.call_count == 1

        # Second call - should still call tool (no cache)
        await agent._execute_tool(action, step)
        assert mock_wiki_tool.execute.call_count == 2


class TestBuildThoughtContext:
    """Tests for enriched context building."""

    def test_context_includes_full_previous_results(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
    ):
        """
        Given: TodoList with many completed steps
        When: Building thought context
        Then: All previous results are included (not truncated)
        """
        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[],
            todolist_manager=mock_todolist_manager,
            system_prompt="Test prompt",
        )

        # Create todolist with 10 completed steps
        items = []
        for i in range(1, 11):
            item = TodoItem(
                position=i,
                description=f"Step {i}",
                acceptance_criteria=f"Criteria {i}",
                dependencies=[],
                status=TaskStatus.COMPLETED,
                chosen_tool="test_tool",
                execution_result={"result": f"data_{i}"},
            )
            items.append(item)

        # Add current step
        current_step = TodoItem(
            position=11,
            description="Current step",
            acceptance_criteria="Current criteria",
            dependencies=[],
            status=TaskStatus.PENDING,
        )
        items.append(current_step)

        todolist = TodoList(
            todolist_id="test-list",
            items=items,
            open_questions=[],
            notes="Test mission",
        )

        context = agent._build_thought_context(current_step, todolist, {})

        # Should include ALL 10 previous results
        assert len(context["previous_results"]) == 10
        assert context["previous_results"][0]["result"]["result"] == "data_1"
        assert context["previous_results"][9]["result"]["result"] == "data_10"

    def test_context_includes_cache_info(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
    ):
        """
        Given: Agent with tool cache
        When: Building thought context
        Then: Cache info is included in context
        """
        cache = ToolResultCache()
        cache.get("tool", {"key": "value"})  # Generate a miss

        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[],
            todolist_manager=mock_todolist_manager,
            system_prompt="Test prompt",
            tool_cache=cache,
        )

        step = TodoItem(
            position=1,
            description="Test",
            acceptance_criteria="Test",
            dependencies=[],
            status=TaskStatus.PENDING,
        )

        todolist = TodoList(
            todolist_id="test-list",
            items=[step],
            open_questions=[],
            notes="Test",
        )

        context = agent._build_thought_context(step, todolist, {})

        assert context["cache_info"] is not None
        assert context["cache_info"]["enabled"] is True
        assert context["cache_info"]["stats"]["misses"] == 1
        assert "hint" in context["cache_info"]

    def test_context_includes_conversation_history(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
    ):
        """
        Given: State with conversation history
        When: Building thought context
        Then: Conversation history is included
        """
        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[],
            todolist_manager=mock_todolist_manager,
            system_prompt="Test prompt",
        )

        step = TodoItem(
            position=1,
            description="Test",
            acceptance_criteria="Test",
            dependencies=[],
            status=TaskStatus.PENDING,
        )

        todolist = TodoList(
            todolist_id="test-list",
            items=[step],
            open_questions=[],
            notes="Test",
        )

        state = {
            "conversation_history": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ]
        }

        context = agent._build_thought_context(step, todolist, state)

        assert len(context["conversation_history"]) == 2
        assert context["conversation_history"][0]["role"] == "user"


class TestCacheableToolsWhitelist:
    """Tests for cacheable tools whitelist."""

    def test_read_only_tools_are_cacheable(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
    ):
        """Test that read-only tools are in CACHEABLE_TOOLS."""
        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[],
            todolist_manager=mock_todolist_manager,
            system_prompt="Test prompt",
        )

        cacheable = [
            "wiki_get_page",
            "wiki_get_page_tree",
            "wiki_search",
            "file_read",
            "semantic_search",
            "web_search",
            "get_document",
            "list_documents",
        ]

        for tool_name in cacheable:
            assert agent._is_cacheable_tool(tool_name), f"{tool_name} should be cacheable"

    def test_write_tools_not_cacheable(
        self,
        mock_state_manager,
        mock_llm_provider,
        mock_todolist_manager,
    ):
        """Test that write/mutation tools are NOT cacheable."""
        agent = Agent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[],
            todolist_manager=mock_todolist_manager,
            system_prompt="Test prompt",
        )

        not_cacheable = [
            "file_write",
            "git_commit",
            "powershell",
            "ask_user",
            "llm_generate",
        ]

        for tool_name in not_cacheable:
            assert not agent._is_cacheable_tool(tool_name), f"{tool_name} should NOT be cacheable"

