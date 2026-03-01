"""Memory context loader for automatic memory injection at session start.

Loads relevant long-term memories from a ``MemoryStoreProtocol`` and
formats them as a system-prompt section so the agent can leverage past
experience without requiring an explicit ``memory`` tool call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol

# Kinds that are useful for automatic injection (excludes transient records).
_DEFAULT_KINDS: list[MemoryKind] = [
    MemoryKind.PREFERENCE,
    MemoryKind.LEARNED_FACT,
    MemoryKind.CONSOLIDATED,
    MemoryKind.LONG_TERM,
]


@dataclass
class MemoryContextConfig:
    """Configuration for memory context injection.

    Controls which memories are loaded and how much budget they may consume
    inside the system prompt.
    """

    max_memories: int = 20
    max_chars_per_memory: int = 500
    max_total_chars: int = 3000
    kinds: list[MemoryKind] = field(default_factory=lambda: list(_DEFAULT_KINDS))
    scope: MemoryScope = MemoryScope.USER

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryContextConfig:
        """Create config from a YAML dictionary.

        Expected keys (all optional):
            max_memories, max_chars_per_memory, max_total_chars,
            kinds (list of kind strings), scope (string).
        """
        kinds = data.get("kinds")
        parsed_kinds = (
            [MemoryKind(k) for k in kinds] if kinds else list(_DEFAULT_KINDS)
        )
        scope_raw = data.get("scope")
        parsed_scope = MemoryScope(scope_raw) if scope_raw else MemoryScope.USER
        return cls(
            max_memories=data.get("max_memories", 20),
            max_chars_per_memory=data.get("max_chars_per_memory", 500),
            max_total_chars=data.get("max_total_chars", 3000),
            kinds=parsed_kinds,
            scope=parsed_scope,
        )


class MemoryContextLoader:
    """Load and format long-term memories for system-prompt injection.

    Usage::

        loader = MemoryContextLoader(memory_store, config, logger)
        section = await loader.load_memory_context()
        if section:
            system_prompt += section
    """

    def __init__(
        self,
        memory_store: MemoryStoreProtocol,
        config: MemoryContextConfig,
        logger: LoggerProtocol,
    ) -> None:
        self._store = memory_store
        self._config = config
        self._logger = logger

    async def load_memory_context(self) -> str | None:
        """Load memories and return a formatted prompt section.

        Returns:
            A Markdown section string starting with ``## LONG-TERM MEMORY``,
            or ``None`` when no relevant records exist.
        """
        records = await self._fetch_records()
        if not records:
            return None

        records.sort(key=lambda r: r.updated_at, reverse=True)
        records = records[: self._config.max_memories]

        lines: list[str] = []
        total_chars = 0
        for record in records:
            entry = self._format_record(record)
            if total_chars + len(entry) > self._config.max_total_chars:
                break
            lines.append(entry)
            total_chars += len(entry)

        if not lines:
            return None

        self._logger.info(
            "memory_context.loaded",
            count=len(lines),
            total_chars=total_chars,
        )
        header = (
            "\n\n## LONG-TERM MEMORY\n"
            "The following memories were automatically loaded from previous sessions. "
            "Use them to personalise your responses and avoid repeating past mistakes.\n\n"
        )
        return header + "\n".join(lines)

    async def _fetch_records(self) -> list[MemoryRecord]:
        """Fetch records for all configured kinds."""
        all_records: list[MemoryRecord] = []
        for kind in self._config.kinds:
            records = await self._store.list(scope=self._config.scope, kind=kind)
            all_records.extend(records)
        return all_records

    def _format_record(self, record: MemoryRecord) -> str:
        """Format a single memory record as a bullet point."""
        content = record.content
        max_len = self._config.max_chars_per_memory
        if len(content) > max_len:
            content = content[: max_len - 3] + "..."
        kind_label = record.kind.value.upper().replace("_", " ")
        return f"- **[{kind_label}]** {content}"
