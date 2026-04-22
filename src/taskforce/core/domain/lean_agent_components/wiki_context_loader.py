"""Wiki context loader for automatic index injection at session start.

Replaces ``MemoryContextLoader``.  Loads the wiki index (always small)
and optionally the top-N pages matching the current mission, then
returns a system-prompt section that tells the agent what pages exist
and hints at which are most relevant.

The agent fetches page bodies on demand via ``wiki(action=read_page)``
— we deliberately do not inject full page content to keep the prompt
small and force the agent to consult the wiki actively.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from taskforce.core.domain.wiki_page import WikiPage
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.interfaces.wiki_store import WikiStoreProtocol


@dataclass
class WikiContextConfig:
    """Configuration for wiki context injection."""

    max_total_chars: int = 2000
    top_k_relevant: int = 5
    include_index: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WikiContextConfig:
        return cls(
            max_total_chars=int(data.get("max_total_chars", 2000)),
            top_k_relevant=int(data.get("top_k_relevant", 5)),
            include_index=bool(data.get("include_index", True)),
        )


class WikiContextLoader:
    """Inject the wiki index + relevant-page hints into the system prompt."""

    def __init__(
        self,
        wiki_store: WikiStoreProtocol,
        config: WikiContextConfig,
        logger: LoggerProtocol,
    ) -> None:
        self._store = wiki_store
        self._config = config
        self._logger = logger

    async def load_wiki_context(self, mission: str | None = None) -> str | None:
        sections: list[str] = []

        if self._config.include_index:
            index_text = (await self._store.read_index()).strip()
            if index_text:
                sections.append(index_text)

        if mission:
            relevant = await self._store.search(mission, limit=max(1, self._config.top_k_relevant))
            if relevant:
                sections.append(_render_relevant(relevant))

        if not sections:
            return None

        combined = "\n\n".join(sections)
        if len(combined) > self._config.max_total_chars:
            combined = combined[: self._config.max_total_chars].rstrip() + "\n…"

        self._logger.info(
            "wiki_context.loaded",
            chars=len(combined),
            sections=len(sections),
        )
        header = (
            "\n\n## WIKI INDEX (your long-term memory)\n"
            "Your persistent knowledge lives in a wiki. Search it before asking "
            "the user for info they may have shared before. Read full pages with "
            "`wiki(action=read_page, name=...)`.\n\n"
        )
        return header + combined


def _render_relevant(pages: list[WikiPage]) -> str:
    lines = ["### Potentially relevant pages"]
    for page in pages:
        hook = _first_line(page.body) or page.kind
        lines.append(f"- `{page.name}` — {page.title}: {hook[:140]}")
    return "\n".join(lines)


def _first_line(body: str) -> str:
    for raw in body.splitlines():
        line = raw.strip().lstrip("- ").lstrip("#").strip()
        if line:
            return line
    return ""
