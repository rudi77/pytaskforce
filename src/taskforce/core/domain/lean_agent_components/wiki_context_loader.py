"""Wiki context loader for optional index injection at session start.

Replaces ``MemoryContextLoader``.  When enabled, loads the wiki index
and optionally the top-N pages matching the current mission, then
returns a system-prompt section that tells the agent what pages exist
and hints at which are most relevant.

**Auto-injection is OFF by default** (issue #275). Wiki page names and
top-K body snippets used to land in every LLM call's system prompt,
which trips Azure / OpenAI content filters once the wiki accumulates
customer / invoice / PII-adjacent data — and the filter recovery in
ADR-025 cannot strip system-prompt content. Profiles that want the
old behaviour can re-enable it explicitly via ``wiki.context_injection``.

Two recommended replacement paths:

1. **On-demand lookup** — the agent calls ``wiki(action=search)`` /
   ``wiki(action=read_page)`` itself when it needs prior context. The
   tool description (see :mod:`wiki_tool`) already tells the agent to
   search at the start of a new topic.
2. **Memory sub-agent** — wire the ``memory_specialist`` sub-agent
   (``agents/butler/configs/custom/memory_specialist.yaml``) and let
   the master delegate recall queries to it. The specialist returns a
   structured JSON payload so raw page bodies never enter the master's
   context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from taskforce.core.domain.wiki_page import WikiPage
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.interfaces.wiki_store import WikiStoreProtocol


@dataclass
class WikiContextConfig:
    """Configuration for wiki context injection.

    Defaults are conservative (no auto-injection) — see module docstring
    for the rationale. Profiles that need backward-compatible behaviour
    set ``top_k_relevant`` and/or ``include_index`` explicitly.
    """

    max_total_chars: int = 2000
    top_k_relevant: int = 0
    include_index: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WikiContextConfig:
        return cls(
            max_total_chars=int(data.get("max_total_chars", 2000)),
            top_k_relevant=int(data.get("top_k_relevant", 0)),
            include_index=bool(data.get("include_index", False)),
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

        # ``top_k_relevant == 0`` means "do not include relevant-page
        # hooks at all" — must not silently coerce to 1 (issue #275).
        if mission and self._config.top_k_relevant > 0:
            relevant = await self._store.search(mission, limit=self._config.top_k_relevant)
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
