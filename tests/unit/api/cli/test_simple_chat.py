from __future__ import annotations

from types import SimpleNamespace

import pytest
from rich.console import Console

from taskforce.api.cli.simple_chat import SimpleChatRunner
from taskforce.core.domain.agent_definition import AgentDefinition, AgentSource
from taskforce.core.domain.enums import SkillType
from taskforce.core.domain.skill import SkillMetadataModel


class DummyStateManager:
    def __init__(self, initial_state: dict | None = None) -> None:
        self._states: dict[str, dict] = {}
        self._initial = initial_state or {
            "conversation_history": [{"role": "user", "content": "Hello"}]
        }

    async def load_state(self, session_id: str) -> dict:
        return self._states.get(session_id, dict(self._initial))

    async def save_state(self, session_id: str, state_data: dict) -> None:
        self._states[session_id] = state_data


class DummySkillManager:
    active_skill_name = "debug-skill"

    def get_active_instructions(self) -> str:
        return "Focus on concise diagnostics."


class DummyAgent:
    def __init__(self) -> None:
        self.closed = False
        self.state_manager = DummyStateManager()
        self.system_prompt = "Base system prompt"
        self.skill_manager = DummySkillManager()
        self._openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        self.token_budgeter = SimpleNamespace(max_input_tokens=1000)

    def _build_system_prompt(self, mission=None, state=None, messages=None) -> str:
        return "Base system prompt\n\n## CURRENT PLAN STATUS\n- Step 1"

    async def close(self) -> None:
        self.closed = True


class DummyAgentRegistry:
    def __init__(self, plugins: list[AgentDefinition]) -> None:
        self._plugins = plugins

    def list_all(self, sources: list[AgentSource] | None = None) -> list[AgentDefinition]:
        return list(self._plugins)

    def get(self, agent_id: str) -> AgentDefinition | None:
        for plugin in self._plugins:
            if plugin.agent_id == agent_id:
                return plugin
        return None


class DummySkillService:
    """Minimal stub for SkillService used in chat tests."""

    def __init__(self, metadata: list[SkillMetadataModel] | None = None) -> None:
        self._metadata = metadata or []
        self._active: list = []

    def get_all_metadata(self) -> list[SkillMetadataModel]:
        return list(self._metadata)

    def get_active_skills(self) -> list:
        return list(self._active)

    def resolve_slash_command(self, command_input: str) -> tuple[None, str]:
        return None, ""


class DummyFactory:
    def __init__(self, agent: DummyAgent) -> None:
        self.agent = agent
        self.received_plugin_path: str | None = None
        self.received_profile: str | None = None
        self.received_user_context: dict[str, str] | None = None

    async def create_agent_with_plugin(
        self,
        plugin_path: str,
        profile: str,
        user_context: dict[str, str] | None = None,
    ) -> DummyAgent:
        self.received_plugin_path = plugin_path
        self.received_profile = profile
        self.received_user_context = user_context
        return self.agent


def _build_runner(agent: DummyAgent) -> SimpleChatRunner:
    runner = SimpleChatRunner(
        session_id="session-id",
        profile="dev",
        agent=agent,
        stream=True,
        user_context=None,
    )
    runner.console = Console(record=True)
    return runner


def test_list_plugins_renders_available_plugins() -> None:
    plugin_def = AgentDefinition(
        agent_id="accounting_agent",
        name="Accounting Agent",
        description="Handles accounting tasks.",
        source=AgentSource.PLUGIN,
        plugin_path="examples/accounting_agent",
    )
    runner = _build_runner(DummyAgent())
    runner.agent_registry = DummyAgentRegistry([plugin_def])

    runner._list_plugins()

    output = runner.console.export_text()
    assert "/accounting_agent" in output
    assert "Handles accounting tasks." in output


def test_list_skills_shows_grouped_output() -> None:
    """_list_skills() should show skills grouped by type via SkillService."""
    meta_prompt = SkillMetadataModel(
        name="code-review",
        description="Review code quality",
        source_path="/some/path",
        skill_type=SkillType.PROMPT,
    )
    meta_context = SkillMetadataModel(
        name="pdf-processing",
        description="Process PDF files",
        source_path="/some/other/path",
        skill_type=SkillType.CONTEXT,
    )
    runner = _build_runner(DummyAgent())
    runner._skill_service = DummySkillService(metadata=[meta_prompt, meta_context])

    runner._list_skills()

    output = runner.console.export_text()
    assert "code-review" in output
    assert "pdf-processing" in output
    assert "Prompt skills" in output or "prompt" in output.lower()


def test_list_skills_shows_empty_message_when_no_skills() -> None:
    """_list_skills() shows a helpful message when no skills are found."""
    runner = _build_runner(DummyAgent())
    runner._skill_service = DummySkillService(metadata=[])

    runner._list_skills()

    output = runner.console.export_text()
    assert "No skills found" in output


@pytest.mark.asyncio
async def test_try_switch_plugin_command(monkeypatch) -> None:
    plugin_def = AgentDefinition(
        agent_id="accounting_agent",
        name="Accounting Agent",
        description="Handles accounting tasks.",
        source=AgentSource.PLUGIN,
        plugin_path="examples/accounting_agent",
        base_profile="dev",
    )
    old_agent = DummyAgent()
    new_agent = DummyAgent()
    runner = _build_runner(old_agent)
    runner.agent_registry = DummyAgentRegistry([plugin_def])

    factory = DummyFactory(new_agent)

    monkeypatch.setattr(
        "taskforce.api.cli.simple_chat.AgentFactory",
        lambda: factory,
    )

    result = await runner._try_switch_plugin("accounting_agent")

    assert result is True
    assert old_agent.closed is True
    assert runner.agent is new_agent
    assert runner.profile == "plugin:accounting_agent"
    assert factory.received_plugin_path == "examples/accounting_agent"


@pytest.mark.asyncio
async def test_context_command_renders_snapshot() -> None:
    runner = _build_runner(DummyAgent())

    await runner._handle_command("/context")

    output = runner.console.export_text()
    assert "Context Snapshot" in output
    assert "System Prompt" in output
    assert "Conversation History" in output


@pytest.mark.asyncio
async def test_context_full_renders_content_column() -> None:
    runner = _build_runner(DummyAgent())

    await runner._handle_command("/context full")

    output = runner.console.export_text()
    assert "Content" in output


@pytest.mark.asyncio
async def test_tokens_command_shows_total() -> None:
    """/tokens prints the accumulated token count."""
    runner = _build_runner(DummyAgent())
    runner.total_tokens = 1234

    await runner._handle_command("/tokens")

    output = runner.console.export_text()
    assert "1,234" in output


@pytest.mark.asyncio
async def test_clear_resets_context() -> None:
    """/clear resets conversation history, token counter, and plan state."""
    agent = DummyAgent()
    runner = _build_runner(agent)

    # Simulate accumulated state
    runner.total_tokens = 500
    runner.plan_state.steps = [{"description": "step 1", "status": "PENDING"}]
    runner._last_event_signature = ("tool_call", "file_read:{}")

    # Store conversation history for this session
    await agent.state_manager.save_state(
        "session-id",
        {"conversation_history": [{"role": "user", "content": "Hello"}]},
    )

    await runner._handle_command("/clear")

    # In-memory counters should be reset
    assert runner.total_tokens == 0
    assert runner.plan_state.steps == []
    assert runner.plan_state.text is None
    assert runner._last_event_signature is None

    # Conversation history should be cleared in the state manager
    state = await agent.state_manager.load_state("session-id")
    assert state["conversation_history"] == []
