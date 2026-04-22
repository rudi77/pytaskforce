"""Wiki page domain model.

A wiki page is a single markdown document stored at a relative path under
the wiki root (e.g. ``entities/steuerberater-mueller``).  The directory
prefix encodes the page kind: ``entities``, ``preferences``, ``concepts``
(others are permitted but conventionally reserved for future use).

Pages are plain markdown with YAML frontmatter — no decay, no strength,
no associations.  Relevance comes from search ranking and index
membership, not from bookkeeping fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


@dataclass
class WikiPage:
    """A single wiki page.

    Attributes:
        name: Relative path without extension (e.g.
            ``entities/steuerberater-mueller``).  Acts as the page's ID.
        title: Human-readable title.
        body: Markdown content without the frontmatter block.
        tags: Optional keywords for discovery.  Kept deliberately small —
            the wiki's structure carries most of the organisation.
        created_at: When the page was first written.
        updated_at: When the page was last modified.
        extra: Any additional YAML frontmatter fields the agent wrote.
            Preserved on read so the model is lossless.
    """

    name: str
    title: str
    body: str
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        """Derive the page kind from the directory prefix."""
        parts = self.name.split("/", 1)
        return parts[0] if len(parts) > 1 else "other"

    def touch(self) -> None:
        """Update the page's updated_at timestamp."""
        self.updated_at = datetime.now(UTC)


def slugify(value: str) -> str:
    """Convert a free-form string into a filesystem-safe slug.

    Lowercases, replaces German umlauts with ASCII equivalents, collapses
    non-alphanumerics to single hyphens and trims leading/trailing
    hyphens.  Used to derive page filenames from titles.
    """
    lowered = value.strip().lower().translate(_UMLAUT_MAP)
    return _SLUG_PATTERN.sub("-", lowered).strip("-")
