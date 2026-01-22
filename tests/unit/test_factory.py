"""
Unit tests for AgentFactory - Agent creation.

Tests verify:
- Agent creation with dev profile
- Planning strategy configuration
- Specialist profile integration
- System prompt assembly
"""

from unittest.mock import MagicMock

import pytest

from taskforce.application.factory import AgentFactory


class TestAgentFactory:
    """Tests for Agent factory creation (Story 5: CLI Integration)."""

    @pytest.mark.asyncio
    async def test_create_lean_agent_basic(self):
        """Test creating a basic Agent."""
        from taskforce.core.domain.agent import Agent

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_lean_agent(profile="dev")

        assert isinstance(agent, Agent)
        assert agent.state_manager is not None
        assert agent.llm_provider is not None
        assert len(agent.tools) > 0

    @pytest.mark.asyncio
    async def test_lean_agent_has_planner_tool(self):
        """Test that Agent has PlannerTool injected."""
        from taskforce.core.tools.planner_tool import PlannerTool

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_lean_agent(profile="dev")

        # PlannerTool should be present (injected by Agent if not in tools)
        assert "planner" in agent.tools
        assert isinstance(agent.tools["planner"], PlannerTool)

    @pytest.mark.asyncio
    async def test_lean_agent_uses_lean_kernel_prompt(self):
        """Test that Agent uses LEAN_KERNEL_PROMPT."""
        from taskforce.core.prompts.autonomous_prompts import LEAN_KERNEL_PROMPT

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_lean_agent(profile="dev")

        # The system prompt should contain LEAN_KERNEL_PROMPT content
        assert "Lean ReAct Agent" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_lean_agent_with_specialist(self):
        """Test creating Agent with specialist profile."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_lean_agent(profile="dev", specialist="coding")

        # Should have coding specialist content appended
        assert "Coding Specialist" in agent.system_prompt or "Senior Software Engineer" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_lean_agent_work_dir_override(self):
        """Test Agent with work_dir override."""
        from taskforce.core.domain.agent import Agent

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_lean_agent(
            profile="dev", work_dir=".lean_test_workdir"
        )

        assert isinstance(agent, Agent)
        # State manager should use the override work_dir
        assert ".lean_test_workdir" in str(agent.state_manager.work_dir)

    @pytest.mark.asyncio
    async def test_lean_agent_planning_strategy_default(self):
        """Test that Agent defaults to NativeReAct strategy."""
        from taskforce.core.domain.planning_strategy import NativeReActStrategy

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_lean_agent(profile="dev")

        assert isinstance(agent.planning_strategy, NativeReActStrategy)

    @pytest.mark.asyncio
    async def test_lean_agent_planning_strategy_override(self):
        """Test overriding planning strategy for Agent."""
        from taskforce.core.domain.planning_strategy import PlanAndExecuteStrategy

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_lean_agent(
            profile="dev",
            planning_strategy="plan_and_execute",
            planning_strategy_params={"max_step_iterations": 2, "max_plan_steps": 3},
        )

        assert isinstance(agent.planning_strategy, PlanAndExecuteStrategy)
        assert agent.planning_strategy.max_step_iterations == 2
        assert agent.planning_strategy.max_plan_steps == 3

    @pytest.mark.asyncio
    async def test_lean_agent_invalid_planning_strategy(self):
        """Test invalid planning strategy raises ValueError."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")

        with pytest.raises(ValueError):
            await factory.create_lean_agent(profile="dev", planning_strategy="invalid")

    @pytest.mark.asyncio
    async def test_assemble_lean_system_prompt_no_specialist(self):
        """Test lean system prompt assembly without specialist."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")

        prompt = factory._assemble_lean_system_prompt(None, [])

        assert "Lean ReAct Agent" in prompt
        # Should not have specialist-specific content
        assert "Coding Specialist" not in prompt
        assert "RAG Specialist" not in prompt

    @pytest.mark.asyncio
    async def test_assemble_lean_system_prompt_with_coding(self):
        """Test lean system prompt assembly with coding specialist."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")

        prompt = factory._assemble_lean_system_prompt("coding", [])

        assert "Lean ReAct Agent" in prompt
        # Should have coding specialist content
        assert "Senior Software Engineer" in prompt or "Coding Specialist" in prompt

    @pytest.mark.asyncio
    async def test_assemble_lean_system_prompt_with_rag(self):
        """Test lean system prompt assembly with rag specialist."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")

        prompt = factory._assemble_lean_system_prompt("rag", [])

        assert "Lean ReAct Agent" in prompt
        # Should have RAG specialist content
        assert "RAG" in prompt
