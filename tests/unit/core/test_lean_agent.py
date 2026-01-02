"""
Unit Tests for LeanAgent with Native Tool Calling

Tests the LeanAgent class using protocol mocks to verify the simplified
ReAct loop with native LLM tool calling (no JSON parsing).
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.core.domain.models import ExecutionResult
from taskforce.core.tools.planner_tool import PlannerTool


@pytest.fixture
def mock_state_manager():
    """Mock StateManagerProtocol."""
    mock = AsyncMock()
    mock.load_state.return_value = {"answers": {}}
    mock.save_state.return_value = True
    return mock


@pytest.fixture
def mock_llm_provider():
    """Mock LLMProviderProtocol with native tool calling support."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def mock_tool():
    """Mock ToolProtocol for a generic tool."""
    tool = MagicMock()
    tool.name = "test_tool"
    tool.description = "A test tool for unit tests"
    tool.parameters_schema = {
        "type": "object",
        "properties": {"param": {"type": "string"}},
    }
    tool.execute = AsyncMock(
        return_value={"success": True, "output": "test result"}
    )
    return tool


@pytest.fixture
def calculator_tool():
    """Mock Calculator tool for integration testing."""
    tool = MagicMock()
    tool.name = "calculator"
    tool.description = "Perform mathematical calculations"
    tool.parameters_schema = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate",
            },
        },
        "required": ["expression"],
    }

    async def mock_execute(expression: str):
        try:
            result = eval(expression)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    tool.execute = mock_execute
    return tool


@pytest.fixture
def planner_tool():
    """Real PlannerTool for testing plan management."""
    return PlannerTool()


@pytest.fixture
def lean_agent(mock_state_manager, mock_llm_provider, mock_tool, planner_tool):
    """Create LeanAgent with mocked dependencies."""
    return LeanAgent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools=[mock_tool, planner_tool],
        system_prompt="You are a helpful assistant.",
    )


def make_tool_call(tool_name: str, args: dict, call_id: str = "call_1"):
    """Helper to create a tool call response structure."""
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(args),
        },
    }


class TestLeanAgentInitialization:
    """Tests for LeanAgent initialization."""

    def test_initializes_with_dependencies(self, lean_agent, mock_tool):
        """Test agent initializes with correct dependencies."""
        assert lean_agent.state_manager is not None
        assert lean_agent.llm_provider is not None
        assert "test_tool" in lean_agent.tools
        assert "planner" in lean_agent.tools
        assert lean_agent.system_prompt == "You are a helpful assistant."

    def test_creates_planner_if_not_provided(
        self, mock_state_manager, mock_llm_provider
    ):
        """Test that PlannerTool is created if not provided."""
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[],  # No tools provided
            system_prompt="Test prompt",
        )
        assert "planner" in agent.tools
        assert isinstance(agent._planner, PlannerTool)

    def test_creates_openai_tools_format(self, lean_agent):
        """Test that tools are converted to OpenAI format."""
        assert lean_agent._openai_tools is not None
        assert len(lean_agent._openai_tools) >= 2  # test_tool + planner

        # Verify format
        for tool in lean_agent._openai_tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]


