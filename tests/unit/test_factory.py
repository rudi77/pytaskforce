"""
Unit tests for AgentFactory.

Tests verify:
- Correct adapter wiring for each profile
- Agent creation with dev/staging/prod profiles
- RAG agent creation with RAG tools
- Configuration loading and validation
- Error handling for missing configs
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from taskforce.application.factory import AgentFactory
from taskforce.core.domain.agent import Agent
from taskforce.infrastructure.persistence.file_state import FileStateManager


class TestAgentFactory:
    """Test suite for AgentFactory."""

    def test_factory_initialization(self):
        """Test factory initializes with config directory."""
        factory = AgentFactory(config_dir="configs")
        assert factory.config_dir == Path("configs")

    def test_load_profile_dev(self):
        """Test loading dev profile."""
        factory = AgentFactory(config_dir="configs")
        config = factory._load_profile("dev")

        assert config["profile"] == "dev"
        assert config["persistence"]["type"] == "file"
        assert config["persistence"]["work_dir"] == ".taskforce"

    def test_load_profile_staging(self):
        """Test loading staging profile."""
        factory = AgentFactory(config_dir="configs")
        config = factory._load_profile("staging")

        assert config["profile"] == "staging"
        assert config["persistence"]["type"] == "database"
        assert "db_url_env" in config["persistence"]

    def test_load_profile_prod(self):
        """Test loading prod profile."""
        factory = AgentFactory(config_dir="configs")
        config = factory._load_profile("prod")

        assert config["profile"] == "prod"
        assert config["persistence"]["type"] == "database"
        assert config["llm"]["default_model"] == "powerful"

    def test_load_profile_not_found(self):
        """Test error when profile not found."""
        factory = AgentFactory(config_dir="configs")

        with pytest.raises(FileNotFoundError, match="Profile not found"):
            factory._load_profile("nonexistent")

    def test_create_state_manager_file(self):
        """Test creating file-based state manager."""
        factory = AgentFactory(config_dir="configs")
        config = {"persistence": {"type": "file", "work_dir": ".test_taskforce"}}

        state_manager = factory._create_state_manager(config)

        assert isinstance(state_manager, FileStateManager)
        assert state_manager.work_dir == Path(".test_taskforce")

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"})
    def test_create_state_manager_database(self):
        """Test creating database state manager."""
        factory = AgentFactory(config_dir="configs")
        config = {"persistence": {"type": "database", "db_url_env": "DATABASE_URL"}}

        # Import here to avoid dependency issues if db_state not implemented yet
        try:
            from taskforce.infrastructure.persistence.db_state import DbStateManager

            state_manager = factory._create_state_manager(config)
            assert isinstance(state_manager, DbStateManager)
        except ImportError:
            pytest.skip("DbStateManager not yet implemented")

    def test_create_state_manager_invalid_type(self):
        """Test error for invalid persistence type."""
        factory = AgentFactory(config_dir="configs")
        config = {"persistence": {"type": "invalid"}}

        with pytest.raises(ValueError, match="Unknown persistence type"):
            factory._create_state_manager(config)

    def test_create_llm_provider(self):
        """Test creating LLM provider."""
        factory = AgentFactory(config_dir="configs")
        config = {"llm": {"config_path": "configs/llm_config.yaml"}}

        llm_provider = factory._create_llm_provider(config)

        # Verify it's an OpenAIService instance
        from taskforce.infrastructure.llm.openai_service import OpenAIService

        assert isinstance(llm_provider, OpenAIService)

    def test_create_native_tools(self):
        """Test creating native tools."""
        factory = AgentFactory(config_dir="configs")
        config = {}

        # Create mock LLM provider
        mock_llm = MagicMock()

        tools = factory._create_native_tools(config, mock_llm)

        # Verify we have the expected number of tools
        # NOTE: llm_generate is intentionally excluded (Story 4.1)
        assert len(tools) == 9  # 9 native tools (no llm_generate)

        # Verify tool names
        tool_names = [tool.name for tool in tools]
        expected_tools = [
            "web_search",
            "web_fetch",
            "python",
            "github",
            "git",
            "file_read",
            "file_write",
            "powershell",
            # "llm_generate" intentionally excluded - agent uses internal LLM
            "ask_user",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Tool {expected} not found in {tool_names}"

    @patch.dict(
        os.environ,
        {
            "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
            "AZURE_SEARCH_API_KEY": "test-key",
        },
    )
    def test_create_rag_tools(self):
        """Test creating RAG tools."""
        factory = AgentFactory(config_dir="configs")
        config = {
            "rag": {
                "endpoint_env": "AZURE_SEARCH_ENDPOINT",
                "api_key_env": "AZURE_SEARCH_API_KEY",
                "index_name": "test-docs",
            }
        }

        user_context = {"user_id": "test_user", "org_id": "test_org"}
        tools = factory._create_rag_tools(config, user_context)

        # Verify we have 3 RAG tools
        assert len(tools) == 3

        # Verify tool names
        tool_names = [tool.name for tool in tools]
        expected_tools = ["rag_semantic_search", "rag_list_documents", "rag_get_document"]

        for expected in expected_tools:
            assert expected in tool_names, f"Tool {expected} not found in {tool_names}"

    def test_create_rag_tools_missing_config(self):
        """Test warning when RAG config is missing (not an error)."""
        factory = AgentFactory(config_dir="configs")
        config = {}  # No RAG config

        # Should succeed but log a warning (RAG tools get config from environment)
        tools = factory._create_rag_tools(config, None)
        assert len(tools) == 3  # Still creates tools

    def test_create_rag_tools_missing_credentials(self):
        """Test RAG tools creation (credentials checked at runtime, not construction)."""
        factory = AgentFactory(config_dir="configs")
        config = {
            "rag": {
                "endpoint_env": "MISSING_ENDPOINT",
                "api_key_env": "MISSING_KEY",
                "index_name": "test-docs",
            }
        }

        # Tools are created successfully; credentials are checked at execution time
        tools = factory._create_rag_tools(config, None)
        assert len(tools) == 3

    def test_create_todolist_manager(self):
        """Test creating TodoList manager."""
        factory = AgentFactory(config_dir="configs")
        config = {}

        # Create mock LLM provider
        mock_llm = MagicMock()

        todolist_manager = factory._create_todolist_manager(config, mock_llm)

        # Verify it's a PlanGenerator instance
        from taskforce.core.domain.plan import PlanGenerator

        assert isinstance(todolist_manager, PlanGenerator)

    def test_load_system_prompt_generic(self):
        """Test loading generic system prompt."""
        factory = AgentFactory(config_dir="configs")

        prompt = factory._load_system_prompt("generic")

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "ReAct" in prompt or "agent" in prompt.lower()

    def test_load_system_prompt_rag(self):
        """Test loading RAG system prompt."""
        factory = AgentFactory(config_dir="configs")

        prompt = factory._load_system_prompt("rag")

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "RAG" in prompt or "retrieval" in prompt.lower()

    def test_load_system_prompt_invalid(self):
        """Test error for invalid agent type."""
        factory = AgentFactory(config_dir="configs")

        with pytest.raises(ValueError, match="Unknown agent type"):
            factory._load_system_prompt("invalid")

    @pytest.mark.asyncio
    async def test_create_agent_with_dev_profile(self):
        """Test creating agent with dev profile."""
        factory = AgentFactory(config_dir="configs")

        agent = await factory.create_agent(profile="dev")

        # Verify agent is created
        assert isinstance(agent, Agent)
        assert agent.state_manager is not None
        assert agent.llm_provider is not None
        assert len(agent.tools) > 0
        assert agent.todolist_manager is not None
        assert agent.system_prompt is not None

    @pytest.mark.asyncio
    async def test_create_agent_with_work_dir_override(self):
        """Test creating agent with work_dir override."""
        factory = AgentFactory(config_dir="configs")

        agent = await factory.create_agent(profile="dev", work_dir=".test_work")

        # Verify state manager uses overridden work_dir
        assert isinstance(agent.state_manager, FileStateManager)
        assert agent.state_manager.work_dir == Path(".test_work")

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {
            "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
            "AZURE_SEARCH_API_KEY": "test-key",
        },
    )
    async def test_create_rag_agent_with_dev_profile(self):
        """Test creating RAG agent with dev profile."""
        factory = AgentFactory(config_dir="configs")

        # Use dev profile (file-based persistence) instead of staging (database)
        agent = await factory.create_rag_agent(
            profile="dev",
            user_context={"user_id": "test_user", "org_id": "test_org"},
            work_dir=".test_rag_work",
        )

        # Verify agent is created
        assert isinstance(agent, Agent)
        assert agent.state_manager is not None
        assert agent.llm_provider is not None
        # NOTE: llm_generate excluded (Story 4.1), so 9 native + 3 RAG = 12+
        assert len(agent.tools) > 9  # Native + RAG tools
        assert agent.todolist_manager is not None
        assert agent.system_prompt is not None

        # Verify RAG tools are present
        tool_names = list(agent.tools.keys())
        assert "rag_semantic_search" in tool_names
        assert "rag_list_documents" in tool_names
        assert "rag_get_document" in tool_names

    @pytest.mark.asyncio
    async def test_create_rag_agent_has_more_tools_than_generic(self):
        """Test that RAG agent has more tools than generic agent."""
        factory = AgentFactory(config_dir="configs")

        generic_agent = await factory.create_agent(profile="dev")

        # Mock environment for RAG agent
        with patch.dict(
            os.environ,
            {
                "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
                "AZURE_SEARCH_API_KEY": "test-key",
            },
        ):
            # Use dev profile instead of staging to avoid database dependency
            rag_agent = await factory.create_rag_agent(
                profile="dev",
                user_context={"user_id": "test", "org_id": "test"},
            )

        # RAG agent should have 3 more tools (RAG tools)
        assert len(rag_agent.tools) == len(generic_agent.tools) + 3


class TestSpecialistProfiles:
    """Tests for specialist profile functionality (Kernel + Specialist prompts)."""

    def test_assemble_system_prompt_generic(self):
        """Test assembling system prompt for generic specialist."""
        factory = AgentFactory(config_dir="configs")

        prompt = factory._assemble_system_prompt("generic")

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain kernel prompt content
        assert "Autonomous Agent" in prompt or "autonomous" in prompt.lower()

    def test_assemble_system_prompt_coding(self):
        """Test assembling system prompt for coding specialist."""
        factory = AgentFactory(config_dir="configs")

        prompt = factory._assemble_system_prompt("coding")

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain both kernel and coding specialist content
        assert "Autonomous Agent" in prompt or "autonomous" in prompt.lower()
        assert "Coding Specialist" in prompt or "file" in prompt.lower()

    def test_assemble_system_prompt_rag(self):
        """Test assembling system prompt for RAG specialist."""
        factory = AgentFactory(config_dir="configs")

        prompt = factory._assemble_system_prompt("rag")

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain both kernel and RAG specialist content
        assert "Autonomous Agent" in prompt or "autonomous" in prompt.lower()
        assert "RAG Specialist" in prompt or "semantic" in prompt.lower()

    def test_assemble_system_prompt_invalid(self):
        """Test error for invalid specialist profile."""
        factory = AgentFactory(config_dir="configs")

        with pytest.raises(ValueError, match="Unknown specialist profile"):
            factory._assemble_system_prompt("invalid")

    def test_create_specialist_tools_coding(self):
        """Test creating tools for coding specialist."""
        factory = AgentFactory(config_dir="configs")
        config = {}
        mock_llm = MagicMock()

        tools = factory._create_specialist_tools("coding", config, mock_llm)

        # Coding specialist should have 4 tools
        assert len(tools) == 4

        tool_names = [tool.name for tool in tools]
        expected_tools = ["file_read", "file_write", "powershell", "ask_user"]

        for expected in expected_tools:
            assert expected in tool_names, f"Tool {expected} not found"

    @patch.dict(
        os.environ,
        {
            "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
            "AZURE_SEARCH_API_KEY": "test-key",
        },
    )
    def test_create_specialist_tools_rag(self):
        """Test creating tools for RAG specialist."""
        factory = AgentFactory(config_dir="configs")
        config = {}  # RAG tools get config from environment
        mock_llm = MagicMock()
        user_context = {"user_id": "test_user", "org_id": "test_org"}

        tools = factory._create_specialist_tools(
            "rag", config, mock_llm, user_context=user_context
        )

        # RAG specialist should have 4 tools
        assert len(tools) == 4

        tool_names = [tool.name for tool in tools]
        expected_tools = [
            "rag_semantic_search",
            "rag_list_documents",
            "rag_get_document",
            "ask_user",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Tool {expected} not found"

    def test_create_specialist_tools_invalid(self):
        """Test error for invalid specialist profile."""
        factory = AgentFactory(config_dir="configs")
        config = {}
        mock_llm = MagicMock()

        with pytest.raises(ValueError, match="Unknown specialist profile"):
            factory._create_specialist_tools("invalid", config, mock_llm)

    @pytest.mark.asyncio
    async def test_create_agent_with_coding_specialist_from_config(self):
        """Test creating agent with coding specialist using coding_dev config."""
        factory = AgentFactory(config_dir="configs")

        # coding_dev.yaml has specialist: coding AND tools defined
        agent = await factory.create_agent(
            profile="coding_dev",
            work_dir=".test_coding_agent",
        )

        assert isinstance(agent, Agent)
        assert len(agent.tools) == 4  # 4 coding tools from config

        tool_names = list(agent.tools.keys())
        assert "file_read" in tool_names
        assert "file_write" in tool_names
        assert "powershell" in tool_names
        assert "ask_user" in tool_names
        # Prompt should still be coding specialist
        assert "Coding Specialist" in agent.system_prompt

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {
            "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
            "AZURE_SEARCH_API_KEY": "test-key",
        },
    )
    async def test_create_agent_with_rag_specialist_from_config(self):
        """Test creating agent with RAG specialist using rag_dev config."""
        factory = AgentFactory(config_dir="configs")

        # rag_dev.yaml has specialist: rag AND tools defined
        agent = await factory.create_agent(
            profile="rag_dev",
            work_dir=".test_rag_agent",
        )

        assert isinstance(agent, Agent)
        # rag_dev has RAG tools + standard tools in config
        assert len(agent.tools) >= 4

        tool_names = list(agent.tools.keys())
        assert "rag_semantic_search" in tool_names
        assert "rag_list_documents" in tool_names
        assert "rag_get_document" in tool_names
        # Prompt should be RAG specialist
        assert "RAG Specialist" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_config_tools_override_specialist_defaults(self):
        """Test that config tools override specialist defaults (Option B)."""
        factory = AgentFactory(config_dir="configs")

        # dev.yaml has tools defined AND specialist: generic
        # Even if we specify specialist="coding", it should use config tools
        generic_agent = await factory.create_agent(profile="dev")
        
        # coding_dev.yaml has tools defined
        coding_agent = await factory.create_agent(profile="coding_dev")

        # Both configs have tools, so tools come from config (not specialist defaults)
        # dev has more tools than coding_dev
        assert len(generic_agent.tools) > len(coding_agent.tools)
        assert len(coding_agent.tools) == 4  # coding_dev has 4 tools in config

    @pytest.mark.asyncio
    async def test_specialist_prompt_is_longer_than_kernel_only(self):
        """Test that specialist prompts add content to the kernel."""
        factory = AgentFactory(config_dir="configs")

        generic_agent = await factory.create_agent(profile="dev", specialist="generic")
        coding_agent = await factory.create_agent(profile="dev", specialist="coding")

        # Coding prompt should be longer (kernel + specialist)
        assert len(coding_agent.system_prompt) > len(generic_agent.system_prompt)

    @pytest.mark.asyncio
    async def test_create_agent_loads_specialist_from_config(self):
        """Test that specialist is loaded from config YAML when not provided."""
        factory = AgentFactory(config_dir="configs")

        # coding_dev.yaml has specialist: coding
        agent = await factory.create_agent(profile="coding_dev")

        # Should have coding tools (4 tools)
        assert len(agent.tools) == 4
        tool_names = list(agent.tools.keys())
        assert "file_read" in tool_names
        assert "file_write" in tool_names
        assert "powershell" in tool_names
        assert "ask_user" in tool_names

        # Should have coding specialist prompt
        assert "Coding Specialist" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_specialist_param_overrides_config_for_prompt(self):
        """Test that specialist parameter overrides config for prompt selection."""
        factory = AgentFactory(config_dir="configs")

        # dev.yaml has specialist: generic AND tools defined
        # Override specialist to "coding" - this affects the PROMPT, not tools
        # (because dev.yaml has tools defined, those are used)
        agent = await factory.create_agent(profile="dev", specialist="coding")

        # Tools come from config (dev.yaml has tools)
        # NOTE: llm_generate excluded (Story 4.1), so 9+ tools
        assert len(agent.tools) >= 9  # dev has 9+ tools (no llm_generate)
        assert "file_read" in agent.tools
        # But prompt should be coding specialist (parameter override)
        assert "Coding Specialist" in agent.system_prompt


class TestAgentFactoryIntegration:
    """Integration tests for AgentFactory with real dependencies."""

    @pytest.mark.asyncio
    async def test_agent_construction_time(self):
        """Test agent construction completes in <200ms (IV3)."""
        import time

        factory = AgentFactory(config_dir="configs")

        start = time.time()
        agent = await factory.create_agent(profile="dev")
        duration = (time.time() - start) * 1000  # Convert to ms

        assert isinstance(agent, Agent)
        assert duration < 200, f"Agent construction took {duration:.2f}ms (>200ms)"

    @pytest.mark.asyncio
    async def test_agent_has_correct_tool_count(self):
        """Test agent has expected number of tools."""
        factory = AgentFactory(config_dir="configs")
        agent = await factory.create_agent(profile="dev")

        # Should have 9 native tools (llm_generate excluded per Story 4.1)
        assert len(agent.tools) == 9

    @pytest.mark.asyncio
    async def test_multiple_agents_can_be_created(self):
        """Test multiple agents can be created from same factory."""
        factory = AgentFactory(config_dir="configs")

        agent1 = await factory.create_agent(profile="dev", work_dir=".test_agent1")
        agent2 = await factory.create_agent(profile="dev", work_dir=".test_agent2")

        assert isinstance(agent1, Agent)
        assert isinstance(agent2, Agent)
        assert agent1 is not agent2
        assert agent1.state_manager is not agent2.state_manager


class TestLeanAgentFactory:
    """Tests for LeanAgent factory creation (Story 5: CLI Integration)."""

    @pytest.mark.asyncio
    async def test_create_lean_agent_basic(self):
        """Test creating a basic LeanAgent."""
        from taskforce.core.domain.lean_agent import LeanAgent

        factory = AgentFactory(config_dir="configs")
        agent = await factory.create_lean_agent(profile="dev")

        assert isinstance(agent, LeanAgent)
        assert agent.state_manager is not None
        assert agent.llm_provider is not None
        assert len(agent.tools) > 0

    @pytest.mark.asyncio
    async def test_lean_agent_has_planner_tool(self):
        """Test that LeanAgent has PlannerTool injected."""
        from taskforce.core.tools.planner_tool import PlannerTool

        factory = AgentFactory(config_dir="configs")
        agent = await factory.create_lean_agent(profile="dev")

        # PlannerTool should be present (injected by LeanAgent if not in tools)
        assert "planner" in agent.tools
        assert isinstance(agent.tools["planner"], PlannerTool)

    @pytest.mark.asyncio
    async def test_lean_agent_uses_lean_kernel_prompt(self):
        """Test that LeanAgent uses LEAN_KERNEL_PROMPT."""
        from taskforce.core.prompts.autonomous_prompts import LEAN_KERNEL_PROMPT

        factory = AgentFactory(config_dir="configs")
        agent = await factory.create_lean_agent(profile="dev")

        # The system prompt should contain LEAN_KERNEL_PROMPT content
        assert "Lean ReAct Agent" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_lean_agent_with_specialist(self):
        """Test creating LeanAgent with specialist profile."""
        factory = AgentFactory(config_dir="configs")
        agent = await factory.create_lean_agent(profile="dev", specialist="coding")

        # Should have coding specialist content appended
        assert "Coding Specialist" in agent.system_prompt or "Senior Software Engineer" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_lean_agent_work_dir_override(self):
        """Test LeanAgent with work_dir override."""
        from taskforce.core.domain.lean_agent import LeanAgent

        factory = AgentFactory(config_dir="configs")
        agent = await factory.create_lean_agent(
            profile="dev", work_dir=".lean_test_workdir"
        )

        assert isinstance(agent, LeanAgent)
        # State manager should use the override work_dir
        assert ".lean_test_workdir" in str(agent.state_manager.work_dir)

    @pytest.mark.asyncio
    async def test_assemble_lean_system_prompt_no_specialist(self):
        """Test lean system prompt assembly without specialist."""
        factory = AgentFactory(config_dir="configs")
        
        prompt = factory._assemble_lean_system_prompt(None, [])
        
        assert "Lean ReAct Agent" in prompt
        # Should not have specialist-specific content
        assert "Coding Specialist" not in prompt
        assert "RAG Specialist" not in prompt

    @pytest.mark.asyncio
    async def test_assemble_lean_system_prompt_with_coding(self):
        """Test lean system prompt assembly with coding specialist."""
        factory = AgentFactory(config_dir="configs")
        
        prompt = factory._assemble_lean_system_prompt("coding", [])
        
        assert "Lean ReAct Agent" in prompt
        # Should have coding specialist content
        assert "Senior Software Engineer" in prompt or "Coding Specialist" in prompt

    @pytest.mark.asyncio
    async def test_assemble_lean_system_prompt_with_rag(self):
        """Test lean system prompt assembly with rag specialist."""
        factory = AgentFactory(config_dir="configs")
        
        prompt = factory._assemble_lean_system_prompt("rag", [])
        
        assert "Lean ReAct Agent" in prompt
        # Should have RAG specialist content
        assert "RAG" in prompt