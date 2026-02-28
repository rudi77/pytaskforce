from __future__ import annotations

from types import SimpleNamespace

from taskforce.application.context_display_service import ContextDisplayService


class DummySkillManager:
    def __init__(self) -> None:
        self.active_skill_name = "review"

    def get_active_instructions(self) -> str:
        return "Always include risks and mitigations."


class DummyAgent:
    def __init__(self) -> None:
        self.system_prompt = "Base system"
        self.skill_manager = DummySkillManager()
        self._openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read files",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        self.token_budgeter = SimpleNamespace(max_input_tokens=1000)

    def _build_system_prompt(self, mission=None, state=None, messages=None) -> str:
        return "Base system\n\n## CURRENT PLAN STATUS\nstep-1"


def test_build_snapshot_groups_context_sections() -> None:
    service = ContextDisplayService()
    agent = DummyAgent()
    state = {
        "conversation_history": [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
    }

    snapshot = service.build_snapshot(agent=agent, state=state, include_content=False)

    assert snapshot.max_tokens == 1000
    assert snapshot.total_tokens > 0
    assert len(snapshot.system_prompt) == 2
    assert len(snapshot.messages) == 2
    assert len(snapshot.skills) == 1
    assert len(snapshot.tools) == 1


def test_build_snapshot_includes_content_in_full_mode() -> None:
    service = ContextDisplayService()
    snapshot = service.build_snapshot(
        agent=DummyAgent(),
        state={"conversation_history": [{"role": "user", "content": "Hello world"}]},
        include_content=True,
    )

    assert snapshot.system_prompt[0].content == "Base system"
    assert snapshot.messages[0].content == "Hello world"
    assert "mitigations" in (snapshot.skills[0].content or "")
    assert "file_read" in (snapshot.tools[0].content or "")
