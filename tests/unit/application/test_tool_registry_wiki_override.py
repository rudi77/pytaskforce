"""Regression tests for the WikiTool ↔ wiki-store-override interaction.

The enterprise plugin installs ``set_wiki_store_override`` so the wiki
store is scoped per (tenant, user) rather than living at a flat
``<work_dir>/memory/wiki``. Until this fix the override was respected
by the framework's ``InfrastructureBuilder.build_wiki_store`` (used by
``/api/v1/memory/*``) but bypassed when the tool registry constructed
the WikiTool for an agent — so agent writes ended up in the flat path
while UI reads hit the per-user path. This module pins the fixed
behaviour.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    set_wiki_store_override,
)
from taskforce.application.tool_registry import ToolRegistry


@pytest.fixture(autouse=True)
def _reset_overrides():
    clear_infrastructure_overrides()
    yield
    clear_infrastructure_overrides()


@pytest.mark.spec("wiki-memory.store_override_is_consulted_per_build")
def test_wikitool_uses_override_when_installed(tmp_path):
    """An installed wiki-store override is consulted when WikiTool is built."""
    sentinel_store = MagicMock(name="tenant-scoped-wiki-store")

    def provider(work_dir):
        # The enterprise provider ignores ``work_dir`` and reads (tenant, user)
        # from ContextVars. We just record that it was called.
        provider.called_with = work_dir
        return sentinel_store

    provider.called_with = None
    set_wiki_store_override(provider)

    registry = ToolRegistry(wiki_store_dir=str(tmp_path / "memory" / "wiki"))
    tools = registry.resolve(["wiki"])
    assert len(tools) == 1
    wiki_tool = tools[0]

    # The tool's underlying store must be the one returned by the override,
    # NOT a freshly constructed FileWikiStore at the flat path.
    assert wiki_tool._store is sentinel_store
    assert provider.called_with is not None  # provider was actually invoked


@pytest.mark.spec("wiki-memory.store_override_is_consulted_per_build")
def test_wikitool_falls_back_to_store_dir_without_override(tmp_path):
    """Without an override, the legacy ``store_dir`` injection still wins."""
    store_dir = str(tmp_path / "memory" / "wiki")
    registry = ToolRegistry(wiki_store_dir=store_dir)
    tools = registry.resolve(["wiki"])
    wiki_tool = tools[0]

    # The store should be a FileWikiStore rooted at the configured dir.
    from taskforce.infrastructure.memory.file_wiki_store import FileWikiStore

    assert isinstance(wiki_tool._store, FileWikiStore)
    # FileWikiStore exposes its root as ``_root``.
    assert str(wiki_tool._store._root) == store_dir


def test_wikitool_falls_back_when_override_raises(tmp_path):
    """A buggy override mustn't break agent build — fall back to store_dir."""

    def broken_provider(work_dir):
        raise RuntimeError("boom")

    set_wiki_store_override(broken_provider)
    store_dir = str(tmp_path / "memory" / "wiki")
    registry = ToolRegistry(wiki_store_dir=store_dir)
    tools = registry.resolve(["wiki"])
    wiki_tool = tools[0]

    from taskforce.infrastructure.memory.file_wiki_store import FileWikiStore

    assert isinstance(wiki_tool._store, FileWikiStore)
