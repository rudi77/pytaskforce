"""
Unit tests for AgentFactory - Agent creation with unified API.

Tests verify:
- Agent creation with config file path
- Agent creation with inline parameters
- Mutually exclusive config vs inline parameters
- Planning strategy configuration
- Specialist profile integration
- System prompt assembly
- Backward compatibility with deprecated methods
"""

from unittest.mock import MagicMock
import warnings

import pytest

from taskforce.application.factory import AgentFactory


class TestAgentFactoryConfigFile:
    """Tests for Agent creation using config file path."""

    @pytest.mark.asyncio
    async def test_create_agent_with_config_path(self):
        """Test creating agent with config file path."""
        from taskforce.core.domain.agent import Agent

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(config="dev")

        assert isinstance(agent, Agent)
        assert agent.state_manager is not None
        assert agent.llm_provider is not None
        assert len(agent.tools) > 0

    @pytest.mark.asyncio
    async def test_create_agent_with_full_config_path(self):
        """Test creating agent with full config file path."""
        from taskforce.core.domain.agent import Agent

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(config="dev.yaml")

        assert isinstance(agent, Agent)

    @pytest.mark.asyncio
    async def test_create_agent_config_not_found(self):
        """Test error when config file not found."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")

        with pytest.raises(FileNotFoundError):
            await factory.create_agent(config="nonexistent_profile")

    @pytest.mark.asyncio
    async def test_create_agent_with_work_dir_override(self):
        """Test agent with work_dir override."""
        from taskforce.core.domain.agent import Agent

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(
            config="dev",
            work_dir=".test_workdir"
        )

        assert isinstance(agent, Agent)
        assert ".test_workdir" in str(agent.state_manager.work_dir)


class TestAgentFactoryInlineParams:
    """Tests for Agent creation using inline parameters."""

    @pytest.mark.asyncio
    async def test_create_agent_with_inline_tools(self):
        """Test creating agent with inline tool list."""
        from taskforce.core.domain.agent import Agent

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(
            tools=["python", "file_read"]
        )

        assert isinstance(agent, Agent)
        tool_names = [t.name for t in agent.tools.values()]
        assert "python" in tool_names
        assert "file_read" in tool_names

    @pytest.mark.asyncio
    async def test_create_agent_with_system_prompt(self):
        """Test creating agent with custom system prompt."""
        from taskforce.core.domain.agent import Agent

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(
            system_prompt="You are a custom test assistant.",
            tools=["python"]
        )

        assert isinstance(agent, Agent)
        assert "custom test assistant" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_create_agent_with_specialist(self):
        """Test creating agent with specialist profile."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(
            tools=["python"],
            specialist="coding"
        )

        # Should have coding specialist content in prompt (German: "Lead Software Architect")
        assert "Lead Software" in agent.system_prompt or "Architectural Mindset" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_create_agent_minimal_defaults(self):
        """Test creating agent with minimal parameters (uses defaults)."""
        from taskforce.core.domain.agent import Agent

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(
            tools=["python"]
        )

        assert isinstance(agent, Agent)
        assert agent.max_steps == 30  # Default from dev config

    @pytest.mark.asyncio
    async def test_create_agent_with_max_steps(self):
        """Test creating agent with custom max_steps."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(
            tools=["python"],
            max_steps=10
        )

        assert agent.max_steps == 10


class TestAgentFactoryMutualExclusion:
    """Tests for mutual exclusion of config vs inline parameters."""

    @pytest.mark.asyncio
    async def test_config_and_inline_raises_error(self):
        """Test that providing both config and inline params raises ValueError."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")

        with pytest.raises(ValueError) as exc_info:
            await factory.create_agent(
                config="dev",
                system_prompt="This should fail"
            )

        assert "Cannot use 'config' with inline parameters" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_config_and_tools_raises_error(self):
        """Test that providing config and tools raises ValueError."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")

        with pytest.raises(ValueError) as exc_info:
            await factory.create_agent(
                config="dev",
                tools=["python"]
            )

        assert "Cannot use 'config' with inline parameters" in str(exc_info.value)


class TestAgentFactoryPlanningStrategy:
    """Tests for planning strategy configuration."""

    @pytest.mark.asyncio
    async def test_default_planning_strategy(self):
        """Test that agent defaults to NativeReAct strategy."""
        from taskforce.core.domain.planning_strategy import NativeReActStrategy

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(config="dev")

        assert isinstance(agent.planning_strategy, NativeReActStrategy)

    @pytest.mark.asyncio
    async def test_planning_strategy_override_config(self):
        """Test overriding planning strategy with config file."""
        from taskforce.core.domain.planning_strategy import PlanAndExecuteStrategy

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(
            config="dev",
            planning_strategy="plan_and_execute",
            planning_strategy_params={"max_step_iterations": 2, "max_plan_steps": 3},
        )

        assert isinstance(agent.planning_strategy, PlanAndExecuteStrategy)
        assert agent.planning_strategy.max_step_iterations == 2
        assert agent.planning_strategy.max_plan_steps == 3

    @pytest.mark.asyncio
    async def test_planning_strategy_override_inline(self):
        """Test overriding planning strategy with inline params."""
        from taskforce.core.domain.planning_strategy import PlanAndReactStrategy

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(
            tools=["python"],
            planning_strategy="plan_and_react",
        )

        assert isinstance(agent.planning_strategy, PlanAndReactStrategy)

    @pytest.mark.asyncio
    async def test_invalid_planning_strategy(self):
        """Test invalid planning strategy raises ValueError."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")

        with pytest.raises(ValueError):
            await factory.create_agent(
                config="dev",
                planning_strategy="invalid_strategy"
            )


