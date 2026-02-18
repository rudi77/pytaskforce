"""Memory domain models and enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class MemoryScope(str, Enum):
    """Scopes for memory records."""

    SESSION = "session"
    PROFILE = "profile"
    USER = "user"
    ORG = "org"


class MemoryKind(str, Enum):
    """Kinds of memory records."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    TOOL_RESULT = "tool_result"
    EPIC_LOG = "epic_log"
    PREFERENCE = "preference"
    LEARNED_FACT = "learned_fact"


@dataclass
class MemoryRecord:
    """A single memory record."""

    scope: MemoryScope
    kind: MemoryKind
    content: str
    id: str = field(default_factory=lambda: uuid4().hex)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        """Update the record's updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)