class TestLeanAgentNativeToolCalling:
    """Tests for native tool calling (no JSON parsing)."""

    @pytest.mark.asyncio
    async def test_execute_with_content_response(
        self, lean_agent, mock_llm_provider, mock_state_manager
    ):
        """Test that execute completes when LLM returns content (no tool calls)."""
        # Setup: LLM returns content immediately (final answer)
        mock_llm_provider.complete.return_value = {
            "success": True,
            "content": "Hello! How can I help you today?",
            "tool_calls": None,
        }

        # Execute
        result = await lean_agent.execute(
            mission="Say hello",
            session_id="test-session",
        )

        # Verify
        assert isinstance(result, ExecutionResult)
        assert result.status == "completed"
        assert result.final_message == "Hello! How can I help you today?"
        assert result.session_id == "test-session"
        mock_state_manager.save_state.assert_called()

    @pytest.mark.asyncio
    async def test_execute_tool_call_then_respond(
        self, lean_agent, mock_llm_provider, mock_tool
    ):
        """Test tool execution via native tool calling followed by response."""
        # Setup: First call returns tool_call, second returns content
        mock_llm_provider.complete.side_effect = [
            {
                "success": True,
                "content": None,
                "tool_calls": [make_tool_call("test_tool", {"param": "value"})],
            },
            {
                "success": True,
                "content": "Task completed successfully.",
                "tool_calls": None,
            },
        ]

        # Execute
        result = await lean_agent.execute(
            mission="Do something with test_tool",
            session_id="test-session",
        )

        # Verify
        assert result.status == "completed"
        assert result.final_message == "Task completed successfully."
        mock_tool.execute.assert_called_once_with(param="value")

    @pytest.mark.asyncio
    async def test_execute_multiple_tool_calls_in_one_response(
        self, mock_state_manager, mock_llm_provider, calculator_tool, planner_tool
    ):
        """Test handling multiple tool calls in a single LLM response."""
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[calculator_tool, planner_tool],
            system_prompt="Test",
        )

        # Setup: LLM calls two tools at once, then responds
        mock_llm_provider.complete.side_effect = [
            {
                "success": True,
                "content": None,
                "tool_calls": [
                    make_tool_call("calculator", {"expression": "2+2"}, "call_1"),
                    make_tool_call("calculator", {"expression": "3*3"}, "call_2"),
                ],
            },
            {
                "success": True,
                "content": "Calculations complete: 2+2=4, 3*3=9",
                "tool_calls": None,
            },
        ]

        result = await agent.execute(mission="Calculate", session_id="test")

        assert result.status == "completed"
        # Verify execution history contains both tool calls
        tool_calls = [
            h for h in result.execution_history if h["type"] == "tool_call"
        ]
        assert len(tool_calls) == 2

    @pytest.mark.asyncio
    async def test_execute_with_planner_tool(
        self, lean_agent, mock_llm_provider, planner_tool
    ):
        """Test execution with PlannerTool via native tool calling."""
        # Setup: LLM creates plan, marks done, then responds
        mock_llm_provider.complete.side_effect = [
            # Step 1: Create plan
            {
                "success": True,
                "content": None,
                "tool_calls": [
                    make_tool_call(
                        "planner",
                        {
                            "action": "create_plan",
                            "tasks": ["Step 1: Do X", "Step 2: Do Y"],
                        },
                    )
                ],
            },
            # Step 2: Mark first step done
            {
                "success": True,
                "content": None,
                "tool_calls": [
                    make_tool_call("planner", {"action": "mark_done", "step_index": 1})
                ],
            },
            # Step 3: Mark second step done
            {
                "success": True,
                "content": None,
                "tool_calls": [
                    make_tool_call("planner", {"action": "mark_done", "step_index": 2})
                ],
            },
            # Step 4: Respond with summary
            {
                "success": True,
                "content": "All steps completed!",
                "tool_calls": None,
            },
        ]

        # Execute
        result = await lean_agent.execute(
            mission="Complete the two-step process",
            session_id="test-session",
        )

        # Verify
        assert result.status == "completed"
        assert result.final_message == "All steps completed!"

        # Verify plan state after execution
        plan_result = planner_tool._read_plan()
        assert "[x] 1." in plan_result["output"]
        assert "[x] 2." in plan_result["output"]


