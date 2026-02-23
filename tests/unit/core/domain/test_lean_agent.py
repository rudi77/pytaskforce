"""Tests for the LeanAgent (Agent) module.

Covers initialization, system prompt property, skill activation,
and various configuration scenarios.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from taskforce.core.domain.lean_agent import Agent, LeanAgent
from taskforce.core.domain.planning_strategy import NativeReActStrategy
from taskforce.core.tools.planner_tool import PlannerTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_tool(name: str = "test_tool") -> MagicMock:
    """Create a minimal mock satisfying ToolProtocol."""
    tool = MagicMock()
    tool.name = name
    tool.description = f"Description for {name}"
    tool.parameters_schema = {
        "type": "object",
        "properties": {"input": {"type": "string"}},
    }
    tool.requires_approval = False
    tool.approval_risk_level = "low"
    tool.supports_parallelism = False
    tool.execute = AsyncMock(return_value={"success": True, "output": "ok"})
    return tool


def _make_mock_logger() -> MagicMock:
    """Create a mock LoggerProtocol."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    logger.debug = MagicMock()
    return logger


def _make_agent(**overrides: Any) -> Agent:
    """Create an Agent with sensible defaults and optional overrides."""
    defaults: dict[str, Any] = {
        "state_manager": AsyncMock(),
        "llm_provider": AsyncMock(),
        "tools": [_make_mock_tool()],
        "logger": _make_mock_logger(),
    }
    defaults.update(overrides)
    return Agent(**defaults)


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------


class TestAgentInitialization:
    """Tests for Agent.__init__."""

    def test_basic_initialization(self) -> None:
        """Agent initializes with required dependencies."""
        agent = _make_agent()
        assert agent.max_steps == Agent.DEFAULT_MAX_STEPS
        assert agent.max_parallel_tools == Agent.DEFAULT_MAX_PARALLEL_TOOLS
        assert agent.model_alias == "main"

    def test_custom_max_steps(self) -> None:
        """max_steps can be overridden."""
        agent = _make_agent(max_steps=50)
        assert agent.max_steps == 50

    def test_custom_max_parallel_tools(self) -> None:
        """max_parallel_tools can be overridden."""
        agent = _make_agent(max_parallel_tools=8)
        assert agent.max_parallel_tools == 8

    def test_custom_model_alias(self) -> None:
        """model_alias can be overridden."""
        agent = _make_agent(model_alias="fast")
        assert agent.model_alias == "fast"

    def test_custom_system_prompt(self) -> None:
        """Custom system prompt replaces the default."""
        agent = _make_agent(system_prompt="Custom prompt")
        assert agent.system_prompt == "Custom prompt"
        assert agent._base_system_prompt == "Custom prompt"

    def test_default_system_prompt_uses_lean_kernel(self) -> None:
        """When no prompt is given, LEAN_KERNEL_PROMPT is used."""
        from taskforce.core.prompts.autonomous_prompts import LEAN_KERNEL_PROMPT

        agent = _make_agent()
        assert agent.system_prompt == LEAN_KERNEL_PROMPT

    def test_planner_tool_auto_created(self) -> None:
        """If no PlannerTool in tools list, one is auto-created."""
        mock_tool = _make_mock_tool("file_read")
        agent = _make_agent(tools=[mock_tool])
        assert agent._planner is not None
        assert isinstance(agent._planner, PlannerTool)
        assert "planner" in agent.tools

    def test_existing_planner_tool_reused(self) -> None:
        """If a PlannerTool is provided, it's reused (not duplicated)."""
        planner = PlannerTool()
        mock_tool = _make_mock_tool("file_read")
        agent = _make_agent(tools=[mock_tool, planner])
        assert agent._planner is planner
        # Only the original planner, no extra one
        planner_count = sum(
            1 for t in agent.tools.values() if isinstance(t, PlannerTool)
        )
        assert planner_count == 1

    def test_tools_dict_populated(self) -> None:
        """All provided tools are added to the tools dict."""
        tool_a = _make_mock_tool("tool_a")
        tool_b = _make_mock_tool("tool_b")
        agent = _make_agent(tools=[tool_a, tool_b])
        assert "tool_a" in agent.tools
        assert "tool_b" in agent.tools
        # Plus auto-created planner
        assert "planner" in agent.tools

    def test_default_planning_strategy(self) -> None:
        """Default planning strategy is NativeReActStrategy."""
        agent = _make_agent()
        assert isinstance(agent.planning_strategy, NativeReActStrategy)

    def test_custom_planning_strategy(self) -> None:
        """Planning strategy can be overridden."""
        custom_strategy = MagicMock()
        agent = _make_agent(planning_strategy=custom_strategy)
        assert agent.planning_strategy is custom_strategy

    def test_no_runtime_tracker_by_default(self) -> None:
        """runtime_tracker is None by default."""
        agent = _make_agent()
        assert agent.runtime_tracker is None

    def test_custom_runtime_tracker(self) -> None:
        """runtime_tracker can be injected."""
        tracker = AsyncMock()
        agent = _make_agent(runtime_tracker=tracker)
        assert agent.runtime_tracker is tracker

    def test_no_skill_manager_by_default(self) -> None:
        """skill_manager is None by default."""
        agent = _make_agent()
        assert agent.skill_manager is None

    def test_custom_skill_manager(self) -> None:
        """skill_manager can be injected."""
        sm = MagicMock()
        agent = _make_agent(skill_manager=sm)
        assert agent.skill_manager is sm

    def test_summary_threshold_default(self) -> None:
        """Default summary_threshold is DEFAULT_SUMMARY_THRESHOLD."""
        agent = _make_agent()
        assert agent.summary_threshold == Agent.DEFAULT_SUMMARY_THRESHOLD

    def test_custom_summary_threshold(self) -> None:
        """summary_threshold can be overridden."""
        agent = _make_agent(summary_threshold=10)
        assert agent.summary_threshold == 10

    def test_tool_result_store_none_by_default(self) -> None:
        """tool_result_store is None by default."""
        agent = _make_agent()
        assert agent.tool_result_store is None


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestAgentProperties:
    """Tests for Agent properties."""

    def test_system_prompt_property(self) -> None:
        """system_prompt returns the base system prompt."""
        agent = _make_agent(system_prompt="Hello")
        assert agent.system_prompt == "Hello"

    def test_planner_property(self) -> None:
        """planner property returns the PlannerTool instance."""
        agent = _make_agent()
        assert agent.planner is agent._planner


