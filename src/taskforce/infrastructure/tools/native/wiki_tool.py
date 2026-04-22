"""Wiki tool — markdown knowledge base for agents.

Replaces the record-based ``memory`` tool.  The agent operates on a
directory of markdown pages (one per topic) rather than on a stream of
typed records.  Actions are wiki-native: list, read, search, write,
update a section, delete, log.

Pages live under ``.taskforce/memory/wiki/`` by convention, organised
into ``entities/``, ``preferences/`` and ``concepts/`` subdirectories.
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.domain.wiki_page import WikiPage
from taskforce.core.interfaces.wiki_store import WikiStoreProtocol
from taskforce.infrastructure.tools.base_tool import BaseTool

logger = structlog.get_logger(__name__)

_VALID_ACTIONS = (
    "list_pages",
    "read_page",
    "search",
    "write_page",
    "update_page",
    "delete_page",
    "log",
)


class WikiTool(BaseTool):
    """Expose the wiki store to agents as a single ``wiki`` tool.

    The agent chooses an action (``list_pages``, ``read_page``,
    ``search``, ``write_page``, ``update_page``, ``delete_page``, ``log``)
    and supplies the matching parameters.  The tool normalises inputs,
    calls the store, and returns structured results.
    """

    tool_name = "wiki"
    tool_description = (
        "Personal wiki for long-term memory. Markdown pages, one per topic, "
        "grouped into entities/preferences/concepts. Use 'search' at the start "
        "of a new topic to recall prior info, 'read_page' to load a full page, "
        "'write_page' to create a new page, 'update_page' to edit a single "
        "section, and 'log' to record an event. Always search before writing to "
        "avoid duplicates — prefer updating the matching page instead."
    )
    tool_parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_VALID_ACTIONS),
                "description": "Which wiki operation to perform.",
            },
            "name": {
                "type": "string",
                "description": (
                    "Page path without extension, e.g. " "'entities/steuerberater-mueller'."
                ),
            },
            "title": {
                "type": "string",
                "description": "Human-readable page title (used by write_page).",
            },
            "content": {
                "type": "string",
                "description": ("Markdown body (write_page) or section content (update_page)."),
            },
            "section": {
                "type": "string",
                "description": ("Section heading (without '##') to edit in update_page."),
            },
            "mode": {
                "type": "string",
                "enum": ["append", "replace"],
                "description": "How update_page should handle the existing section.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional keywords (write_page only).",
            },
            "query": {
                "type": "string",
                "description": "Search query (search only).",
            },
            "limit": {
                "type": "integer",
                "description": "Max number of search results (default 5).",
            },
            "entry": {
                "type": "string",
                "description": "One-line log message (log only).",
            },
        },
        "required": ["action"],
    }
    tool_supports_parallelism = False

    def __init__(
        self,
        store: WikiStoreProtocol | None = None,
        store_dir: str | None = None,
    ) -> None:
        if store is not None:
            self._store = store
            return
        from taskforce.infrastructure.memory.file_wiki_store import FileWikiStore

        self._store = FileWikiStore(store_dir or ".taskforce/memory/wiki")

    async def _execute(self, **kwargs: Any) -> dict[str, Any]:
        action = kwargs.get("action")
        if action == "list_pages":
            return await self._list_pages()
        if action == "read_page":
            return await self._read_page(kwargs.get("name"))
        if action == "search":
            return await self._search(kwargs.get("query"), kwargs.get("limit", 5))
        if action == "write_page":
            return await self._write_page(
                kwargs.get("name"),
                kwargs.get("title"),
                kwargs.get("content"),
                kwargs.get("tags") or [],
            )
        if action == "update_page":
            return await self._update_page(
                kwargs.get("name"),
                kwargs.get("section"),
                kwargs.get("content"),
                kwargs.get("mode", "append"),
            )
        if action == "delete_page":
            return await self._delete_page(kwargs.get("name"))
        if action == "log":
            return await self._log(kwargs.get("entry"))
        return {
            "success": False,
            "error": f"unknown action: {action!r}",
        }

    # -- action handlers --------------------------------------------------

    async def _list_pages(self) -> dict[str, Any]:
        pages = await self._store.list_pages()
        return {
            "success": True,
            "count": len(pages),
            "pages": [_summarise(p) for p in pages],
        }

    async def _read_page(self, name: str | None) -> dict[str, Any]:
        if not name:
            return _missing("name")
        page = await self._store.get_page(name)
        if page is None:
            return {"success": False, "error": f"page not found: {name}"}
        return {"success": True, "page": _full(page)}

    async def _search(self, query: str | None, limit: int) -> dict[str, Any]:
        if not query:
            return _missing("query")
        results = await self._store.search(query, limit=max(1, int(limit)))
        return {
            "success": True,
            "count": len(results),
            "results": [_summarise(p) for p in results],
        }

    async def _write_page(
        self,
        name: str | None,
        title: str | None,
        content: str | None,
        tags: list[str],
    ) -> dict[str, Any]:
        if not name:
            return _missing("name")
        if not title:
            return _missing("title")
        if content is None:
            return _missing("content")
        page = WikiPage(name=name, title=title, body=content, tags=list(tags))
        saved = await self._store.write_page(page)
        return {"success": True, "page": _summarise(saved)}

    async def _update_page(
        self,
        name: str | None,
        section: str | None,
        content: str | None,
        mode: str,
    ) -> dict[str, Any]:
        if not name:
            return _missing("name")
        if not section:
            return _missing("section")
        if content is None:
            return _missing("content")
        page = await self._store.update_section(name, section, content, mode)
        if page is None:
            return {"success": False, "error": f"page not found: {name}"}
        return {"success": True, "page": _summarise(page)}

    async def _delete_page(self, name: str | None) -> dict[str, Any]:
        if not name:
            return _missing("name")
        deleted = await self._store.delete_page(name)
        return {"success": deleted, "name": name}

    async def _log(self, entry: str | None) -> dict[str, Any]:
        if not entry:
            return _missing("entry")
        await self._store.append_log(entry)
        return {"success": True}


def _summarise(page: WikiPage) -> dict[str, Any]:
    return {
        "name": page.name,
        "title": page.title,
        "kind": page.kind,
        "tags": list(page.tags),
        "updated_at": page.updated_at.isoformat(),
    }


def _full(page: WikiPage) -> dict[str, Any]:
    data = _summarise(page)
    data["body"] = page.body
    data["created_at"] = page.created_at.isoformat()
    return data


def _missing(param: str) -> dict[str, Any]:
    return {"success": False, "error": f"missing required parameter: {param}"}