class TestLeanAgentErrorHandling:
    """Tests for error handling in native tool calling."""

    @pytest.mark.asyncio
    async def test_handles_tool_not_found(self, lean_agent, mock_llm_provider):
        """Test graceful handling when tool is not found."""
        # Setup: LLM calls non-existent tool, then responds
        mock_llm_provider.complete.side_effect = [
            {
                "success": True,
                "content": None,
                "tool_calls": [
                    make_tool_call("nonexistent_tool", {})
                ],
            },
            {
                "success": True,
                "content": "Recovered from error.",
                "tool_calls": None,
            },
        ]

        result = await lean_agent.execute(
            mission="Use nonexistent tool",
            session_id="test-session",
        )

        # Verify: Agent should continue and eventually respond
        assert result.status == "completed"
        # Check execution history for error
        error_calls = [
            h for h in result.execution_history
            if h["type"] == "tool_call" and not h["result"].get("success")
        ]
        assert len(error_calls) == 1
        assert "Tool not found" in error_calls[0]["result"]["error"]

    @pytest.mark.asyncio
    async def test_handles_tool_exception(self, lean_agent, mock_llm_provider, mock_tool):
        """Test handling of tool execution exception."""
        # Setup: Tool raises exception
        mock_tool.execute = AsyncMock(side_effect=RuntimeError("Tool crashed"))

        mock_llm_provider.complete.side_effect = [
            {
                "success": True,
                "content": None,
                "tool_calls": [make_tool_call("test_tool", {})],
            },
            {
                "success": True,
                "content": "Handled the error.",
                "tool_calls": None,
            },
        ]

        result = await lean_agent.execute(mission="Test", session_id="test")

        assert result.status == "completed"
        # Error should be captured in history
        error_calls = [
            h for h in result.execution_history
            if h["type"] == "tool_call" and not h["result"].get("success")
        ]
        assert len(error_calls) == 1
        assert "Tool crashed" in error_calls[0]["result"]["error"]

    @pytest.mark.asyncio
    async def test_handles_llm_failure(self, lean_agent, mock_llm_provider):
        """Test handling of LLM API failure."""
        # Setup: First call fails, second succeeds
        mock_llm_provider.complete.side_effect = [
            {"success": False, "error": "API rate limit"},
            {
                "success": True,
                "content": "Recovered from API error.",
                "tool_calls": None,
            },
        ]

        result = await lean_agent.execute(mission="Test", session_id="test")

        assert result.status == "completed"
        assert result.final_message == "Recovered from API error."

    @pytest.mark.asyncio
    async def test_handles_invalid_tool_arguments(
        self, lean_agent, mock_llm_provider
    ):
        """Test handling of malformed tool arguments JSON."""
        # Setup: LLM returns invalid JSON in arguments
        mock_llm_provider.complete.side_effect = [
            {
                "success": True,
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "test_tool",
                            "arguments": "not valid json {{{",
                        },
                    }
                ],
            },
            {
                "success": True,
                "content": "Done.",
                "tool_calls": None,
            },
        ]

        result = await lean_agent.execute(mission="Test", session_id="test")

        # Should still complete (tool called with empty args)
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_respects_max_steps(self, lean_agent, mock_llm_provider, mock_tool):
        """Test that execution stops at MAX_STEPS."""
        lean_agent.MAX_STEPS = 3  # Set low for test

        # Setup: LLM always returns tool_call (never responds)
        mock_llm_provider.complete.return_value = {
            "success": True,
            "content": None,
            "tool_calls": [make_tool_call("test_tool", {})],
        }

        result = await lean_agent.execute(
            mission="Infinite loop test",
            session_id="test-session",
        )

        # Verify: Should fail due to max steps
        assert result.status == "failed"
        assert "Exceeded maximum steps" in result.final_message

    @pytest.mark.asyncio
    async def test_handles_empty_response(self, lean_agent, mock_llm_provider):
        """Test handling of empty LLM response (no content, no tool_calls)."""
        mock_llm_provider.complete.side_effect = [
            {
                "success": True,
                "content": None,  # Empty content
                "tool_calls": None,  # No tool calls
            },
            {
                "success": True,
                "content": "Now I have a response.",
                "tool_calls": None,
            },
        ]

        result = await lean_agent.execute(mission="Test", session_id="test")

        # Should recover and complete
        assert result.status == "completed"
        assert result.final_message == "Now I have a response."


