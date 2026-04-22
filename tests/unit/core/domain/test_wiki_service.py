"""Tests for wiki_service helpers (index render, section editing, link extraction)."""

from __future__ import annotations

from taskforce.core.domain.wiki_page import WikiPage
from taskforce.core.domain.wiki_service import (
    apply_section_update,
    extract_sections,
    extract_wiki_links,
    render_index,
)


class TestExtractWikiLinks:
    def test_finds_bracket_links(self) -> None:
        body = "See [[entities/mueller]] and [[preferences/formats]]."
        assert extract_wiki_links(body) == [
            "entities/mueller",
            "preferences/formats",
        ]

    def test_returns_empty_without_links(self) -> None:
        assert extract_wiki_links("plain text, no links") == []


class TestExtractSections:
    def test_basic(self) -> None:
        body = "## Kontakt\nfoo\n\n## Notizen\nbar\n"
        sections = extract_sections(body)
        assert set(sections) == {"Kontakt", "Notizen"}

    def test_section_spans_until_next_header(self) -> None:
        body = "## A\nalpha\n## B\nbeta\n"
        sections = extract_sections(body)
        start_a, end_a = sections["A"]
        assert body[start_a:end_a] == "## A\nalpha\n"


class TestApplySectionUpdate:
    def test_replace_section_body(self) -> None:
        body = "## Kontakt\nalt\n\n## Notizen\nx\n"
        result = apply_section_update(body, "Kontakt", "neu", mode="replace")
        assert "## Kontakt\n\nneu\n" in result
        assert "alt" not in result
        assert "## Notizen" in result

    def test_append_to_existing_section(self) -> None:
        body = "## Notizen\nzeile 1\n"
        result = apply_section_update(body, "Notizen", "zeile 2", mode="append")
        assert "zeile 1" in result
        assert "zeile 2" in result

    def test_create_section_if_missing(self) -> None:
        body = "## Kontakt\nfoo\n"
        result = apply_section_update(body, "Related", "[[entities/x]]", mode="append")
        assert "## Kontakt" in result
        assert "## Related" in result
        assert "[[entities/x]]" in result

    def test_rejects_unknown_mode(self) -> None:
        try:
            apply_section_update("body", "s", "c", mode="wiggle")
        except ValueError as exc:
            assert "wiggle" in str(exc)
        else:
            raise AssertionError("expected ValueError for invalid mode")


class TestRenderIndex:
    def test_groups_by_kind_and_sorts(self) -> None:
        pages = [
            WikiPage(name="entities/b", title="B entity", body="body b"),
            WikiPage(name="entities/a", title="A entity", body="body a"),
            WikiPage(name="preferences/x", title="Pref X", body="pref body"),
        ]
        index = render_index(pages)
        assert "## Entities" in index
        assert "## Preferences" in index
        assert index.index("A entity") < index.index("B entity")
        assert "[Pref X](preferences/x.md)" in index

    def test_placeholder_for_empty_kind(self) -> None:
        index = render_index([])
        assert "_(no pages yet)_" in index

    def test_hook_uses_first_paragraph(self) -> None:
        pages = [
            WikiPage(
                name="entities/x",
                title="X",
                body="# X\n\nFirst paragraph content.\n\nSecond.\n",
            )
        ]
        index = render_index(pages)
        assert "First paragraph content" in index
