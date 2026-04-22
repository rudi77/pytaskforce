"""Protocol for wiki page persistence.

Replaces the record-based ``MemoryStoreProtocol``.  The wiki stores
markdown pages, not typed records — no kind enums, no scopes, no decay.
"""

from __future__ import annotations

from typing import Protocol

from taskforce.core.domain.wiki_page import WikiPage


class WikiStoreProtocol(Protocol):
    """Persistence interface for wiki pages."""

    async def list_pages(self) -> list[WikiPage]:
        """Return every page currently in the wiki."""
        ...

    async def get_page(self, name: str) -> WikiPage | None:
        """Load one page by its relative path (e.g. ``entities/foo``)."""
        ...

    async def search(self, query: str, limit: int = 5) -> list[WikiPage]:
        """Return the top-N pages ranked by relevance to ``query``."""
        ...

    async def write_page(self, page: WikiPage) -> WikiPage:
        """Create or fully overwrite a page.  Index is updated."""
        ...

    async def update_section(
        self,
        name: str,
        section: str,
        content: str,
        mode: str = "append",
    ) -> WikiPage | None:
        """Update one ``## section`` of a page.

        ``mode`` is either ``"append"`` (add to the section body) or
        ``"replace"`` (overwrite the section body).  Returns the updated
        page or ``None`` if the page does not exist.
        """
        ...

    async def delete_page(self, name: str) -> bool:
        """Remove a page.  Returns True if something was deleted."""
        ...

    async def append_log(self, entry: str) -> None:
        """Append an entry to the chronological ``log.md``."""
        ...

    async def read_index(self) -> str:
        """Return the raw ``index.md`` contents."""
        ...