class TestLeanAgentStatePersistence:
    """Tests for state persistence including PlannerTool state."""

    @pytest.mark.asyncio
    async def test_planner_state_persisted(
        self, lean_agent, mock_llm_provider, mock_state_manager, planner_tool
    ):
        """Test that PlannerTool state is saved with session state."""
        # Setup: Create plan and respond
        mock_llm_provider.complete.side_effect = [
            {
                "success": True,
                "content": None,
                "tool_calls": [
                    make_tool_call(
                        "planner",
                        {"action": "create_plan", "tasks": ["Task A", "Task B"]},
                    )
                ],
            },
            {
                "success": True,
                "content": "Plan created.",
                "tool_calls": None,
            },
        ]

        await lean_agent.execute(mission="Create plan", session_id="test-session")

        # Verify: State should include planner_state
        saved_state = mock_state_manager.save_state.call_args[0][1]
        assert "planner_state" in saved_state
        assert "tasks" in saved_state["planner_state"]
        assert len(saved_state["planner_state"]["tasks"]) == 2

    @pytest.mark.asyncio
    async def test_planner_state_restored(
        self, mock_state_manager, mock_llm_provider, mock_tool
    ):
        """Test that PlannerTool state is restored from session state."""
        # Setup: State with existing planner state
        mock_state_manager.load_state.return_value = {
            "answers": {},
            "planner_state": {
                "tasks": [
                    {"description": "Existing task", "status": "PENDING"},
                ],
            },
        }

        # Setup: LLM reads plan then responds
        mock_llm_provider.complete.side_effect = [
            {
                "success": True,
                "content": None,
                "tool_calls": [
                    make_tool_call("planner", {"action": "read_plan"})
                ],
            },
            {
                "success": True,
                "content": "Found existing plan.",
                "tool_calls": None,
            },
        ]

        planner = PlannerTool()
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool, planner],
            system_prompt="Test",
        )

        await agent.execute(mission="Check plan", session_id="test-session")

        # Verify: Planner should have restored state
        result = planner._read_plan()
        assert "Existing task" in result["output"]


class TestLeanAgentNoLegacyDependencies:
    """Tests verifying LeanAgent has no legacy dependencies."""

    def test_no_todolist_manager_attribute(self, lean_agent):
        """Verify LeanAgent has no todolist_manager attribute."""
        assert not hasattr(lean_agent, "todolist_manager")

    def test_no_router_attribute(self, lean_agent):
        """Verify LeanAgent has no router attribute."""
        assert not hasattr(lean_agent, "_router")
        assert not hasattr(lean_agent, "router")

    def test_no_fast_path_methods(self, lean_agent):
        """Verify LeanAgent has no fast-path methods."""
        assert not hasattr(lean_agent, "_execute_fast_path")
        assert not hasattr(lean_agent, "_execute_full_path")
        assert not hasattr(lean_agent, "_generate_fast_path_thought")

    def test_no_replan_method(self, lean_agent):
        """Verify LeanAgent has no _replan method."""
        assert not hasattr(lean_agent, "_replan")

    def test_no_json_parsing_methods(self, lean_agent):
        """Verify LeanAgent has no JSON parsing methods (native tool calling)."""
        assert not hasattr(lean_agent, "_parse_thought")
        assert not hasattr(lean_agent, "_generate_thought")


class TestToolConverterIntegration:
    """Tests for tool converter integration."""

    def test_tools_converted_to_openai_format(self, lean_agent):
        """Test that tools are properly converted to OpenAI format."""
        openai_tools = lean_agent._openai_tools

        # Find planner tool in the list
        planner_tool_def = next(
            (t for t in openai_tools if t["function"]["name"] == "planner"), None
        )
        assert planner_tool_def is not None
        assert planner_tool_def["type"] == "function"
        assert "description" in planner_tool_def["function"]
        assert "parameters" in planner_tool_def["function"]