class TestAgentFactorySystemPrompt:
    """Tests for system prompt assembly."""

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
        # Should have coding specialist content (German: "Lead Software Architect")
        assert "Lead Software" in prompt or "Architectural Mindset" in prompt

    @pytest.mark.asyncio
    async def test_assemble_lean_system_prompt_with_rag(self):
        """Test lean system prompt assembly with rag specialist."""
        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")

        prompt = factory._assemble_lean_system_prompt("rag", [])

        assert "Lean ReAct Agent" in prompt
        # Should have RAG specialist content
        assert "RAG" in prompt


class TestAgentFactoryBackwardCompatibility:
    """Tests for backward compatibility with deprecated methods."""

    @pytest.mark.asyncio
    async def test_create_lean_agent_deprecated(self):
        """Test that create_lean_agent still works but shows deprecation warning."""
        from taskforce.core.domain.agent import Agent

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = await factory.create_lean_agent(profile="dev")

            # Check deprecation warning was raised
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()

        assert isinstance(agent, Agent)

    @pytest.mark.asyncio
    async def test_create_agent_from_definition_deprecated(self):
        """Test that create_agent_from_definition still works but shows deprecation warning."""
        from taskforce.core.domain.agent import Agent

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = await factory.create_agent_from_definition(
                agent_definition={
                    "system_prompt": "Test assistant",
                    "tool_allowlist": ["python"],
                },
                profile="dev",
            )

            # Check deprecation warning was raised
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()

        assert isinstance(agent, Agent)


class TestAgentFactoryHasPlannerTool:
    """Tests for PlannerTool injection."""

    @pytest.mark.asyncio
    async def test_agent_has_planner_tool_with_config(self):
        """Test that Agent has PlannerTool injected when using config."""
        from taskforce.core.tools.planner_tool import PlannerTool

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(config="dev")

        # PlannerTool should be present (injected by Agent if not in tools)
        assert "planner" in agent.tools
        assert isinstance(agent.tools["planner"], PlannerTool)

    @pytest.mark.asyncio
    async def test_agent_has_planner_tool_with_inline(self):
        """Test that Agent has PlannerTool injected when using inline params."""
        from taskforce.core.tools.planner_tool import PlannerTool

        factory = AgentFactory(config_dir="src/taskforce_extensions/configs")
        agent = await factory.create_agent(tools=["python"])

        # PlannerTool should be present
        assert "planner" in agent.tools
        assert isinstance(agent.tools["planner"], PlannerTool)
