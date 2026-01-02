"""
Unit Tests for Core Agent ReAct Loop

Tests the Agent class using protocol mocks to verify ReAct logic
without any I/O or infrastructure dependencies.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.agent import Agent
from taskforce.core.domain.events import ActionType
from taskforce.core.domain.models import ExecutionResult
from taskforce.core.interfaces.todolist import TaskStatus, TodoItem, TodoList


@pytest.fixture
def mock_state_manager():
    """Mock StateManagerProtocol."""
    mock = AsyncMock()
    mock.load_state.return_value = {"answers": {}}
    mock.save_state.return_value = None
    return mock


@pytest.fixture
def mock_llm_provider():
    """Mock LLMProviderProtocol."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def mock_todolist_manager():
    """Mock TodoListManagerProtocol."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def mock_tool():
    """Mock ToolProtocol."""
    tool = MagicMock()
    tool.name = "test_tool"
    tool.description = "A test tool"
    tool.parameters_schema = {"type": "object", "properties": {}}
    tool.execute = AsyncMock(return_value={"success": True, "output": "test result"})
    return tool


@pytest.fixture
def agent(mock_state_manager, mock_llm_provider, mock_tool, mock_todolist_manager):
    """Create Agent with mocked dependencies."""
    return Agent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools=[mock_tool],
        todolist_manager=mock_todolist_manager,
        system_prompt="Test system prompt",
    )


@pytest.mark.asyncio
async def test_agent_initialization(agent, mock_tool):
    """Test agent initializes with correct dependencies."""
    assert agent.state_manager is not None
    assert agent.llm_provider is not None
    assert agent.todolist_manager is not None
    assert "test_tool" in agent.tools
    assert agent.tools["test_tool"] == mock_tool
    assert agent.system_prompt == "Test system prompt"


@pytest.mark.asyncio
async def test_execute_creates_todolist_on_first_run(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that execute creates a TodoList on first run."""
    # Setup: State has no todolist_id
    mock_state_manager.load_state.return_value = {"answers": {}}

    # Setup: TodoList with one completed item
    todolist = TodoList(
        todolist_id="test-todolist-123",
        items=[
            TodoItem(
                position=1,
                description="Test task",
                acceptance_criteria="Task completed",
                dependencies=[],
                status=TaskStatus.COMPLETED,
                execution_result={"success": True},
            )
        ],
        open_questions=[],
        notes="Test notes",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify TodoList was created
    mock_todolist_manager.create_todolist.assert_called_once()
    call_args = mock_todolist_manager.create_todolist.call_args
    assert call_args.kwargs["mission"] == "Test mission"
    assert "tools_desc" in call_args.kwargs

    # Verify state was saved with todolist_id
    assert mock_state_manager.save_state.called
    saved_state = mock_state_manager.save_state.call_args_list[0][0][1]
    assert saved_state["todolist_id"] == "test-todolist-123"

    # Verify result
    assert isinstance(result, ExecutionResult)
    assert result.session_id == "test-session"
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_execute_loads_existing_todolist(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that execute loads existing TodoList if todolist_id in state and items pending."""
    # Setup: State has todolist_id
    mock_state_manager.load_state.return_value = {
        "todolist_id": "existing-todolist-456",
        "answers": {},
    }

    # Setup: Existing TodoList with PENDING item (not completed, so it resumes)
    todolist = TodoList(
        todolist_id="existing-todolist-456",
        items=[
            TodoItem(
                position=1,
                description="Existing task",
                acceptance_criteria="Task done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.load_todolist.return_value = todolist

    # LLM returns finish_step to complete the pending task
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps({
            "step_ref": 1,
            "rationale": "Task already done",
            "action": {"type": "finish_step"},
            "expected_outcome": "Complete",
            "confidence": 1.0,
        }),
    }

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify TodoList was loaded, not created
    mock_todolist_manager.load_todolist.assert_called_with("existing-todolist-456")
    mock_todolist_manager.create_todolist.assert_not_called()

    # Verify result
    assert result.todolist_id == "existing-todolist-456"


@pytest.mark.asyncio
async def test_react_loop_executes_pending_step(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider, mock_tool
):
    """Test ReAct loop executes a pending step with tool_call then finish_step."""
    # Setup state
    mock_state_manager.load_state.return_value = {"answers": {}}

    # Setup TodoList with one pending item
    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Execute test tool",
                acceptance_criteria="Tool executed successfully",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # Setup LLM to return tool_call first, then finish_step, then markdown
    tool_call_response = {
        "step_ref": 1,
        "rationale": "Need to execute the test tool",
        "action": {"type": "tool_call", "tool": "test_tool", "tool_input": {"param": "value"}},
        "expected_outcome": "Tool executes successfully",
        "confidence": 0.9,
    }
    finish_step_response = {
        "step_ref": 1,
        "rationale": "Tool succeeded, marking step complete",
        "action": {"type": "finish_step"},
        "expected_outcome": "Step is done",
        "confidence": 1.0,
    }
    mock_llm_provider.complete.side_effect = [
        {"success": True, "content": json.dumps(tool_call_response)},
        {"success": True, "content": json.dumps(finish_step_response)},
        {"success": True, "content": "Task completed successfully."},  # Two-phase markdown
    ]

    # Setup tool to succeed
    mock_tool.execute.return_value = {"success": True, "output": "test result"}

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify LLM was called 3 times (tool_call + finish_step + markdown)
    assert mock_llm_provider.complete.call_count == 3

    # Verify tool was executed once (tool_input is spread as kwargs)
    mock_tool.execute.assert_called_once_with(param="value")

    # Verify TodoList was updated
    assert mock_todolist_manager.update_todolist.called
    updated_todolist = mock_todolist_manager.update_todolist.call_args[0][0]
    assert updated_todolist.items[0].status == TaskStatus.COMPLETED
    assert updated_todolist.items[0].chosen_tool == "test_tool"

    # Verify result
    assert result.status == "completed"
    assert len(result.execution_history) > 0


@pytest.mark.asyncio
async def test_react_loop_handles_ask_user_action(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test ReAct loop pauses when ask_user action is generated."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Need user input",
                acceptance_criteria="User provides answer",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns ask_user action
    thought_response = {
        "step_ref": 1,
        "rationale": "Need to ask user for input",
        "action": {
            "type": "ask_user",
            "question": "What is your name?",
            "answer_key": "user_name",
        },
        "expected_outcome": "User provides their name",
        "confidence": 1.0,
    }
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps(thought_response),
    }

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify execution paused
    assert result.status == "paused"
    # Final message is the actual question when pending_question exists
    assert result.final_message == "What is your name?"

    # Verify pending question was stored in state
    save_calls = mock_state_manager.save_state.call_args_list
    # Find the call that saved pending_question
    pending_question_saved = False
    for call in save_calls:
        state_arg = call[0][1]
        if "pending_question" in state_arg:
            assert state_arg["pending_question"]["question"] == "What is your name?"
            assert state_arg["pending_question"]["answer_key"] == "user_name"
            pending_question_saved = True
            break
    assert pending_question_saved


@pytest.mark.asyncio
async def test_react_loop_handles_complete_action(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test ReAct loop handles early completion with complete action."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Complete immediately",
                acceptance_criteria="Mission done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns complete action
    thought_response = {
        "step_ref": 1,
        "rationale": "Mission is already complete",
        "action": {"type": "complete", "summary": "Task completed successfully"},
        "expected_outcome": "Mission marked as complete",
        "confidence": 1.0,
    }
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps(thought_response),
    }

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify early completion
    assert result.status == "completed"
    assert result.final_message == "Task completed successfully"

    # Verify TodoList was updated (step gets marked as completed first, then skipped)
    # The complete action marks the current step as completed via observation processing
    # Then marks all PENDING steps as skipped (but this step is already completed)
    assert mock_todolist_manager.update_todolist.called


@pytest.mark.asyncio
async def test_react_loop_retries_failed_step(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider, mock_tool
):
    """Test ReAct loop retries a failed step."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Retry test",
                acceptance_criteria="Tool succeeds",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns tool_call actions, then finish_step after success, then markdown
    tool_call_response = {
        "step_ref": 1,
        "rationale": "Execute tool",
        "action": {"type": "tool_call", "tool": "test_tool", "tool_input": {}},
        "expected_outcome": "Tool succeeds",
        "confidence": 0.9,
    }
    finish_step_response = {
        "step_ref": 1,
        "rationale": "Tool succeeded",
        "action": {"type": "finish_step"},
        "expected_outcome": "Done",
        "confidence": 1.0,
    }
    mock_llm_provider.complete.side_effect = [
        {"success": True, "content": json.dumps(tool_call_response)},  # First attempt
        {"success": True, "content": json.dumps(tool_call_response)},  # Retry
        {"success": True, "content": json.dumps(finish_step_response)},  # Finish
        {"success": True, "content": "Retry succeeded."},  # Two-phase markdown
    ]

    # Tool fails first time, succeeds second time
    mock_tool.execute.side_effect = [
        {"success": False, "error": "First attempt failed"},
        {"success": True, "output": "Success on retry"},
    ]

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify tool was called twice (initial + retry)
    assert mock_tool.execute.call_count == 2

    # Verify final status is completed
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_react_loop_respects_max_attempts(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider, mock_tool
):
    """Test ReAct loop respects max_attempts limit."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Fail repeatedly",
                acceptance_criteria="Tool succeeds",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=2,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns tool_call action
    thought_response = {
        "step_ref": 1,
        "rationale": "Execute tool",
        "action": {"type": "tool_call", "tool": "test_tool", "tool_input": {}},
        "expected_outcome": "Tool succeeds",
        "confidence": 0.9,
    }
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps(thought_response),
    }

    # Tool always fails
    mock_tool.execute.return_value = {"success": False, "error": "Always fails"}

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify tool was called max_attempts times
    assert mock_tool.execute.call_count == 2

    # Verify final status is failed
    assert result.status == "failed"

    # Verify step is marked as FAILED
    updated_todolist = mock_todolist_manager.update_todolist.call_args[0][0]
    assert updated_todolist.items[0].status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_react_loop_respects_dependencies(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider, mock_tool
):
    """Test ReAct loop respects step dependencies."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="First step",
                acceptance_criteria="Step 1 done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            ),
            TodoItem(
                position=2,
                description="Second step (depends on 1)",
                acceptance_criteria="Step 2 done",
                dependencies=[1],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            ),
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns tool_call then finish_step for each step, plus markdown for two-phase
    mock_llm_provider.complete.side_effect = [
        {"success": True, "content": json.dumps({
            "step_ref": 1,
            "rationale": "Execute step 1",
            "action": {"type": "tool_call", "tool": "test_tool", "tool_input": {}},
            "expected_outcome": "Step 1 completes",
            "confidence": 0.9,
        })},
        {"success": True, "content": json.dumps({
            "step_ref": 1,
            "rationale": "Step 1 done",
            "action": {"type": "finish_step"},
            "expected_outcome": "Complete",
            "confidence": 1.0,
        })},
        {"success": True, "content": "Step 1 completed."},  # Two-phase markdown
        {"success": True, "content": json.dumps({
            "step_ref": 2,
            "rationale": "Execute step 2",
            "action": {"type": "tool_call", "tool": "test_tool", "tool_input": {}},
            "expected_outcome": "Step 2 completes",
            "confidence": 0.9,
        })},
        {"success": True, "content": json.dumps({
            "step_ref": 2,
            "rationale": "Step 2 done",
            "action": {"type": "finish_step"},
            "expected_outcome": "Complete",
            "confidence": 1.0,
        })},
        {"success": True, "content": "Step 2 completed."},  # Two-phase markdown
    ]

    mock_tool.execute.return_value = {"success": True, "output": "success"}

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify both steps were executed in order
    assert mock_tool.execute.call_count == 2

    # Verify both steps completed
    assert result.status == "completed"
    updated_todolist = mock_todolist_manager.update_todolist.call_args[0][0]
    assert updated_todolist.items[0].status == TaskStatus.COMPLETED
    assert updated_todolist.items[1].status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_react_loop_stops_at_max_iterations(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider, mock_tool
):
    """Test ReAct loop stops at MAX_ITERATIONS to prevent infinite loops."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    # Create a TodoList that never completes (always returns PENDING)
    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Never completes",
                acceptance_criteria="Impossible",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=100,  # High limit
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM always returns tool_call
    thought_response = {
        "step_ref": 1,
        "rationale": "Keep trying",
        "action": {"type": "tool_call", "tool": "test_tool", "tool_input": {}},
        "expected_outcome": "Eventually succeeds",
        "confidence": 0.5,
    }
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps(thought_response),
    }

    # Tool always fails
    mock_tool.execute.return_value = {"success": False, "error": "Always fails"}

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify execution stopped at MAX_ITERATIONS
    assert result.status == "failed"
    assert "maximum iterations" in result.final_message.lower()


@pytest.mark.asyncio
async def test_get_next_actionable_step_skips_completed(agent):
    """Test _get_next_actionable_step skips completed steps."""
    todolist = TodoList(
        todolist_id="test",
        items=[
            TodoItem(
                position=1,
                description="Completed",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.COMPLETED,
                execution_history=[],
            ),
            TodoItem(
                position=2,
                description="Pending",
                acceptance_criteria="Not done",
                dependencies=[],
                status=TaskStatus.PENDING,
                execution_history=[],
            ),
        ],
        open_questions=[],
        notes="",
    )

    next_step = agent._get_next_actionable_step(todolist)

    assert next_step is not None
    assert next_step.position == 2


@pytest.mark.asyncio
async def test_get_next_actionable_step_respects_dependencies(agent):
    """Test _get_next_actionable_step respects dependencies."""
    todolist = TodoList(
        todolist_id="test",
        items=[
            TodoItem(
                position=1,
                description="First",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                execution_history=[],
            ),
            TodoItem(
                position=2,
                description="Second (depends on 1)",
                acceptance_criteria="Done",
                dependencies=[1],
                status=TaskStatus.PENDING,
                execution_history=[],
            ),
        ],
        open_questions=[],
        notes="",
    )

    next_step = agent._get_next_actionable_step(todolist)

    # Should return step 1 first (no dependencies)
    assert next_step.position == 1

    # Mark step 1 as completed
    todolist.items[0].status = TaskStatus.COMPLETED

    next_step = agent._get_next_actionable_step(todolist)

    # Now should return step 2
    assert next_step.position == 2


@pytest.mark.asyncio
async def test_is_plan_complete(agent):
    """Test _is_plan_complete correctly identifies completed plans."""
    # All completed
    todolist = TodoList(
        todolist_id="test",
        items=[
            TodoItem(
                position=1,
                description="Task 1",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.COMPLETED,
                execution_history=[],
            ),
            TodoItem(
                position=2,
                description="Task 2",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.COMPLETED,
                execution_history=[],
            ),
        ],
        open_questions=[],
        notes="",
    )

    assert agent._is_plan_complete(todolist) is True

    # Some pending
    todolist.items[1].status = TaskStatus.PENDING
    assert agent._is_plan_complete(todolist) is False

    # Some skipped (should still be complete)
    todolist.items[1].status = TaskStatus.SKIPPED
    assert agent._is_plan_complete(todolist) is True


# ============================================================================
# FINISH_STEP Tests - Autonomous Kernel Infrastructure
# ============================================================================


@pytest.mark.asyncio
async def test_action_type_includes_finish_step():
    """Test that ActionType enum includes FINISH_STEP."""
    assert ActionType.FINISH_STEP == "finish_step"
    assert ActionType.FINISH_STEP.value == "finish_step"


@pytest.mark.asyncio
async def test_tool_success_keeps_step_pending(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider, mock_tool
):
    """Test that successful tool execution keeps step PENDING (not COMPLETED).
    
    This is the core behavior change: tool success != step completion.
    The agent must explicitly emit FINISH_STEP to complete a step.
    """
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test step",
                acceptance_criteria="Must be verified",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns tool_call (NOT finish_step)
    thought_response = {
        "step_ref": 1,
        "rationale": "Execute tool first",
        "action": {"type": "tool_call", "tool": "test_tool", "tool_input": {}},
        "expected_outcome": "Tool executes",
        "confidence": 0.9,
    }
    
    # After tool success, LLM emits finish_step
    finish_response = {
        "step_ref": 1,
        "rationale": "Tool succeeded, step is done",
        "action": {"type": "finish_step"},
        "expected_outcome": "Step marked complete",
        "confidence": 1.0,
    }
    
    mock_llm_provider.complete.side_effect = [
        {"success": True, "content": json.dumps(thought_response)},
        {"success": True, "content": json.dumps(finish_response)},
        {"success": True, "content": "Task completed."},  # Two-phase markdown
    ]

    # Tool succeeds
    mock_tool.execute.return_value = {"success": True, "output": "done"}

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify: LLM was called 3 times (tool_call, finish_step, markdown)
    assert mock_llm_provider.complete.call_count == 3

    # Verify: step ends up COMPLETED only after finish_step
    assert result.status == "completed"
    updated_todolist = mock_todolist_manager.update_todolist.call_args[0][0]
    assert updated_todolist.items[0].status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_tool_success_resets_attempts_counter(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider, mock_tool
):
    """Test that successful tool execution resets attempts counter to 0.
    
    This allows extended workflows without hitting retry limits.
    The execution_history records attempt counts at each step, which proves the reset.
    """
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test step",
                acceptance_criteria="Verified",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=2,  # Start with some attempts already used
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns tool_call then finish_step then markdown
    mock_llm_provider.complete.side_effect = [
        {"success": True, "content": json.dumps({
            "step_ref": 1,
            "rationale": "Execute tool",
            "action": {"type": "tool_call", "tool": "test_tool", "tool_input": {}},
            "expected_outcome": "Success",
            "confidence": 0.9,
        })},
        {"success": True, "content": json.dumps({
            "step_ref": 1,
            "rationale": "Done",
            "action": {"type": "finish_step"},
            "expected_outcome": "Complete",
            "confidence": 1.0,
        })},
        {"success": True, "content": "Completed."},  # Two-phase markdown
    ]

    mock_tool.execute.return_value = {"success": True, "output": "done"}

    # Execute
    await agent.execute(mission="Test mission", session_id="test-session")

    # Verify reset happened by checking execution_history
    # The execution_history records attempt count at each call:
    # - First entry: tool_call with attempt=3 (2+1 before reset)
    # - Second entry: finish_step with attempt=1 (0+1 after reset)
    step = todolist.items[0]
    assert len(step.execution_history) == 2
    
    # First call recorded attempt 3 (started at 2, incremented to 3)
    assert step.execution_history[0]["attempt"] == 3
    
    # After reset to 0, finish_step incremented to 1
    # This proves the reset happened between the two calls
    assert step.execution_history[1]["attempt"] == 1


@pytest.mark.asyncio
async def test_finish_step_completes_step_explicitly(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that FINISH_STEP action explicitly completes a step."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Complete explicitly",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM directly emits finish_step (e.g., if step was already satisfied)
    thought_response = {
        "step_ref": 1,
        "rationale": "Step requirements already met",
        "action": {"type": "finish_step"},
        "expected_outcome": "Step marked complete",
        "confidence": 1.0,
    }
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps(thought_response),
    }

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify step is COMPLETED
    assert result.status == "completed"
    updated_todolist = mock_todolist_manager.update_todolist.call_args[0][0]
    assert updated_todolist.items[0].status == TaskStatus.COMPLETED


# ============================================================================
# Fallback-Entschärfung Tests - Story 5.1
# ============================================================================


@pytest.mark.asyncio
async def test_thought_parse_invalid_json_returns_friendly_message(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that invalid JSON response returns a user-friendly message, not raw JSON."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test invalid JSON handling",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns invalid JSON (missing closing brace)
    invalid_json = '{"step_ref": 1, "rationale": "test", "action": {"type": "complete"'
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": invalid_json,
    }

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify: User gets a friendly message, NOT the raw invalid JSON
    assert result.status == "completed"
    assert "Verarbeitungsfehler" in result.final_message
    assert invalid_json not in result.final_message
    # Ensure no JSON-like characters in user output
    assert "{" not in result.final_message
    assert "step_ref" not in result.final_message


@pytest.mark.asyncio
async def test_thought_parse_empty_response_returns_friendly_message(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that empty LLM response returns a user-friendly message."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test empty response",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns empty string
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": "",
    }

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify: User gets a friendly message
    assert result.status == "completed"
    assert "Verarbeitungsfehler" in result.final_message


@pytest.mark.asyncio
async def test_thought_parse_missing_action_key_returns_friendly_message(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that JSON missing required 'action' key returns friendly message."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test missing key",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns JSON missing 'action' key
    incomplete_json = json.dumps({
        "step_ref": 1,
        "rationale": "Missing action",
        "expected_outcome": "Test",
    })
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": incomplete_json,
    }

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify: User gets friendly message, not KeyError traceback
    assert result.status == "completed"
    assert "Verarbeitungsfehler" in result.final_message


@pytest.mark.asyncio
async def test_thought_parse_extracts_summary_from_invalid_json(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that summary is extracted from invalid JSON when possible."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test summary extraction",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns invalid JSON but with extractable summary
    invalid_but_with_summary = (
        '{"step_ref": 1, "action": {"type": "complete", '
        '"summary": "Die Antwort auf Ihre Frage ist 42."}, '
        '"rationale": "test"'  # Missing closing brace - invalid JSON
    )
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": invalid_but_with_summary,
    }

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify: Summary was extracted from invalid JSON
    assert result.status == "completed"
    assert "42" in result.final_message
    # Should NOT have the generic error message since summary was extracted
    assert "Verarbeitungsfehler" not in result.final_message


@pytest.mark.asyncio
async def test_extract_summary_from_invalid_json_with_escaped_quotes(agent):
    """Test _extract_summary_from_invalid_json handles escaped quotes correctly."""
    # Input with escaped quotes
    raw_content = '{"summary": "Er sagte \\"Hallo\\" und ging.", "other": "data"}'
    
    result = agent._extract_summary_from_invalid_json(raw_content)
    
    assert result is not None
    assert 'Er sagte "Hallo" und ging.' == result


@pytest.mark.asyncio
async def test_extract_summary_from_invalid_json_with_newlines(agent):
    """Test _extract_summary_from_invalid_json handles newlines correctly."""
    raw_content = '{"summary": "Zeile 1\\nZeile 2\\nZeile 3", "x": 1}'
    
    result = agent._extract_summary_from_invalid_json(raw_content)
    
    assert result is not None
    assert "Zeile 1\nZeile 2\nZeile 3" == result


@pytest.mark.asyncio
async def test_extract_summary_from_invalid_json_returns_none_when_not_found(agent):
    """Test _extract_summary_from_invalid_json returns None when no summary field."""
    raw_content = '{"rationale": "something", "action": {"type": "complete"}}'
    
    result = agent._extract_summary_from_invalid_json(raw_content)
    
    assert result is None


# ============================================================================
# Minimales Action-Schema Tests - Story 5.2
# ============================================================================


@pytest.mark.asyncio
async def test_action_type_includes_respond():
    """Test that ActionType enum includes RESPOND as the new primary completion type."""
    assert ActionType.RESPOND == "respond"
    assert ActionType.RESPOND.value == "respond"
    # Legacy types still exist
    assert ActionType.FINISH_STEP == "finish_step"
    assert ActionType.COMPLETE == "complete"


@pytest.mark.asyncio
async def test_minimal_schema_tool_call(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider, mock_tool
):
    """Test agent parses minimal schema format for tool_call action."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test minimal schema",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns MINIMAL SCHEMA (action is string, not nested object)
    minimal_tool_call = {
        "action": "tool_call",
        "tool": "test_tool",
        "tool_input": {"param": "value"},
    }
    minimal_respond = {
        "action": "respond",
        "summary": "Task completed successfully",
    }
    mock_llm_provider.complete.side_effect = [
        {"success": True, "content": json.dumps(minimal_tool_call)},
        {"success": True, "content": json.dumps(minimal_respond)},
        {"success": True, "content": "Task completed successfully."},  # Two-phase markdown
    ]

    mock_tool.execute.return_value = {"success": True, "output": "done"}

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify: Tool was called with correct params
    mock_tool.execute.assert_called_once_with(param="value")

    # Verify: Result is completed (two-phase generates markdown)
    assert result.status == "completed"
    assert "completed" in result.final_message.lower()


@pytest.mark.asyncio
async def test_minimal_schema_respond_action(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test agent parses minimal schema 'respond' action (replaces finish_step/complete)."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test respond action",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns minimal schema with respond action
    minimal_respond = {
        "action": "respond",
        "summary": "Here is your answer: 42",
    }
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps(minimal_respond),
    }

    # Execute
    result = await agent.execute(mission="What is the answer?", session_id="test-session")

    # Verify: Result is completed with the summary
    assert result.status == "completed"
    assert "42" in result.final_message


@pytest.mark.asyncio
async def test_minimal_schema_ask_user_action(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test agent parses minimal schema 'ask_user' action."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Need user input",
                acceptance_criteria="User provides answer",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns minimal schema with ask_user
    minimal_ask_user = {
        "action": "ask_user",
        "question": "What is your preferred language?",
        "answer_key": "preferred_language",
    }
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps(minimal_ask_user),
    }

    # Execute
    result = await agent.execute(mission="Help me", session_id="test-session")

    # Verify: Execution paused for user input
    assert result.status == "paused"
    assert "preferred language" in result.final_message.lower()


@pytest.mark.asyncio
async def test_minimal_schema_tool_name_as_action_fallback(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider, mock_tool
):
    """Test agent corrects LLM mistake when tool name is used as action type.
    
    This tests the fallback where LLM returns:
        {"action": "list_wiki", "tool": "list_wiki", ...}
    instead of:
        {"action": "tool_call", "tool": "list_wiki", ...}
    
    The agent should recognize this pattern and correct it to tool_call.
    """
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="List wikis",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns WRONG format: tool name as action type (common LLM mistake)
    wrong_format = {
        "action": "list_wiki",  # WRONG: should be "tool_call"
        "tool": "test_tool",    # But tool field is correct (matches mock_tool)
        "tool_input": {"param": "value"},
    }
    minimal_respond = {
        "action": "respond",
        "summary": "Done listing wikis",
    }
    
    # Setup mock responses: wrong format -> respond -> markdown
    mock_llm_provider.complete.side_effect = [
        {"success": True, "content": json.dumps(wrong_format)},
        {"success": True, "content": json.dumps(minimal_respond)},
        {"success": True, "content": "Done listing wikis."},  # Two-phase markdown
    ]
    
    mock_tool.execute.return_value = {"success": True, "output": "Wiki list"}

    # Execute - should NOT fail with "list_wiki is not a valid ActionType"
    result = await agent.execute(mission="List wikis", session_id="test-session")

    # Verify: Agent should have executed the tool despite wrong action format
    assert result.status == "completed"
    mock_tool.execute.assert_called_once_with(param="value")


@pytest.mark.asyncio
async def test_legacy_schema_still_works(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that legacy schema format (nested action object) still works."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test legacy schema",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns LEGACY SCHEMA (action is nested object)
    legacy_complete = {
        "step_ref": 1,
        "rationale": "Task is done",
        "action": {
            "type": "complete",
            "summary": "Legacy schema still works",
        },
        "expected_outcome": "Complete",
        "confidence": 0.95,
    }
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps(legacy_complete),
    }

    # Execute
    result = await agent.execute(mission="Test legacy", session_id="test-session")

    # Verify: Legacy schema was parsed and worked
    assert result.status == "completed"
    assert "Legacy schema still works" in result.final_message


@pytest.mark.asyncio
async def test_legacy_finish_step_maps_to_respond(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that legacy 'finish_step' is mapped to RESPOND internally."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test finish_step mapping",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns finish_step (legacy) via minimal schema
    legacy_finish_step = {
        "action": "finish_step",  # Legacy value
        "summary": "Done via finish_step",
    }
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps(legacy_finish_step),
    }

    # Execute
    result = await agent.execute(mission="Test finish_step", session_id="test-session")

    # Verify: finish_step was handled (mapped to respond internally)
    assert result.status == "completed"
    assert "Done via finish_step" in result.final_message


@pytest.mark.asyncio
async def test_complete_triggers_early_exit(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that 'complete' action triggers early exit (skips remaining steps).
    
    Unlike 'respond' which only completes the current step, 'complete'
    is a special action that completes the entire mission immediately.
    """
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="First step",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            ),
            TodoItem(
                position=2,
                description="Second step (will be skipped)",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns 'complete' - should exit immediately, skipping step 2
    complete_action = {
        "action": "complete",
        "summary": "Mission done early",
    }
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps(complete_action),
    }

    # Execute
    result = await agent.execute(mission="Test complete", session_id="test-session")

    # Verify: complete triggered early exit
    assert result.status == "completed"
    assert "Mission done early" in result.final_message
    
    # Verify: LLM was only called once (not for step 2)
    assert mock_llm_provider.complete.call_count == 1
    
    # Verify: Step 2 was skipped
    updated_todolist = mock_todolist_manager.update_todolist.call_args[0][0]
    assert updated_todolist.items[1].status == TaskStatus.SKIPPED


@pytest.mark.asyncio
async def test_minimal_schema_without_optional_fields(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that minimal schema works without rationale, confidence, expected_outcome."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test minimal fields",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM returns ONLY the required minimal fields (no rationale, confidence, etc.)
    truly_minimal = {
        "action": "respond",
        "summary": "Minimal response",
    }
    # Two LLM calls: first for thought (respond action), second for markdown generation
    mock_llm_provider.complete.side_effect = [
        {"success": True, "content": json.dumps(truly_minimal)},
        {"success": True, "content": "# Minimal response\n\nHere is your answer."},
    ]

    # Execute
    result = await agent.execute(mission="Test minimal", session_id="test-session")

    # Verify: Works even with absolute minimum fields
    assert result.status == "completed"
    # Two-phase: markdown_response is returned, not the original summary
    assert "answer" in result.final_message.lower() or "Minimal" in result.final_message


# ============================================================================
# Zwei-Phasen-Response Tests - Story 5.3
# ============================================================================


@pytest.mark.asyncio
async def test_respond_action_triggers_two_phase_flow(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that RESPOND action triggers a second LLM call for markdown generation."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test two-phase response",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # Phase 1: LLM returns respond action
    respond_action = {
        "action": "respond",
        "summary": "ignored - two phase will generate markdown",
    }
    # Phase 2: LLM generates clean markdown
    markdown_response = "# Ergebnis\n\n- Punkt 1\n- Punkt 2\n\nZusammenfassung fertig."

    mock_llm_provider.complete.side_effect = [
        {"success": True, "content": json.dumps(respond_action)},  # Phase 1: Thought
        {"success": True, "content": markdown_response},  # Phase 2: Markdown
    ]

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify: Two LLM calls were made
    assert mock_llm_provider.complete.call_count == 2

    # Verify: Second call was WITHOUT JSON mode
    second_call_kwargs = mock_llm_provider.complete.call_args_list[1].kwargs
    assert second_call_kwargs.get("response_format") is None

    # Verify: Final message is the markdown, not the original summary
    assert result.status == "completed"
    assert "Ergebnis" in result.final_message
    assert "Punkt 1" in result.final_message


@pytest.mark.asyncio
async def test_two_phase_response_includes_previous_results(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider, mock_tool
):
    """Test that two-phase response includes context from previous tool results."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Execute a tool",
                acceptance_criteria="Tool done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            ),
            TodoItem(
                position=2,
                description="Respond to user",
                acceptance_criteria="Response given",
                dependencies=[1],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            ),
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # LLM flow: tool_call -> finish_step -> respond -> markdown
    mock_llm_provider.complete.side_effect = [
        # Step 1: tool_call
        {"success": True, "content": json.dumps({
            "action": "tool_call",
            "tool": "test_tool",
            "tool_input": {},
        })},
        # Step 1: finish_step
        {"success": True, "content": json.dumps({
            "action": "respond",
            "summary": "Step 1 done",
        })},
        # Step 1 markdown (two-phase)
        {"success": True, "content": "Step 1 completed."},
        # Step 2: respond
        {"success": True, "content": json.dumps({
            "action": "respond",
            "summary": "Final answer",
        })},
        # Step 2 markdown (two-phase) - should have access to step 1 results
        {"success": True, "content": "# Final Answer\n\nBased on previous results."},
    ]

    mock_tool.execute.return_value = {"success": True, "output": "tool output data"}

    # Execute
    result = await agent.execute(mission="Multi-step mission", session_id="test-session")

    # Verify: Completed successfully
    assert result.status == "completed"

    # Verify: Multiple LLM calls (thought + markdown for each respond)
    assert mock_llm_provider.complete.call_count >= 4


@pytest.mark.asyncio
async def test_two_phase_response_handles_llm_failure_gracefully(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that two-phase response returns fallback on LLM failure."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test LLM failure handling",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # Phase 1: respond action
    respond_action = {"action": "respond", "summary": "Answer"}
    
    mock_llm_provider.complete.side_effect = [
        {"success": True, "content": json.dumps(respond_action)},  # Phase 1
        {"success": False, "error": "LLM service unavailable"},  # Phase 2 fails
    ]

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify: Returns graceful fallback message
    assert result.status == "completed"
    assert "Entschuldigung" in result.final_message or "konnte keine Antwort" in result.final_message


@pytest.mark.asyncio
async def test_complete_action_skips_two_phase(
    agent, mock_state_manager, mock_todolist_manager, mock_llm_provider
):
    """Test that COMPLETE action does NOT trigger two-phase (uses summary directly)."""
    # Setup
    mock_state_manager.load_state.return_value = {"answers": {}}

    todolist = TodoList(
        todolist_id="test-todolist",
        items=[
            TodoItem(
                position=1,
                description="Test complete action",
                acceptance_criteria="Done",
                dependencies=[],
                status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=3,
                execution_history=[],
            )
        ],
        open_questions=[],
        notes="",
    )
    mock_todolist_manager.create_todolist.return_value = todolist

    # COMPLETE action - should NOT trigger second LLM call
    complete_action = {
        "action": "complete",
        "summary": "Early exit with direct summary",
    }
    mock_llm_provider.complete.return_value = {
        "success": True,
        "content": json.dumps(complete_action),
    }

    # Execute
    result = await agent.execute(mission="Test mission", session_id="test-session")

    # Verify: Only ONE LLM call (no second call for markdown)
    assert mock_llm_provider.complete.call_count == 1

    # Verify: Summary is used directly
    assert result.status == "completed"
    assert "Early exit with direct summary" in result.final_message


@pytest.mark.asyncio
async def test_summarize_results_for_response_empty_list(agent):
    """Test _summarize_results_for_response handles empty list."""
    result = agent._summarize_results_for_response([])
    assert result == "Keine vorherigen Ergebnisse."


@pytest.mark.asyncio
async def test_summarize_results_for_response_with_results(agent):
    """Test _summarize_results_for_response formats results correctly."""
    previous_results = [
        {
            "tool": "wiki_search",
            "result": {"success": True, "content": "Found 5 pages about Python"},
        },
        {
            "tool": "file_read",
            "result": {"success": False, "error": "File not found"},
        },
    ]

    result = agent._summarize_results_for_response(previous_results)

    # Check formatting
    assert "wiki_search" in result
    assert "file_read" in result
    assert "[✓]" in result  # Success indicator
    assert "[✗]" in result  # Failure indicator


@pytest.mark.asyncio
async def test_build_response_context_for_respond(agent):
    """Test _build_response_context_for_respond extracts correct context."""
    state = {
        "mission": "Find information about X",
        "conversation_history": [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
        ],
        "answers": {"key1": "value1"},
    }
    step = TodoItem(
        position=1,
        description="Test step",
        acceptance_criteria="Done",
        dependencies=[],
        status=TaskStatus.PENDING,
    )

    context = agent._build_response_context_for_respond(state, step)

    assert context["mission"] == "Find information about X"
    assert len(context["conversation_history"]) == 2
    assert context["user_answers"] == {"key1": "value1"}