class TestDynamicContextInjection:
    """Tests for Story 4: Dynamic Context Injection."""

    def test_build_system_prompt_without_plan(
        self, mock_state_manager, mock_llm_provider, mock_tool
    ):
        """Test that _build_system_prompt returns base prompt when no plan exists."""
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            system_prompt="Base prompt here.",
        )

        prompt = agent._build_system_prompt()

        assert "Base prompt here." in prompt
        assert "CURRENT PLAN STATUS" not in prompt

    def test_build_system_prompt_with_active_plan(
        self, mock_state_manager, mock_llm_provider, mock_tool
    ):
        """Test that _build_system_prompt injects plan when one exists."""
        planner = PlannerTool()
        planner._create_plan(tasks=["Step 1: Do A", "Step 2: Do B"])

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool, planner],
            system_prompt="Base prompt.",
        )

        prompt = agent._build_system_prompt()

        assert "Base prompt." in prompt
        assert "## CURRENT PLAN STATUS" in prompt
        assert "[ ] 1. Step 1: Do A" in prompt
        assert "[ ] 2. Step 2: Do B" in prompt

    def test_build_system_prompt_reflects_completed_steps(
        self, mock_state_manager, mock_llm_provider, mock_tool
    ):
        """Test that plan injection shows completed steps with [x]."""
        planner = PlannerTool()
        planner._create_plan(tasks=["Step 1", "Step 2"])
        planner._mark_done(step_index=1)

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool, planner],
            system_prompt="Test",
        )

        prompt = agent._build_system_prompt()

        assert "[x] 1. Step 1" in prompt
        assert "[ ] 2. Step 2" in prompt

    @pytest.mark.asyncio
    async def test_plan_updates_in_system_prompt_during_loop(
        self, mock_state_manager, mock_llm_provider
    ):
        """Test that system prompt is updated each loop with latest plan state."""
        planner = PlannerTool()
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[planner],
            system_prompt="Base",
        )

        captured_prompts = []

        # Mock complete to capture system prompt on each call
        async def capture_complete(messages, **kwargs):
            # Capture the system prompt from messages
            system_msg = next(
                (m for m in messages if m["role"] == "system"), None
            )
            if system_msg:
                captured_prompts.append(system_msg["content"])

            # Simulate: 1st call creates plan, 2nd marks done, 3rd responds
            call_count = len(captured_prompts)
            if call_count == 1:
                return {
                    "success": True,
                    "content": None,
                    "tool_calls": [
                        make_tool_call(
                            "planner",
                            {"action": "create_plan", "tasks": ["Task A"]},
                        )
                    ],
                }
            elif call_count == 2:
                return {
                    "success": True,
                    "content": None,
                    "tool_calls": [
                        make_tool_call(
                            "planner", {"action": "mark_done", "step_index": 1}
                        )
                    ],
                }
            else:
                return {
                    "success": True,
                    "content": "All done!",
                    "tool_calls": None,
                }

        mock_llm_provider.complete = capture_complete

        await agent.execute(mission="Do task", session_id="test")

        # Verify prompts evolved
        assert len(captured_prompts) == 3

        # 1st call: No plan yet
        assert "CURRENT PLAN STATUS" not in captured_prompts[0]

        # 2nd call: Plan exists with pending task
        assert "CURRENT PLAN STATUS" in captured_prompts[1]
        assert "[ ] 1. Task A" in captured_prompts[1]

        # 3rd call: Plan exists with completed task
        assert "CURRENT PLAN STATUS" in captured_prompts[2]
        assert "[x] 1. Task A" in captured_prompts[2]

    def test_system_prompt_property_returns_base_prompt(
        self, mock_state_manager, mock_llm_provider, mock_tool
    ):
        """Test backward compatibility: system_prompt property returns base."""
        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            system_prompt="My custom prompt",
        )

        assert agent.system_prompt == "My custom prompt"

    def test_uses_lean_kernel_prompt_by_default(
        self, mock_state_manager, mock_llm_provider, mock_tool
    ):
        """Test that LEAN_KERNEL_PROMPT is used when no prompt is provided."""
        from taskforce.core.prompts.autonomous_prompts import LEAN_KERNEL_PROMPT

        agent = LeanAgent(
            state_manager=mock_state_manager,
            llm_provider=mock_llm_provider,
            tools=[mock_tool],
            # No system_prompt provided
        )

        assert agent.system_prompt == LEAN_KERNEL_PROMPT
        assert "Lean ReAct Agent" in agent.system_prompt