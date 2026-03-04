"""Memory context loader for automatic memory injection at session start.

Loads relevant long-term memories from a ``MemoryStoreProtocol`` and
formats them as a system-prompt section so the agent can leverage past
experience without requiring an explicit ``memory`` tool call.

Selection is based on **effective memory strength** (combining recency,
access frequency, emotional valence, and importance) rather than a
simple recency sort.  This mirrors how human recall surfaces the most
*salient* memories first — not necessarily the newest ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from taskforce.core.domain.memory import (
    EmotionalValence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.interfaces.memory_store import MemoryStoreProtocol

# Kinds that are useful for automatic injection (excludes transient records).
_DEFAULT_KINDS: list[MemoryKind] = [
    MemoryKind.PREFERENCE,
    MemoryKind.LEARNED_FACT,
    MemoryKind.CONSOLIDATED,
    MemoryKind.LONG_TERM,
]

# Strength below which memories are considered too faded to inject.
_MIN_INJECTION_STRENGTH: float = 0.15

_EMOTION_ICONS: dict[EmotionalValence, str] = {
    EmotionalValence.NEUTRAL: "",
    EmotionalValence.POSITIVE: "(+)",
    EmotionalValence.NEGATIVE: "(-)",
    EmotionalValence.SURPRISE: "(!)",
    EmotionalValence.FRUSTRATION: "(?!)",
}


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

    Memories are selected by **effective strength** — a composite score
    that accounts for recency, access frequency, emotional encoding, and
    importance.  This ensures the agent's "working memory" is populated
    with the most salient knowledge, not just the most recent.

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

        now = datetime.now(UTC)

        # Filter out archived and very weak memories.
        active = [
            r
            for r in records
            if "archived" not in r.tags
            and r.effective_strength(now) >= _MIN_INJECTION_STRENGTH
        ]
        if not active:
            return None

        # Sort by effective strength (strongest / most salient first).
        active.sort(key=lambda r: r.effective_strength(now), reverse=True)
        active = active[: self._config.max_memories]

        # Reinforce injected memories (they are being "recalled").
        for record in active:
            record.reinforce(now)
            await self._store.update(record)

        lines: list[str] = []
        total_chars = 0
        for record in active:
            entry = self._format_record(record, now)
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
            "They are sorted by salience (strongest memories first). "
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

    def _format_record(self, record: MemoryRecord, now: datetime) -> str:
        """Format a single memory record as a bullet point.

        Includes a strength indicator and optional emotion icon to give
        the agent a sense of how reliable/vivid the memory is.
        """
        content = record.content
        max_len = self._config.max_chars_per_memory
        if len(content) > max_len:
            content = content[: max_len - 3] + "..."
        kind_label = record.kind.value.upper().replace("_", " ")
        eff = record.effective_strength(now)
        strength_bar = self._strength_indicator(eff)
        emotion = _EMOTION_ICONS.get(record.emotional_valence, "")
        emotion_suffix = f" {emotion}" if emotion else ""
        return f"- **[{kind_label}]** {strength_bar}{emotion_suffix} {content}"

    @staticmethod
    def _strength_indicator(strength: float) -> str:
        """Return a visual indicator of memory strength."""
        if strength >= 0.8:
            return "[vivid]"
        if strength >= 0.5:
            return "[clear]"
        if strength >= 0.3:
            return "[fading]"
        return "[dim]"