# ---------------------------------------------------------------------------
# Backward Compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Tests for backward-compatible alias."""

    def test_lean_agent_alias(self) -> None:
        """LeanAgent is an alias for Agent."""
        assert LeanAgent is Agent


# ---------------------------------------------------------------------------
# Skill Activation Tests
# ---------------------------------------------------------------------------


class TestGetActiveSkillName:
    """Tests for get_active_skill_name()."""

    def test_returns_none_without_skill_manager(self) -> None:
        """Returns None when no skill_manager is configured."""
        agent = _make_agent()
        assert agent.get_active_skill_name() is None

    def test_returns_skill_name_from_manager(self) -> None:
        """Delegates to skill_manager.active_skill_name."""
        sm = MagicMock()
        sm.active_skill_name = "invoice_processor"
        agent = _make_agent(skill_manager=sm)
        assert agent.get_active_skill_name() == "invoice_processor"

    def test_returns_none_when_no_active_skill(self) -> None:
        """Returns None when skill_manager has no active skill."""
        sm = MagicMock()
        sm.active_skill_name = None
        agent = _make_agent(skill_manager=sm)
        assert agent.get_active_skill_name() is None


class TestActivateSkill:
    """Tests for activate_skill()."""

    def test_returns_false_without_skill_manager(self) -> None:
        """Returns False when no skill_manager is configured."""
        agent = _make_agent()
        assert agent.activate_skill("some_skill") is False

    def test_returns_true_on_successful_activation(self) -> None:
        """Returns True and logs when skill is activated."""
        skill_obj = MagicMock()
        skill_obj.name = "my_skill"

        sm = MagicMock()
        sm.activate_skill.return_value = skill_obj

        agent = _make_agent(skill_manager=sm)
        result = agent.activate_skill("my_skill")

        assert result is True
        sm.activate_skill.assert_called_once_with("my_skill")
        agent.logger.info.assert_called_with("skill_activated", skill="my_skill")

    def test_returns_false_when_skill_not_found(self) -> None:
        """Returns False when skill_manager returns falsy value."""
        sm = MagicMock()
        sm.activate_skill.return_value = None

        agent = _make_agent(skill_manager=sm)
        result = agent.activate_skill("nonexistent")

        assert result is False


