"""End-to-end integration test for wiki-style long-term memory.

Verifies the full wiring path: ``AgentFactory`` builds an agent with a
``wiki`` tool in its tool list, the tool receives a ``FileWikiStore``
bound to the configured directory, and the agent's ``_wiki_store``
reference points at the same directory so the auto-injected wiki index
stays in sync with what the tool reads and writes.

No LLM is called — the test stubs tool execution by driving the wiki
tool directly from the agent's tool registry.  That catches wiring
regressions (factory → tool_registry → tool_builder → lean_agent)
without needing API keys.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskforce.application.factory import AgentFactory


@pytest.mark.asyncio
async def test_factory_wires_wiki_tool_and_store(tmp_path: Path) -> None:
    wiki_root = tmp_path / "memory" / "wiki"
    factory = AgentFactory()

    agent = await factory.create_agent(
        system_prompt="You are a test agent.",
        tools=["wiki"],
        persistence={"type": "file", "work_dir": str(tmp_path)},
    )

    wiki_tool = agent.tools.get("wiki")
    assert wiki_tool is not None, "agent should expose the 'wiki' tool"

    result = await wiki_tool.execute(
        action="write_page",
        name="entities/mueller",
        title="Steuerberater Mueller",
        content="## Kontakt\n- Tel: 0664-1234567\n",
        tags=["kontakt", "steuer"],
    )
    assert result["success"] is True
    page_file = wiki_root / "entities" / "mueller.md"
    assert page_file.exists(), f"expected page file at {page_file}"

    recall = await wiki_tool.execute(action="search", query="Mueller")
    assert recall["success"] is True
    assert recall["count"] == 1
    assert recall["results"][0]["name"] == "entities/mueller"


@pytest.mark.asyncio
async def test_agent_wiki_context_is_injected_at_session_start(
    tmp_path: Path,
) -> None:
    """The agent's wiki store reads the same index the tool writes."""
    factory = AgentFactory()
    agent = await factory.create_agent(
        system_prompt="You are a test agent.",
        tools=["wiki"],
        persistence={"type": "file", "work_dir": str(tmp_path)},
    )

    # Fresh agent: the wiki store should be wired in.
    assert agent._wiki_store is not None, "wiki_store must be injected"

    wiki_tool = agent.tools["wiki"]
    await wiki_tool.execute(
        action="write_page",
        name="preferences/bookkeeping-formats",
        title="Bookkeeping Formats",
        content="Always book as Tab-separated.",
    )

    await agent.load_memory_context(mission="bookkeeping")
    context = agent._wiki_context or ""
    assert "bookkeeping" in context.lower(), (
        "the freshly written page should show up in the injected wiki context"
    )


@pytest.mark.asyncio
async def test_update_page_does_not_create_duplicate(tmp_path: Path) -> None:
    """Updating an existing page edits in place instead of duplicating it."""
    factory = AgentFactory()
    agent = await factory.create_agent(
        system_prompt="You are a test agent.",
        tools=["wiki"],
        persistence={"type": "file", "work_dir": str(tmp_path)},
    )
    wiki_tool = agent.tools["wiki"]

    await wiki_tool.execute(
        action="write_page",
        name="entities/mueller",
        title="Steuerberater Mueller",
        content="## Kontakt\n- Tel: 0664-1234567\n",
    )
    await wiki_tool.execute(
        action="update_page",
        name="entities/mueller",
        section="Kontakt",
        content="- Tel: 0664-9999999",
        mode="replace",
    )

    listing = await wiki_tool.execute(action="list_pages")
    names = [p["name"] for p in listing["pages"]]
    assert names == ["entities/mueller"], "no duplicate page should exist"

    read = await wiki_tool.execute(action="read_page", name="entities/mueller")
    assert "0664-9999999" in read["page"]["body"]
    assert "0664-1234567" not in read["page"]["body"]
