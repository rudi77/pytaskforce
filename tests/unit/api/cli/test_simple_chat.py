from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from rich.console import Console

from taskforce.api.cli.simple_chat import SimpleChatRunner
from taskforce.application.executor import ProgressUpdate
from taskforce.core.domain.agent_definition import AgentDefinition, AgentSource
from taskforce.core.domain.enums import EventType, SkillType
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


def _build_runner(agent: DummyAgent, telegram_polling: bool = False) -> SimpleChatRunner:
    runner = SimpleChatRunner(
        session_id="session-id",
        profile="dev",
        agent=agent,
        stream=True,
        user_context=None,
        telegram_polling=telegram_polling,
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


def test_telegram_poller_not_initialized_without_flag(monkeypatch) -> None:
    """Telegram poller should stay disabled unless flag is set."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    runner = _build_runner(DummyAgent(), telegram_polling=False)
    assert runner._telegram_poller is None


@pytest.mark.asyncio
async def test_run_starts_and_stops_configured_telegram_poller() -> None:
    """Runner should start and stop an already configured poller."""
    runner = _build_runner(DummyAgent(), telegram_polling=True)
    fake_poller = AsyncMock()
    runner._telegram_poller = fake_poller

    async def _quit_immediately() -> str:
        return "/quit"

    runner._read_input = _quit_immediately  # type: ignore[method-assign]

    await runner.run()

    fake_poller.start.assert_awaited_once()
    fake_poller.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_inbound_message_routes_via_gateway() -> None:
    """Unsolicited Telegram messages should be processed by the gateway."""
    runner = _build_runner(DummyAgent(), telegram_polling=True)
    gateway = AsyncMock()
    gateway.handle_message = AsyncMock()
    runner._gateway = gateway

    await runner._handle_telegram_inbound_message(
        conversation_id="12345",
        sender_id="67890",
        message="Hallo Agent",
    )

    gateway.handle_message.assert_awaited_once()
    inbound_message, options = gateway.handle_message.await_args.args
    assert inbound_message.channel == "telegram"
    assert inbound_message.conversation_id == "12345"
    assert inbound_message.sender_id == "67890"
    assert inbound_message.message == "Hallo Agent"
    assert options.profile == "dev"


@pytest.mark.asyncio
async def test_stream_response_shows_thinking_and_file_change_preview() -> None:
    """Streaming UI should include thinking state and file-change preview lines."""
    runner = _build_runner(DummyAgent())

    updates = [
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.STEP_START.value,
            message="step",
            details={"step": 1},
        ),
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.TOOL_CALL.value,
            message="tool",
            details={
                "tool": "edit",
                "args": {
                    "file_path": "src/taskforce/application/factory.py",
                    "old_string": "context = old",
                    "new_string": "context = new",
                },
            },
        ),
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.FINAL_ANSWER.value,
            message="done",
            details={"content": "Alles erledigt"},
        ),
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.COMPLETE.value,
            message="complete",
            details={},
        ),
    ]

    async def _fake_stream(*args, **kwargs):
        for item in updates:
            yield item

    runner.executor.execute_mission_streaming = _fake_stream

    await runner._stream_response("Bitte ändere die Datei", [{"role": "user", "content": "x"}])

    output = runner.console.export_text()
    assert "Thinking..." in output
    assert "Update(" in output
    assert "context = old" in output
    assert "context = new" in output


@pytest.mark.asyncio
async def test_stream_response_emits_thinking_for_each_step() -> None:
    """Each new step should emit a Thinking indicator even after earlier thought events."""
    runner = _build_runner(DummyAgent())

    updates = [
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.STEP_START.value,
            message="step1",
            details={"step": 1},
        ),
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.THOUGHT.value,
            message="thought",
            details={"step": 1, "thought": "Ich prüfe Datei A"},
        ),
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.STEP_START.value,
            message="step2",
            details={"step": 2},
        ),
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.FINAL_ANSWER.value,
            message="done",
            details={"content": "Fertig"},
        ),
        ProgressUpdate(
            timestamp=datetime.now(),
            event_type=EventType.COMPLETE.value,
            message="complete",
            details={},
        ),
    ]

    async def _fake_stream(*args, **kwargs):
        for item in updates:
            yield item

    runner.executor.execute_mission_streaming = _fake_stream

    await runner._stream_response("Bitte in zwei Schritten arbeiten", [{"role": "user", "content": "x"}])

    output = runner.console.export_text()
    assert output.count("Thinking...") >= 2