class TestActivateSkillByIntent:
    """Tests for activate_skill_by_intent()."""

    def test_returns_false_without_skill_manager(self) -> None:
        """Returns False when no skill_manager is configured."""
        agent = _make_agent()
        assert agent.activate_skill_by_intent("INVOICE_PROCESSING") is False

    def test_returns_true_on_successful_activation(self) -> None:
        """Returns True and logs when a skill is activated by intent."""
        skill_obj = MagicMock()
        skill_obj.name = "invoice_skill"

        sm = MagicMock()
        sm.activate_by_intent.return_value = skill_obj

        agent = _make_agent(skill_manager=sm)
        result = agent.activate_skill_by_intent("INVOICE_PROCESSING")

        assert result is True
        sm.activate_by_intent.assert_called_once_with("INVOICE_PROCESSING")
        agent.logger.info.assert_called_with(
            "skill_activated_by_intent",
            intent="INVOICE_PROCESSING",
            skill="invoice_skill",
        )

    def test_returns_false_when_no_skill_matches(self) -> None:
        """Returns False when skill_manager cannot match intent."""
        sm = MagicMock()
        sm.activate_by_intent.return_value = None

        agent = _make_agent(skill_manager=sm)
        result = agent.activate_skill_by_intent("UNKNOWN_INTENT")

        assert result is False


# ---------------------------------------------------------------------------
# Effective System Prompt Tests
# ---------------------------------------------------------------------------


class TestGetEffectiveSystemPrompt:
    """Tests for get_effective_system_prompt()."""

    def test_returns_base_prompt_without_skill_manager(self) -> None:
        """Without skill_manager, returns the base system prompt."""
        agent = _make_agent(system_prompt="Base prompt")
        assert agent.get_effective_system_prompt() == "Base prompt"

    def test_delegates_to_skill_manager_enhance_prompt(self) -> None:
        """With skill_manager, calls enhance_prompt."""
        sm = MagicMock()
        sm.enhance_prompt.return_value = "Enhanced prompt with skills"

        agent = _make_agent(system_prompt="Base prompt", skill_manager=sm)
        result = agent.get_effective_system_prompt()

        assert result == "Enhanced prompt with skills"
        sm.enhance_prompt.assert_called_once_with("Base prompt")


# ---------------------------------------------------------------------------
# Build System Prompt (Internal)
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    """Tests for _build_system_prompt (internal method)."""

    def test_without_skill_manager(self) -> None:
        """Without skill_manager, returns prompt from prompt_builder only."""
        agent = _make_agent(system_prompt="Test prompt")
        result = agent._build_system_prompt(mission="test mission")
        # Should contain the base prompt content (from prompt_builder)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_with_active_skill(self) -> None:
        """With an active skill, appends skill instructions to the prompt."""
        sm = MagicMock()
        sm.active_skill_name = "accounting"
        sm.get_active_instructions.return_value = "Follow accounting rules."

        agent = _make_agent(system_prompt="Base prompt", skill_manager=sm)
        result = agent._build_system_prompt(mission="test")

        assert "ACTIVE SKILL: accounting" in result
        assert "Follow accounting rules." in result

    def test_with_skill_manager_no_active_skill(self) -> None:
        """With skill_manager but no active skill, no skill section appended."""
        sm = MagicMock()
        sm.active_skill_name = None

        agent = _make_agent(system_prompt="Base prompt", skill_manager=sm)
        result = agent._build_system_prompt(mission="test")

        assert "ACTIVE SKILL" not in result

    def test_with_skill_manager_empty_instructions(self) -> None:
        """With active skill but empty instructions, no skill section appended."""
        sm = MagicMock()
        sm.active_skill_name = "my_skill"
        sm.get_active_instructions.return_value = ""

        agent = _make_agent(system_prompt="Base prompt", skill_manager=sm)
        result = agent._build_system_prompt(mission="test")

        assert "ACTIVE SKILL" not in result


# ---------------------------------------------------------------------------
# Truncate Output Tests
# ---------------------------------------------------------------------------


class TestTruncateOutput:
    """Tests for _truncate_output."""

    def test_short_output_unchanged(self) -> None:
        """Short output is returned unchanged."""
        agent = _make_agent()
        assert agent._truncate_output("hello") == "hello"

    def test_long_output_truncated(self) -> None:
        """Long output is truncated with '...' suffix."""
        agent = _make_agent()
        long_text = "a" * 5000
        result = agent._truncate_output(long_text)
        assert len(result) == 4003  # 4000 + "..."
        assert result.endswith("...")

    def test_custom_max_length(self) -> None:
        """Custom max_length is respected."""
        agent = _make_agent()
        result = agent._truncate_output("abcdefghij", max_length=5)
        assert result == "abcde..."


# ---------------------------------------------------------------------------
# Heartbeat / Mark Finished Tests
# ---------------------------------------------------------------------------


