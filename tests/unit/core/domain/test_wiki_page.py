"""Tests for the wiki page domain model."""

from __future__ import annotations

from taskforce.core.domain.wiki_page import WikiPage, slugify


class TestSlugify:
    def test_basic_lowercase(self) -> None:
        assert slugify("Hello World") == "hello-world"

    def test_umlauts_mapped(self) -> None:
        assert slugify("Müller & Söhne") == "mueller-soehne"
        assert slugify("Straße") == "strasse"

    def test_collapses_non_alphanum(self) -> None:
        assert slugify("Rechnung #42/2026!") == "rechnung-42-2026"

    def test_trims_dashes(self) -> None:
        assert slugify("  --foo--  ") == "foo"

    def test_empty(self) -> None:
        assert slugify("") == ""


class TestWikiPage:
    def test_kind_derived_from_directory(self) -> None:
        page = WikiPage(
            name="entities/steuerberater-mueller",
            title="Steuerberater Mueller",
            body="# Steuerberater Mueller\n",
        )
        assert page.kind == "entities"

    def test_kind_falls_back_to_other_when_no_prefix(self) -> None:
        page = WikiPage(name="root-page", title="Root", body="")
        assert page.kind == "other"

    def test_touch_updates_timestamp(self) -> None:
        page = WikiPage(name="entities/x", title="X", body="")
        original = page.updated_at
        page.touch()
        assert page.updated_at >= original
