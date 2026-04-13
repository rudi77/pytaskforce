"""Protocol and value objects for the unified LLM context manager."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ContextItem:
    """A tokenized context fragment for display/inspection."""

    title: str
    tokens: int
    content: str | None = None


@dataclass(frozen=True)
class ContextSnapshot:
    """Structured snapshot of everything sent to the LLM."""

    total_tokens: int
    max_tokens: int
    utilization_percent: float
    system_prompt: list[ContextItem] = field(default_factory=list)
    messages: list[ContextItem] = field(default_factory=list)
    memory: list[ContextItem] = field(default_factory=list)
    skills: list[ContextItem] = field(default_factory=list)
    tools: list[ContextItem] = field(default_factory=list)


class ContextManagerProtocol(Protocol):
    """Single source of truth for the full LLM context sent to the model.

    Owns the mutable messages list and coordinates initialization,
    system prompt rebuilds, compression, budget checks, and snapshot
    generation.  Delegates heavy lifting to existing components
    (MessageHistoryManager, TokenBudgeter) rather than reimplementing.
    """

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Current messages list (same mutable object throughout execution)."""
        ...

    @property
    def tools(self) -> list[dict[str, Any]]:
        """OpenAI-format tool definitions."""
        ...

    @property
    def system_prompt(self) -> str:
        """The most recently set system prompt string."""
        ...

    @property
    def is_initialized(self) -> bool:
        """Whether initialize() or restore() has been called."""
        ...

    def initialize(
        self,
        mission: str,
        state: dict[str, Any],
        base_system_prompt: str,
    ) -> None:
        """Build the initial messages list from mission and state.

        Delegates to MessageHistoryManager.build_initial_messages().
        """
        ...

    def restore(self, messages: list[dict[str, Any]]) -> None:
        """Restore messages from a resume context (ask_user pause)."""
        ...

    def set_system_prompt(self, prompt: str) -> None:
        """Overwrite messages[0] with a fresh system prompt."""
        ...

    def append_message(self, message: dict[str, Any]) -> None:
        """Append a single message (tool result, nudge, circuit breaker, etc.)."""
        ...

    async def compress(self) -> None:
        """Run message compression if budget thresholds are exceeded.

        Mutates the internal messages list in-place so all external
        references remain valid.
        """
        ...

    def preflight_check(self) -> None:
        """Run emergency budget check and truncation in-place."""
        ...

    def snapshot(
        self,
        *,
        include_content: bool = False,
        skill_manager: Any | None = None,
        memory_context: str | None = None,
    ) -> ContextSnapshot:
        """Build a structured snapshot for CLI /context and /tree commands."""
        ...