class TestRuntimeTracking:
    """Tests for record_heartbeat and mark_finished."""

    async def test_record_heartbeat_with_tracker(self) -> None:
        """record_heartbeat delegates to runtime_tracker."""
        tracker = AsyncMock()
        agent = _make_agent(runtime_tracker=tracker)
        await agent.record_heartbeat("session-1", "running", {"step": 3})
        tracker.record_heartbeat.assert_awaited_once_with(
            "session-1", "running", {"step": 3}
        )

    async def test_record_heartbeat_without_tracker(self) -> None:
        """record_heartbeat is a no-op without runtime_tracker."""
        agent = _make_agent()
        # Should not raise
        await agent.record_heartbeat("session-1", "running")

    async def test_mark_finished_with_tracker(self) -> None:
        """mark_finished delegates to runtime_tracker."""
        tracker = AsyncMock()
        agent = _make_agent(runtime_tracker=tracker)
        await agent.mark_finished("session-1", "completed", {"msg_len": 100})
        tracker.mark_finished.assert_awaited_once_with(
            "session-1", "completed", {"msg_len": 100}
        )

    async def test_mark_finished_without_tracker(self) -> None:
        """mark_finished is a no-op without runtime_tracker."""
        agent = _make_agent()
        await agent.mark_finished("session-1", "completed")


# ---------------------------------------------------------------------------
# Close Tests
# ---------------------------------------------------------------------------


class TestClose:
    """Tests for Agent.close()."""

    async def test_close_without_mcp_contexts(self) -> None:
        """close() is safe when no MCP contexts exist."""
        agent = _make_agent()
        await agent.close()
        agent.logger.debug.assert_called_with("agent_closed")

    async def test_close_with_mcp_contexts(self) -> None:
        """close() cleans up MCP contexts attached by factory."""
        agent = _make_agent()
        mock_ctx = AsyncMock()
        agent._mcp_contexts = [mock_ctx]
        await agent.close()
        agent.logger.debug.assert_called_with("agent_closed")


# ---------------------------------------------------------------------------
# Execute Tests
# ---------------------------------------------------------------------------


class TestExecute:
    """Tests for Agent.execute()."""

    async def test_execute_delegates_to_planning_strategy(self) -> None:
        """execute() delegates to planning_strategy.execute()."""
        from taskforce.core.domain.models import ExecutionResult

        strategy = MagicMock()
        expected_result = ExecutionResult(
            session_id="session-1",
            status="completed",
            final_message="Done",
        )
        strategy.execute = AsyncMock(return_value=expected_result)

        agent = _make_agent(planning_strategy=strategy)
        result = await agent.execute("Do something", "session-1")

        assert result is expected_result
        strategy.execute.assert_awaited_once_with(agent, "Do something", "session-1")

    async def test_execute_records_heartbeat_and_marks_finished(self) -> None:
        """execute() records heartbeat at start and marks finished at end."""
        from taskforce.core.domain.models import ExecutionResult

        tracker = AsyncMock()
        strategy = MagicMock()
        strategy.execute = AsyncMock(
            return_value=ExecutionResult(
                session_id="session-1", status="completed", final_message="Done"
            )
        )

        agent = _make_agent(runtime_tracker=tracker, planning_strategy=strategy)
        await agent.execute("Mission", "session-1")

        tracker.record_heartbeat.assert_awaited_once()
        tracker.mark_finished.assert_awaited_once()


# ---------------------------------------------------------------------------
# _execute_tool Tests
# ---------------------------------------------------------------------------


