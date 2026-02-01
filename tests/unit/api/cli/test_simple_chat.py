from __future__ import annotations

from dataclasses import dataclass

import pytest
from rich.console import Console

from taskforce.api.cli.simple_chat import SimpleChatRunner
from taskforce.core.domain.agent_definition import AgentDefinition, AgentSource


@dataclass
class DummySkillManager:
    skills: list[str]
    active: str | None = None

    @property
    def has_skills(self) -> bool:
        return bool(self.skills)

    @property
    def active_skill_name(self) -> str | None:
        return self.active

    def list_skills(self) -> list[str]:
        return list(self.skills)


class DummyAgent:
    def __init__(self, skill_manager: DummySkillManager | None = None) -> None:
        self.skill_manager = skill_manager
        self.closed = False

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
    def __init__(self, skills: list[str]) -> None:
        self._skills = skills

    def list_skills(self) -> list[str]:
        return list(self._skills)


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


def test_list_skills_uses_agent_skill_manager() -> None:
    skill_manager = DummySkillManager(skills=["invoice-processing"], active="invoice-processing")
    runner = _build_runner(DummyAgent(skill_manager=skill_manager))

    runner._list_skills()

    output = runner.console.export_text()
    assert "invoice-processing" in output
    assert "active: invoice-processing" in output


def test_list_skills_falls_back_to_skill_service(monkeypatch) -> None:
    runner = _build_runner(DummyAgent())

    def _fake_skill_service() -> DummySkillService:
        return DummySkillService(["pdf-review"])

    monkeypatch.setattr(
        "taskforce.api.cli.simple_chat.get_skill_service",
        _fake_skill_service,
    )

    runner._list_skills()

    output = runner.console.export_text()
    assert "pdf-review" in output


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
