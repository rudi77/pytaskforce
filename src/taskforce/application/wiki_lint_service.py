"""Wiki lint — health checks over a wiki store.

Manual trigger only (no scheduler).  Detects:

* **orphans** — pages not referenced by any other page's ``[[wiki-links]]``
* **duplicate titles** — two pages with the same title but different names
* **broken links** — ``[[name]]`` references that don't resolve to a page

Replaces the old, disruptive consolidation + dream pipeline: a user
runs ``taskforce wiki lint`` when they want to inspect the state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from taskforce.core.domain.wiki_service import extract_wiki_links
from taskforce.core.interfaces.wiki_store import WikiStoreProtocol


@dataclass(frozen=True)
class LintIssue:
    """One actionable finding from a lint pass."""

    kind: str  # "orphan" | "duplicate_title" | "broken_link"
    message: str


@dataclass
class LintReport:
    """Result of a lint pass."""

    issues: list[LintIssue] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.issues


async def lint_wiki(store: WikiStoreProtocol) -> LintReport:
    """Scan the wiki and return a :class:`LintReport`."""
    pages = await store.list_pages()
    report = LintReport()

    by_name = {page.name for page in pages}
    inbound: dict[str, int] = dict.fromkeys(by_name, 0)

    # Scan outbound links.
    for page in pages:
        for target in extract_wiki_links(page.body):
            if target in by_name:
                inbound[target] = inbound.get(target, 0) + 1
            else:
                report.issues.append(
                    LintIssue(
                        kind="broken_link",
                        message=f"{page.name} links to unknown page [[{target}]]",
                    )
                )

    # Orphans — pages with zero inbound links.  Exclude pages in the root
    # ``entities/preferences/concepts`` hub pages if/when they exist.
    for name, count in inbound.items():
        if count == 0:
            report.issues.append(LintIssue(kind="orphan", message=f"{name} has no inbound links"))

    # Duplicate titles across different page names.
    seen_titles: dict[str, str] = {}
    for page in pages:
        prior = seen_titles.get(page.title)
        if prior and prior != page.name:
            report.issues.append(
                LintIssue(
                    kind="duplicate_title",
                    message=f"title '{page.title}' used by both {prior} and {page.name}",
                )
            )
        else:
            seen_titles[page.title] = page.name

    return report