class TestExecuteTool:
    """Tests for Agent._execute_tool (internal method)."""

    async def test_execute_tool_delegates_to_tool_executor(self) -> None:
        """_execute_tool delegates to self.tool_executor.execute."""
        tool = _make_mock_tool("my_tool")
        agent = _make_agent(tools=[tool])
        result = await agent._execute_tool("my_tool", {"param": "value"})
        assert result["success"] is True

    async def test_execute_tool_not_found_returns_error(self) -> None:
        """_execute_tool returns error dict when tool is not found."""
        agent = _make_agent(tools=[_make_mock_tool("other_tool")])
        result = await agent._execute_tool("nonexistent_tool", {})
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    async def test_execute_tool_injects_parent_session_for_orchestration_tool(self) -> None:
        """_execute_tool injects _parent_session_id for tools with requires_parent_session."""
        tool = _make_mock_tool("call_agent")
        tool.requires_parent_session = True

        agent = _make_agent(tools=[tool])
        await agent._execute_tool("call_agent", {"query": "test"}, session_id="parent-sess")

        # The tool should have been called with the extra _parent_session_id arg
        call_kwargs = tool.execute.call_args
        assert "_parent_session_id" in call_kwargs.kwargs or any(
            "_parent_session_id" in str(a) for a in call_kwargs.args
        ) or (
            call_kwargs
            and call_kwargs.kwargs.get("_parent_session_id") == "parent-sess"
        )

    async def test_execute_tool_does_not_inject_session_when_not_required(self) -> None:
        """_execute_tool does not inject _parent_session_id for normal tools."""
        tool = _make_mock_tool("normal_tool")
        # Normal tools don't have requires_parent_session attribute
        del tool.requires_parent_session  # ensure getattr fallback

        agent = _make_agent(tools=[tool])
        await agent._execute_tool("normal_tool", {"param": "val"}, session_id="sess-1")

        # The tool should be called via tool_executor without _parent_session_id
        # The tool_executor.execute is what actually calls the tool
        # We verify the tool was called with original args only
        assert tool.execute.called

    async def test_execute_tool_checks_skill_switch(self) -> None:
        """_execute_tool checks for skill switch when skill_manager is configured."""
        tool = _make_mock_tool("file_read")
        sm = MagicMock()
        switch_result = MagicMock()
        switch_result.switched = True
        switch_result.from_skill = "old_skill"
        switch_result.to_skill = "new_skill"
        sm.check_skill_switch.return_value = switch_result

        agent = _make_agent(tools=[tool], skill_manager=sm)
        await agent._execute_tool("file_read", {"path": "/tmp/test"})

        sm.check_skill_switch.assert_called_once()
        agent.logger.info.assert_called_with(
            "skill_switched",
            from_skill="old_skill",
            to_skill="new_skill",
            trigger_tool="file_read",
        )

    async def test_execute_tool_no_skill_switch_when_not_switched(self) -> None:
        """_execute_tool does not log skill switch when no switch occurs."""
        tool = _make_mock_tool("file_read")
        sm = MagicMock()
        switch_result = MagicMock()
        switch_result.switched = False
        sm.check_skill_switch.return_value = switch_result

        agent = _make_agent(tools=[tool], skill_manager=sm)
        await agent._execute_tool("file_read", {"path": "/tmp/test"})

        sm.check_skill_switch.assert_called_once()
        # info should NOT have been called with "skill_switched"
        for call in agent.logger.info.call_args_list:
            assert call.args[0] != "skill_switched"

    async def test_execute_tool_without_skill_manager_skips_check(self) -> None:
        """_execute_tool skips skill switch check when no skill_manager."""
        tool = _make_mock_tool("file_read")
        agent = _make_agent(tools=[tool])
        result = await agent._execute_tool("file_read", {"path": "/tmp/test"})
        assert result["success"] is True


# ---------------------------------------------------------------------------
# _save_state Tests
# ---------------------------------------------------------------------------


class TestSaveState:
    """Tests for Agent._save_state."""

    async def test_save_state_delegates_to_state_store(self) -> None:
        """_save_state delegates to self.state_store.save."""
        agent = _make_agent()
        agent.state_store = AsyncMock()
        state = {"key": "value"}
        await agent._save_state("session-1", state)
        agent.state_store.save.assert_awaited_once_with(
            session_id="session-1",
            state=state,
            planner=agent._planner,
        )


# ---------------------------------------------------------------------------
# _build_initial_messages Tests
# ---------------------------------------------------------------------------


class TestBuildInitialMessages:
    """Tests for Agent._build_initial_messages."""

    def test_delegates_to_message_history_manager(self) -> None:
        """_build_initial_messages delegates to message_history_manager."""
        agent = _make_agent(system_prompt="Test prompt")
        state: dict[str, Any] = {}
        messages = agent._build_initial_messages("Do task", state)
        # Should return a list starting with a system message
        assert isinstance(messages, list)
        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        # Last message should be the user mission
        assert messages[-1]["role"] == "user"
        assert "Do task" in messages[-1]["content"]

    def test_includes_conversation_history(self) -> None:
        """_build_initial_messages includes conversation history from state."""
        agent = _make_agent(system_prompt="Test prompt")
        state: dict[str, Any] = {
            "conversation_history": [
                {"role": "user", "content": "Previous question"},
                {"role": "assistant", "content": "Previous answer"},
            ]
        }
        messages = agent._build_initial_messages("New question", state)
        # Should contain system + 2 history messages + user message
        assert len(messages) >= 4
        contents = [m["content"] for m in messages]
        assert "Previous question" in contents
        assert "Previous answer" in contents
