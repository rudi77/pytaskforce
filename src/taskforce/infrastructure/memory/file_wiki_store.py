"""File-backed wiki store.

One markdown file per page, stored at ``<root>/<kind>/<slug>.md``.  The
directory prefix encodes the page kind (``entities``, ``preferences``,
``concepts``, ...).  ``index.md`` is regenerated after every mutation;
``log.md`` is append-only.

The store performs no caching — wikis are expected to stay small
(~hundreds of pages) and on-demand file I/O is cheap at that scale.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from taskforce.core.domain.wiki_page import WikiPage
from taskforce.core.domain.wiki_service import apply_section_update, render_index
from taskforce.core.interfaces.wiki_store import WikiStoreProtocol
from taskforce.core.utils.atomic_io import atomic_write_text

logger = structlog.get_logger(__name__)

_FRONTMATTER_DELIM = "---"
_INDEX_FILE = "index.md"
_LOG_FILE = "log.md"
_LOG_FORMAT = "## [%Y-%m-%d %H:%M]"
# Lock key for append_log — contains ":" so it can never collide with a
# real page name (``_validate_name`` rejects names containing ":").
_LOG_LOCK_KEY = "::log"


class FileWikiStore(WikiStoreProtocol):
    """Markdown-file-based wiki store.

    Args:
        base_dir: Wiki root.  Created if it does not exist.
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._root = Path(base_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        # Per-page locks serialise read-modify-write mutations so a
        # concurrent update cannot clobber another writer's change.
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()
        self._index_lock = asyncio.Lock()

    async def _get_lock(self, key: str) -> asyncio.Lock:
        """Return the lock for *key* (a page name or ``_LOG_LOCK_KEY``)."""
        async with self._locks_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    # -- reading ----------------------------------------------------------

    async def list_pages(self) -> list[WikiPage]:
        pages: list[WikiPage] = []
        for path in sorted(self._root.rglob("*.md")):
            if path.name in {_INDEX_FILE, _LOG_FILE}:
                continue
            page = self._read_file(path)
            if page is not None:
                pages.append(page)
        return pages

    async def get_page(self, name: str) -> WikiPage | None:
        path = self._page_path(name)
        if not path.exists():
            return None
        return self._read_file(path)

    async def search(self, query: str, limit: int = 5) -> list[WikiPage]:
        query_words = query.lower().split()
        if not query_words:
            return []
        scored: list[tuple[float, WikiPage]] = []
        for page in await self.list_pages():
            haystack = f"{page.title}\n{page.body}\n{' '.join(page.tags)}\n{page.name}".lower()
            hits = sum(1 for w in query_words if _word_matches(w, haystack))
            if hits == 0:
                continue
            title_haystack = f"{page.title}\n{page.name}".lower()
            title_hits = sum(1 for w in query_words if _word_matches(w, title_haystack))
            score = hits / len(query_words) + title_hits * 0.5
            scored.append((score, page))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [page for _, page in scored[:limit]]

    async def read_index(self) -> str:
        index_path = self._root / _INDEX_FILE
        if not index_path.exists():
            return ""
        return index_path.read_text(encoding="utf-8")

    # -- writing ----------------------------------------------------------

    async def write_page(self, page: WikiPage) -> WikiPage:
        self._validate_name(page.name)
        path = self._page_path(page.name)
        async with await self._get_lock(page.name):
            if path.exists():
                existing = self._read_file(path)
                if existing is not None:
                    page.created_at = existing.created_at
            page.touch()
            path.parent.mkdir(parents=True, exist_ok=True)
            await atomic_write_text(path, self._serialise(page))
        await self._refresh_index()
        logger.info("wiki.write_page", name=page.name)
        return page

    async def update_section(
        self,
        name: str,
        section: str,
        content: str,
        mode: str = "append",
    ) -> WikiPage | None:
        # The read (get_page) and the write must be one critical section,
        # otherwise two concurrent section updates each read the same
        # page and the second write silently drops the first's change.
        async with await self._get_lock(name):
            page = await self.get_page(name)
            if page is None:
                return None
            page.body = apply_section_update(page.body, section, content, mode)
            page.touch()
            await atomic_write_text(self._page_path(name), self._serialise(page))
        await self._refresh_index()
        logger.info("wiki.update_section", name=name, section=section, mode=mode)
        return page

    async def delete_page(self, name: str) -> bool:
        path = self._page_path(name)
        async with await self._get_lock(name):
            if not path.exists():
                return False
            path.unlink()
        await self._refresh_index()
        logger.info("wiki.delete_page", name=name)
        return True

    async def append_log(self, entry: str) -> None:
        log_path = self._root / _LOG_FILE
        header = datetime.now(UTC).strftime(_LOG_FORMAT)
        line = f"{header} {entry.strip()}\n"
        async with await self._get_lock(_LOG_LOCK_KEY):
            if log_path.exists():
                existing = log_path.read_text(encoding="utf-8")
                if not existing.endswith("\n"):
                    existing += "\n"
                await atomic_write_text(log_path, existing + line)
            else:
                await atomic_write_text(log_path, f"# Wiki Log\n\n{line}")

    # -- internals --------------------------------------------------------

    def _page_path(self, name: str) -> Path:
        return self._root / f"{name}.md"

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name:
            raise ValueError(f"invalid page name: {name!r}")
        if name in {"index", "log"}:
            raise ValueError(f"reserved page name: {name!r}")
        # Normalise both Unix and Windows separators before traversal checks
        # so ``..\escape`` is caught on every platform.
        normalised = name.replace("\\", "/")
        if normalised.startswith("/"):
            raise ValueError(f"invalid page name: {name!r}")
        segments = normalised.split("/")
        if ".." in segments or any(":" in seg for seg in segments):
            raise ValueError(f"invalid page name: {name!r}")

    def _read_file(self, path: Path) -> WikiPage | None:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        frontmatter, body = _split_frontmatter(raw)
        try:
            relative = path.relative_to(self._root).with_suffix("")
        except ValueError:
            return None
        name = relative.as_posix()
        title = str(frontmatter.get("title") or name.rsplit("/", 1)[-1])
        tags_raw = frontmatter.get("tags") or []
        tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
        created_at = _parse_ts(frontmatter.get("created_at")) or datetime.now(UTC)
        updated_at = _parse_ts(frontmatter.get("updated_at")) or created_at
        extra = {
            k: v
            for k, v in frontmatter.items()
            if k not in {"title", "tags", "created_at", "updated_at"}
        }
        return WikiPage(
            name=name,
            title=title,
            body=body,
            tags=tags,
            created_at=created_at,
            updated_at=updated_at,
            extra=extra,
        )

    @staticmethod
    def _serialise(page: WikiPage) -> str:
        frontmatter: dict[str, Any] = {
            "title": page.title,
            "tags": list(page.tags),
            "created_at": page.created_at.isoformat(),
            "updated_at": page.updated_at.isoformat(),
        }
        for key, value in page.extra.items():
            frontmatter.setdefault(key, value)
        yaml_block = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
        body = page.body.rstrip() + "\n"
        return f"{_FRONTMATTER_DELIM}\n{yaml_block}\n{_FRONTMATTER_DELIM}\n\n{body}"

    async def _refresh_index(self) -> None:
        # Serialised so two page mutations cannot race on index.md.
        async with self._index_lock:
            pages = await self.list_pages()
            await atomic_write_text(self._root / _INDEX_FILE, render_index(pages))


def _word_matches(word: str, haystack: str) -> bool:
    """Loose word match: substring, or prefix (minus last char) for longer words."""
    if word in haystack:
        return True
    if len(word) > 4:
        return word[:-1] in haystack
    return False


def _split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Split ``---\\n<yaml>\\n---\\n<body>`` into (frontmatter, body)."""
    stripped = raw.lstrip()
    if not stripped.startswith(_FRONTMATTER_DELIM):
        return {}, raw
    after_first = stripped[len(_FRONTMATTER_DELIM) :].lstrip("\r\n")
    closing = after_first.find(f"\n{_FRONTMATTER_DELIM}")
    if closing < 0:
        return {}, raw
    yaml_block = after_first[:closing]
    body = after_first[closing + len(_FRONTMATTER_DELIM) + 1 :].lstrip("\r\n")
    try:
        parsed = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError:
        return {}, raw
    if not isinstance(parsed, dict):
        return {}, raw
    return parsed, body


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None
