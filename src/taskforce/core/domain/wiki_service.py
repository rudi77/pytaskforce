"""Domain-level helpers for wiki operations.

Pure functions for index rendering, link extraction, and section
manipulation.  No I/O — the store does persistence, this module is
reusable by the tool, the lint service, and the context loader.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from taskforce.core.domain.wiki_page import WikiPage

_WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
_SECTION_HEADER_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

_KIND_ORDER = ("entities", "preferences", "concepts", "sources")


def extract_wiki_links(body: str) -> list[str]:
    """Return every ``[[target]]`` wiki-link found in the body."""
    return [match.group(1).strip() for match in _WIKI_LINK_PATTERN.finditer(body)]


def extract_sections(body: str) -> dict[str, tuple[int, int]]:
    """Map ``## section`` titles to their ``(start, end)`` character spans.

    The span covers the section header line through to (but not including)
    the next ``## `` header or the end of the body.  Used by
    ``apply_section_update`` to edit a single section in place.
    """
    sections: dict[str, tuple[int, int]] = {}
    headers = list(_SECTION_HEADER_PATTERN.finditer(body))
    for index, match in enumerate(headers):
        start = match.start()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(body)
        sections[match.group(1)] = (start, end)
    return sections


def apply_section_update(
    body: str,
    section: str,
    content: str,
    mode: str,
) -> str:
    """Return ``body`` with ``section`` updated or created.

    ``mode`` is ``"append"`` or ``"replace"``.  If the section does not
    exist, it is appended at the end of the body in both modes.  The
    leading ``## <section>`` header is managed automatically.
    """
    if mode not in {"append", "replace"}:
        raise ValueError(f"unsupported section mode: {mode!r}")
    sections = extract_sections(body)
    header = f"## {section}\n"
    new_content = content.rstrip() + "\n"
    if section not in sections:
        trimmed = body.rstrip() + ("\n\n" if body.strip() else "")
        return f"{trimmed}{header}\n{new_content}"
    start, end = sections[section]
    if mode == "replace":
        replacement = f"{header}\n{new_content}"
    else:
        existing = body[start:end].rstrip()
        replacement = f"{existing}\n{new_content}"
    trailing = body[end:]
    if trailing and not replacement.endswith("\n\n"):
        replacement = replacement.rstrip() + "\n\n"
    return body[:start] + replacement + trailing


def render_index(pages: Iterable[WikiPage]) -> str:
    """Render ``index.md`` from the current page set.

    Pages are grouped by kind (directory prefix) in a stable order.
    """
    by_kind: dict[str, list[WikiPage]] = {kind: [] for kind in _KIND_ORDER}
    for page in pages:
        by_kind.setdefault(page.kind, []).append(page)
    lines = [
        "# Wiki Index",
        "",
        "Catalog of all wiki pages. One line per page: `- [title](path) — one-line hook`.",
        "",
        "Maintained automatically by the `wiki` tool on every `write_page` / "
        "`update_page` / `delete_page`.",
        "",
    ]
    for kind, kind_pages in by_kind.items():
        lines.append(f"## {kind.capitalize()}")
        lines.append("")
        if not kind_pages:
            lines.append("_(no pages yet)_")
        else:
            for page in sorted(kind_pages, key=lambda p: p.name):
                hook = _index_hook(page)
                lines.append(f"- [{page.title}]({page.name}.md) — {hook}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _index_hook(page: WikiPage) -> str:
    """Return a one-line hook for the index entry.

    Prefers the first non-heading paragraph of the body; falls back to
    the tags, then to the page kind.
    """
    for raw_line in page.body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            line = line.lstrip("- ").strip()
        if line:
            return line[:140]
    if page.tags:
        return ", ".join(page.tags[:5])
    return page.kind
