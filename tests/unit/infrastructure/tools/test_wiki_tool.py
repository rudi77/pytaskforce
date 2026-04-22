"""Tests for the wiki tool's action dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.infrastructure.memory.file_wiki_store import FileWikiStore
from taskforce.infrastructure.tools.native.wiki_tool import WikiTool


@pytest.fixture
def tool(tmp_path: Path) -> WikiTool:
    store = FileWikiStore(tmp_path / "wiki")
    return WikiTool(store=store)


async def test_write_then_read(tool: WikiTool) -> None:
    write = await tool.execute(
        action="write_page",
        name="entities/mueller",
        title="Steuerberater Mueller",
        content="## Kontakt\n- Tel: 0664-1234567\n",
        tags=["kontakt", "steuer"],
    )
    assert write["success"] is True
    assert write["page"]["name"] == "entities/mueller"

    read = await tool.execute(action="read_page", name="entities/mueller")
    assert read["success"] is True
    assert "0664-1234567" in read["page"]["body"]


async def test_search_returns_matches(tool: WikiTool) -> None:
    await tool.execute(
        action="write_page",
        name="entities/mueller",
        title="Steuerberater Mueller",
        content="details",
        tags=["steuer"],
    )
    result = await tool.execute(action="search", query="Mueller", limit=3)
    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"][0]["name"] == "entities/mueller"


async def test_update_page_appends_section(tool: WikiTool) -> None:
    await tool.execute(
        action="write_page",
        name="entities/mueller",
        title="Mueller",
        content="## Kontakt\n- Tel: alt\n",
    )
    result = await tool.execute(
        action="update_page",
        name="entities/mueller",
        section="Kontakt",
        content="- Fax: 0664-9999",
        mode="append",
    )
    assert result["success"] is True

    read = await tool.execute(action="read_page", name="entities/mueller")
    assert "0664-9999" in read["page"]["body"]
    assert "alt" in read["page"]["body"]


async def test_update_page_replace_mode(tool: WikiTool) -> None:
    await tool.execute(
        action="write_page",
        name="entities/x",
        title="X",
        content="## Kontakt\nalt\n",
    )
    await tool.execute(
        action="update_page",
        name="entities/x",
        section="Kontakt",
        content="neu",
        mode="replace",
    )
    read = await tool.execute(action="read_page", name="entities/x")
    assert "alt" not in read["page"]["body"]
    assert "neu" in read["page"]["body"]


async def test_delete_page(tool: WikiTool) -> None:
    await tool.execute(
        action="write_page", name="entities/x", title="X", content="body"
    )
    deleted = await tool.execute(action="delete_page", name="entities/x")
    assert deleted["success"] is True
    read = await tool.execute(action="read_page", name="entities/x")
    assert read["success"] is False


async def test_list_pages(tool: WikiTool) -> None:
    await tool.execute(
        action="write_page", name="entities/a", title="A", content="body"
    )
    await tool.execute(
        action="write_page", name="preferences/b", title="B", content="body"
    )
    result = await tool.execute(action="list_pages")
    assert result["success"] is True
    assert result["count"] == 2


async def test_log_appends(tool: WikiTool) -> None:
    result = await tool.execute(action="log", entry="hello world")
    assert result["success"] is True


async def test_unknown_action(tool: WikiTool) -> None:
    result = await tool.execute(action="does_not_exist")
    assert result["success"] is False
    assert "unknown action" in result["error"]


async def test_missing_required_param(tool: WikiTool) -> None:
    result = await tool.execute(action="read_page")
    assert result["success"] is False
    assert "name" in result["error"]
