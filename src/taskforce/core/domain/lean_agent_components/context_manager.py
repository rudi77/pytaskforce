"""ContextManager — single source of truth for the full LLM context.

Coordinates MessageHistoryManager, TokenBudgeter, and tool definitions
to provide a unified view of what is sent to the LLM.  Owns the mutable
messages list and exposes snapshot generation for CLI commands.
"""

from __future__ import annotations

import json
from typing import Any

from taskforce.core.domain.lean_agent_components.message_history_manager import (
    MessageHistoryManager,
)
from taskforce.core.domain.token_budgeter import TokenBudgeter
from taskforce.core.interfaces.context_manager import ContextItem, ContextSnapshot
from taskforce.core.interfaces.logging import LoggerProtocol


class ContextManager:
    """Single source of truth for the full LLM context sent to the model.

    Holds the mutable messages list and delegates heavy lifting to
    existing components (MessageHistoryManager, TokenBudgeter).
    """

    def __init__(
        self,
        *,
        message_history_manager: MessageHistoryManager,
        openai_tools: list[dict[str, Any]],
        token_budgeter: TokenBudgeter,
        logger: LoggerProtocol,
        chars_per_token: int = TokenBudgeter.CHARS_PER_TOKEN,
    ) -> None:
        self._history_manager = message_history_manager
        self._openai_tools = openai_tools
        self._token_budgeter = token_budgeter
        self._logger = logger
        self._chars_per_token = max(1, chars_per_token)
        self._messages: list[dict[str, Any]] = []
        self._last_system_prompt: str = ""
        self._initialized = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Current messages list (same mutable object throughout execution)."""
        return self._messages

    @property
    def tools(self) -> list[dict[str, Any]]:
        """OpenAI-format tool definitions."""
        return self._openai_tools

    @property
    def system_prompt(self) -> str:
        """The most recently set system prompt string."""
        return self._last_system_prompt

    @property
    def is_initialized(self) -> bool:
        """Whether initialize() or restore() has been called."""
        return self._initialized

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(
        self,
        mission: str,
        state: dict[str, Any],
        base_system_prompt: str,
    ) -> None:
        """Build the initial messages list from mission and state.

        Delegates to MessageHistoryManager.build_initial_messages().

        Args:
            mission: The user mission text.
            state: Session state dict (contains conversation_history, answers).
            base_system_prompt: Base system prompt before dynamic injection.
        """
        new_messages = self._history_manager.build_initial_messages(
            mission=mission,
            state=state,
            base_system_prompt=base_system_prompt,
        )
        self._messages.clear()
        self._messages.extend(new_messages)
        self._last_system_prompt = base_system_prompt
        self._initialized = True
        self._logger.debug("context_initialized", message_count=len(self._messages))

    def restore(self, messages: list[dict[str, Any]]) -> None:
        """Restore messages from a resume context (ask_user pause).

        Args:
            messages: The full message list from a paused execution.
        """
        self._messages.clear()
        self._messages.extend(messages)
        if self._messages and self._messages[0].get("role") == "system":
            self._last_system_prompt = str(self._messages[0].get("content", ""))
        self._initialized = True
        self._logger.debug("context_restored", message_count=len(self._messages))

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def set_system_prompt(self, prompt: str) -> None:
        """Overwrite messages[0] with a fresh system prompt.

        Args:
            prompt: The fully composed system prompt string.
        """
        if not self._messages:
            self._messages.append({"role": "system", "content": prompt})
        else:
            self._messages[0] = {"role": "system", "content": prompt}
        self._last_system_prompt = prompt

    def append_message(self, message: dict[str, Any]) -> None:
        """Append a single message to the context.

        Args:
            message: A message dict (user, assistant, tool, etc.).
        """
        self._messages.append(message)

    # ------------------------------------------------------------------
    # Budget management
    # ------------------------------------------------------------------

    async def compress(self) -> None:
        """Run message compression if budget thresholds are exceeded.

        Mutates the internal messages list in-place so all external
        references remain valid.
        """
        new_messages = await self._history_manager.compress_messages(self._messages)
        if new_messages is not self._messages:
            self._messages.clear()
            self._messages.extend(new_messages)

    def preflight_check(self) -> None:
        """Run emergency budget check and truncation in-place."""
        new_messages = self._history_manager.preflight_budget_check(self._messages)
        if new_messages is not self._messages:
            self._messages.clear()
            self._messages.extend(new_messages)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(
        self,
        *,
        include_content: bool = False,
        skill_manager: Any | None = None,
        memory_context: str | None = None,
    ) -> ContextSnapshot:
        """Build a structured snapshot for CLI /context and /tree commands.

        Args:
            include_content: Whether to include full content in items.
            skill_manager: Optional SkillManager for skill section.
            memory_context: Optional cached memory context string
                (injected into system prompt by Agent).

        Returns:
            A frozen ContextSnapshot with all context sections.
        """
        system_items = self._build_system_items(include_content)
        message_items = self._build_message_items(include_content)
        memory_items = self._build_memory_items(memory_context, include_content)
        skill_items = self._build_skill_items(skill_manager, include_content)
        tool_items = self._build_tool_items(include_content)

        total_tokens = sum(
            item.tokens
            for item in (
                *system_items, *message_items, *memory_items,
                *skill_items, *tool_items,
            )
        )
        max_tokens = self._token_budgeter.max_input_tokens
        utilization = (total_tokens / max_tokens * 100.0) if max_tokens else 0.0

        return ContextSnapshot(
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            utilization_percent=utilization,
            system_prompt=system_items,
            messages=message_items,
            memory=memory_items,
            skills=skill_items,
            tools=tool_items,
        )

    # ------------------------------------------------------------------
    # Snapshot builders (private)
    # ------------------------------------------------------------------

    def _build_system_items(self, include_content: bool) -> list[ContextItem]:
        """Build system prompt section items."""
        prompt = self._last_system_prompt
        return [
            ContextItem(
                title="System prompt",
                tokens=self._estimate_tokens(prompt),
                content=prompt if include_content else None,
            ),
        ]

    def _build_memory_items(
        self, memory_context: str | None, include_content: bool,
    ) -> list[ContextItem]:
        """Build memory section items.

        Memory is injected into the system prompt as a text section.
        This extracts it for separate display in the tree.

        Args:
            memory_context: Cached memory context string, or None.
            include_content: Whether to include full content in items.
        """
        if not memory_context:
            return []
        return [
            ContextItem(
                title="Long-term memory",
                tokens=self._estimate_tokens(memory_context),
                content=memory_context if include_content else None,
            ),
        ]

    def _build_message_items(self, include_content: bool) -> list[ContextItem]:
        """Build message items from the full LLM message list.

        Includes user, assistant (with tool_calls), and tool result messages.
        Skips the system message (shown separately in system_prompt section).

        Args:
            include_content: Whether to include full content in items.
        """
        items: list[ContextItem] = []
        for idx, msg in enumerate(self._messages, start=1):
            role = str(msg.get("role", "unknown"))
            if role == "system":
                continue

            tool_calls = msg.get("tool_calls")
            tool_name = msg.get("name") or msg.get("tool_name", "")
            content = str(msg.get("content") or "")

            if role == "assistant" and tool_calls:
                item = self._build_tool_call_item(idx, tool_calls, include_content)
            elif role == "tool":
                item = self._build_tool_result_item(
                    idx, str(tool_name), content, include_content,
                )
            else:
                item = ContextItem(
                    title=f"{idx}. {role}",
                    tokens=self._estimate_tokens(content),
                    content=content if include_content else None,
                )
            items.append(item)
        return items

    def _build_tool_call_item(
        self,
        idx: int,
        tool_calls: list[dict[str, Any]],
        include_content: bool,
    ) -> ContextItem:
        """Build a ContextItem for an assistant tool_call message."""
        call_names = [
            tc.get("function", {}).get("name", "?") for tc in tool_calls
        ]
        title = f"{idx}. assistant [tool_call: {', '.join(call_names)}]"
        serialized = json.dumps(tool_calls, ensure_ascii=False, default=str)
        return ContextItem(
            title=title,
            tokens=self._estimate_tokens(serialized),
            content=serialized if include_content else None,
        )

    def _build_tool_result_item(
        self,
        idx: int,
        tool_name: str,
        content: str,
        include_content: bool,
    ) -> ContextItem:
        """Build a ContextItem for a tool result message."""
        label = f"[{tool_name}]" if tool_name else ""
        return ContextItem(
            title=f"{idx}. tool {label}".rstrip(),
            tokens=self._estimate_tokens(content),
            content=content if include_content else None,
        )

    def _build_skill_items(
        self, skill_manager: Any | None, include_content: bool,
    ) -> list[ContextItem]:
        """Build skill section items from skill manager."""
        if not skill_manager:
            return []

        items: list[ContextItem] = []
        active_name = getattr(skill_manager, "active_skill_name", None)

        if active_name:
            instructions = str(
                skill_manager.get_active_instructions() or "",
            )
            items.append(
                ContextItem(
                    title=f"Active skill: {active_name}",
                    tokens=self._estimate_tokens(instructions),
                    content=instructions if include_content else None,
                )
            )

        available = (
            skill_manager.list_skills()
            if hasattr(skill_manager, "list_skills")
            else []
        )
        for name in available:
            if name == active_name:
                continue
            skill = (
                skill_manager.get_skill(name)
                if hasattr(skill_manager, "get_skill")
                else None
            )
            desc = getattr(skill, "description", "") or "" if skill else ""
            items.append(
                ContextItem(
                    title=f"Loaded: {name}",
                    tokens=0,  # Not injected into context until activated
                    content=desc if include_content else None,
                )
            )

        return items

    def _build_tool_items(self, include_content: bool) -> list[ContextItem]:
        """Build tool definition section items."""
        items: list[ContextItem] = []
        for tool in self._openai_tools:
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
        """Heuristic token estimation based on character count."""
        if not text:
            return 0
        return max(1, len(text) // self._chars_per_token)
