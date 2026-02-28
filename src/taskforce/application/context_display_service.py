"""Build a CLI-friendly snapshot of the current LLM context."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from taskforce.core.domain.token_budgeter import TokenBudgeter


@dataclass
class ContextItem:
    """A tokenized context fragment."""

    title: str
    tokens: int
    content: str | None = None


@dataclass
class ContextSnapshot:
    """Structured snapshot of everything sent to the LLM."""

    total_tokens: int
    max_tokens: int
    utilization_percent: float
    system_prompt: list[ContextItem] = field(default_factory=list)
    messages: list[ContextItem] = field(default_factory=list)
    skills: list[ContextItem] = field(default_factory=list)
    tools: list[ContextItem] = field(default_factory=list)


class ContextDisplayService:
    """Create context snapshots for the CLI `/context` command."""

    def __init__(self, chars_per_token: int = TokenBudgeter.CHARS_PER_TOKEN) -> None:
        self._chars_per_token = max(1, chars_per_token)

    def build_snapshot(
        self,
        *,
        agent: Any,
        state: dict[str, Any] | None,
        include_content: bool,
    ) -> ContextSnapshot:
        """Build a structured snapshot from the current agent state."""
        state = state or {}
        system_items = self._build_system_items(agent, state, include_content)
        message_items = self._build_message_items(state, include_content)
        skill_items = self._build_skill_items(agent, include_content)
        tool_items = self._build_tool_items(agent, include_content)

        total_tokens = sum(
            item.tokens for item in (*system_items, *message_items, *skill_items, *tool_items)
        )
        max_tokens = getattr(getattr(agent, "token_budgeter", None), "max_input_tokens", 100000)
        utilization = (total_tokens / max_tokens * 100.0) if max_tokens else 0.0

        return ContextSnapshot(
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            utilization_percent=utilization,
            system_prompt=system_items,
            messages=message_items,
            skills=skill_items,
            tools=tool_items,
        )

    def _build_system_items(
        self,
        agent: Any,
        state: dict[str, Any],
        include_content: bool,
    ) -> list[ContextItem]:
        base_prompt = str(getattr(agent, "system_prompt", "") or "")
        effective_prompt = str(agent._build_system_prompt(mission=None, state=state, messages=[]))

        return [
            ContextItem(
                title="Base system prompt",
                tokens=self._estimate_tokens(base_prompt),
                content=base_prompt if include_content else None,
            ),
            ContextItem(
                title="Effective system prompt",
                tokens=self._estimate_tokens(effective_prompt),
                content=effective_prompt if include_content else None,
            ),
        ]

    def _build_message_items(
        self,
        state: dict[str, Any],
        include_content: bool,
    ) -> list[ContextItem]:
        history = state.get("conversation_history", [])
        items: list[ContextItem] = []
        for idx, msg in enumerate(history, start=1):
            role = str(msg.get("role", "unknown"))
            content = str(msg.get("content", ""))
            items.append(
                ContextItem(
                    title=f"{idx}. {role}",
                    tokens=self._estimate_tokens(content),
                    content=content if include_content else None,
                )
            )
        return items

    def _build_skill_items(self, agent: Any, include_content: bool) -> list[ContextItem]:
        manager = getattr(agent, "skill_manager", None)
        if not manager or not getattr(manager, "active_skill_name", None):
            return []

        instructions = str(manager.get_active_instructions() or "")
        return [
            ContextItem(
                title=f"Active skill: {manager.active_skill_name}",
                tokens=self._estimate_tokens(instructions),
                content=instructions if include_content else None,
            )
        ]

    def _build_tool_items(self, agent: Any, include_content: bool) -> list[ContextItem]:
        openai_tools = list(getattr(agent, "_openai_tools", []) or [])
        items: list[ContextItem] = []
        for tool in openai_tools:
            function_data = tool.get("function", {})
            name = function_data.get("name") or tool.get("name") or "unknown"
            serialized = json.dumps(tool, ensure_ascii=False, default=str)
            items.append(
                ContextItem(
                    title=str(name),
                    tokens=self._estimate_tokens(serialized),
                    content=serialized if include_content else None,
                )
            )
        return items

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // self._chars_per_token)
