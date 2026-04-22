"""Tests for ToolBuilder."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.application.tool_builder import ToolBuilder


@pytest.fixture
def mock_factory() -> MagicMock:
    """Create a mock AgentFactory."""
    factory = MagicMock()
    factory._config_dir = Path("/tmp/configs")
    return factory


@pytest.fixture
def mock_resolver() -> MagicMock:
    """Create a mock ToolResolverProtocol."""
    resolver = MagicMock()
    mock_tool = MagicMock()
    mock_tool.name = "mock_tool"
    resolver.resolve.return_value = [mock_tool]
    resolver.resolve_single.return_value = mock_tool
    resolver.get_available_tools.return_value = ["mock_tool", "file_read"]
    return resolver


@pytest.fixture
def builder(mock_factory: MagicMock) -> ToolBuilder:
    """Create a ToolBuilder instance with mock factory."""
    return ToolBuilder(mock_factory)


@pytest.fixture
def builder_with_resolver(
    mock_factory: MagicMock, mock_resolver: MagicMock
) -> ToolBuilder:
    """Create a ToolBuilder with a mock resolver."""
    return ToolBuilder(mock_factory, tool_resolver=mock_resolver)


class TestHydrateWikiToolSpec:
    """Tests for the hydrate_wiki_tool_spec static method."""

    def test_non_wiki_spec_passthrough(self) -> None:
        assert ToolBuilder.hydrate_wiki_tool_spec("file_read", {}) == "file_read"

    def test_dict_spec_passthrough(self) -> None:
        spec: dict[str, Any] = {"type": "CustomTool", "params": {"key": "val"}}
        assert ToolBuilder.hydrate_wiki_tool_spec(spec, {}) == spec

    def test_wiki_spec_with_store_dir(self) -> None:
        config: dict[str, Any] = {"wiki": {"store_dir": "/custom/wiki"}}
        result = ToolBuilder.hydrate_wiki_tool_spec("wiki", config)
        assert isinstance(result, dict)
        assert result["type"] == "WikiTool"
        assert result["params"]["store_dir"] == "/custom/wiki"

    def test_wiki_spec_derives_from_persistence(self) -> None:
        config: dict[str, Any] = {"persistence": {"work_dir": "/data/.tf"}}
        result = ToolBuilder.hydrate_wiki_tool_spec("wiki", config)
        assert isinstance(result, dict)
        assert result["params"]["store_dir"] == str(
            Path("/data/.tf") / "memory" / "wiki"
        )

    def test_wiki_spec_default_persistence(self) -> None:
        result = ToolBuilder.hydrate_wiki_tool_spec("wiki", {})
        assert isinstance(result, dict)
        assert result["params"]["store_dir"] == str(
            Path(".taskforce") / "memory" / "wiki"
        )


class TestResolveWikiStoreDir:
    """Tests for the resolve_wiki_store_dir static method."""

    def test_explicit_store_dir(self) -> None:
        config: dict[str, Any] = {"wiki": {"store_dir": "/explicit/path"}}
        assert ToolBuilder.resolve_wiki_store_dir(config) == "/explicit/path"

    def test_work_dir_override(self) -> None:
        result = ToolBuilder.resolve_wiki_store_dir({}, work_dir_override="/override")
        assert result == str(Path("/override") / "memory" / "wiki")

    def test_persistence_work_dir(self) -> None:
        config: dict[str, Any] = {"persistence": {"work_dir": "/persist"}}
        result = ToolBuilder.resolve_wiki_store_dir(config)
        assert result == str(Path("/persist") / "memory" / "wiki")

    def test_default_fallback(self) -> None:
        result = ToolBuilder.resolve_wiki_store_dir({})
        assert result == str(Path(".taskforce") / "memory" / "wiki")

    def test_explicit_store_dir_takes_precedence(self) -> None:
        config: dict[str, Any] = {
            "wiki": {"store_dir": "/explicit"},
            "persistence": {"work_dir": "/persist"},
        }
        result = ToolBuilder.resolve_wiki_store_dir(
            config, work_dir_override="/override"
        )
        assert result == "/explicit"


class TestBuildOrchestrationTool:
    """Tests for build_orchestration_tool."""

    def test_no_orchestration_config_returns_none(
        self, builder: ToolBuilder
    ) -> None:
        result = builder.build_orchestration_tool({})
        assert result is None

    def test_orchestration_disabled_returns_none(
        self, builder: ToolBuilder
    ) -> None:
        result = builder.build_orchestration_tool(
            {"orchestration": {"enabled": False}}
        )
        assert result is None



class TestCreateDefaultTools:
    """Tests for create_default_tools."""

    def test_returns_expected_tool_count(self, builder: ToolBuilder) -> None:
        llm_provider = AsyncMock()
        tools = builder.create_default_tools(llm_provider)
        assert len(tools) == 9

    def test_tool_names_match_expected_set(self, builder: ToolBuilder) -> None:
        llm_provider = AsyncMock()
        tools = builder.create_default_tools(llm_provider)
        tool_names = {t.name for t in tools}
        expected = {
            "web_search",
            "web_fetch",
            "python",
            "github",
            "git",
            "file_read",
            "file_write",
            "shell",
            "ask_user",
        }
        assert tool_names == expected


class TestCreateNativeTools:
    """Tests for create_native_tools."""

    def test_empty_tools_config_returns_defaults(
        self, builder: ToolBuilder
    ) -> None:
        config: dict[str, Any] = {"tools": []}
        llm_provider = AsyncMock()
        tools = builder.create_native_tools(config, llm_provider)
        assert len(tools) == 9  # defaults

    def test_no_tools_key_returns_defaults(
        self, builder: ToolBuilder
    ) -> None:
        llm_provider = AsyncMock()
        tools = builder.create_native_tools({}, llm_provider)
        assert len(tools) == 9


class TestBuildTools:
    """Tests for the async build_tools entry point."""

    @pytest.mark.asyncio
    async def test_build_tools_uses_config_tools(
        self, builder: ToolBuilder
    ) -> None:
        config: dict[str, Any] = {"tools": ["file_read"]}
        llm_provider = AsyncMock()
        tools, mcp_contexts = await builder.build_tools(
            config=config, llm_provider=llm_provider, include_mcp=False
        )
        # Should have attempted to instantiate file_read (may fail in test env)
        assert isinstance(tools, list)
        assert mcp_contexts == []

    @pytest.mark.asyncio
    async def test_build_tools_no_mcp(self, builder: ToolBuilder) -> None:
        config: dict[str, Any] = {}
        llm_provider = AsyncMock()
        tools, mcp_contexts = await builder.build_tools(
            config=config, llm_provider=llm_provider, include_mcp=False
        )
        assert mcp_contexts == []
        assert len(tools) == 9  # defaults




class TestResolverDelegation:
    """Tests verifying ToolBuilder delegates to resolver when available."""

    def test_create_default_tools_delegates_to_resolver(
        self, builder_with_resolver: ToolBuilder, mock_resolver: MagicMock
    ) -> None:
        llm_provider = AsyncMock()
        tools = builder_with_resolver.create_default_tools(llm_provider)
        mock_resolver.resolve.assert_called_once_with(
            ToolBuilder._DEFAULT_TOOL_NAMES
        )
        assert len(tools) == 1  # mock returns [mock_tool]

    def test_get_all_native_tools_delegates_to_resolver(
        self, builder_with_resolver: ToolBuilder, mock_resolver: MagicMock
    ) -> None:
        llm_provider = AsyncMock()
        tools = builder_with_resolver.get_all_native_tools(llm_provider)
        mock_resolver.get_available_tools.assert_called_once()
        mock_resolver.resolve.assert_called_once_with(
            ["mock_tool", "file_read"]
        )
        assert len(tools) == 1

    def test_create_native_tools_delegates_to_resolver(
        self, builder_with_resolver: ToolBuilder, mock_resolver: MagicMock
    ) -> None:
        config: dict[str, Any] = {"tools": ["file_read", "python"]}
        llm_provider = AsyncMock()
        tools = builder_with_resolver.create_native_tools(config, llm_provider)
        mock_resolver.resolve.assert_called_once_with(
            ["file_read", "python"]
        )
        assert len(tools) == 1

    def test_create_specialist_tools_coding_delegates_to_resolver(
        self, builder_with_resolver: ToolBuilder, mock_resolver: MagicMock
    ) -> None:
        llm_provider = AsyncMock()
        tools = builder_with_resolver.create_specialist_tools(
            "coding", {}, llm_provider
        )
        mock_resolver.resolve.assert_called_once_with(
            ["file_read", "file_write", "powershell", "ask_user"]
        )
        assert len(tools) == 1

    def test_create_specialist_tools_rag_delegates_to_resolver(
        self, builder_with_resolver: ToolBuilder, mock_resolver: MagicMock
    ) -> None:
        llm_provider = AsyncMock()
        tools = builder_with_resolver.create_specialist_tools(
            "rag", {}, llm_provider, user_context={"user_id": "u1"}
        )
        mock_resolver.resolve.assert_called_once_with(
            ["rag_semantic_search", "rag_list_documents", "rag_get_document", "ask_user"]
        )
        assert len(tools) == 1

    def test_create_specialist_tools_unknown_raises(
        self, builder_with_resolver: ToolBuilder
    ) -> None:
        llm_provider = AsyncMock()
        with pytest.raises(ValueError, match="Unknown specialist profile"):
            builder_with_resolver.create_specialist_tools(
                "unknown", {}, llm_provider
            )

    @pytest.mark.asyncio
    async def test_create_tools_from_allowlist_delegates_to_resolver(
        self, builder_with_resolver: ToolBuilder, mock_resolver: MagicMock
    ) -> None:
        llm_provider = AsyncMock()
        tools = await builder_with_resolver.create_tools_from_allowlist(
            tool_allowlist=["file_read", "python"],
            mcp_servers=[],
            mcp_tool_allowlist=[],
            llm_provider=llm_provider,
        )
        mock_resolver.resolve.assert_called_once_with(
            ["file_read", "python"]
        )
        assert len(tools) == 1

    def test_set_resolver_updates_resolver(
        self, builder: ToolBuilder, mock_resolver: MagicMock
    ) -> None:
        """Test that set_resolver changes behavior from legacy to delegation."""
        llm_provider = AsyncMock()

        # Without resolver: falls back to ToolRegistry (creates 9 defaults)
        tools_legacy = builder.create_default_tools(llm_provider)
        assert len(tools_legacy) == 9

        # Set resolver and verify delegation
        builder.set_resolver(mock_resolver)
        tools_resolved = builder.create_default_tools(llm_provider)
        mock_resolver.resolve.assert_called_once()
        assert len(tools_resolved) == 1

    def test_create_native_tools_empty_falls_back_to_defaults(
        self, builder_with_resolver: ToolBuilder, mock_resolver: MagicMock
    ) -> None:
        """Empty tools config should still delegate via create_default_tools."""
        config: dict[str, Any] = {"tools": []}
        llm_provider = AsyncMock()
        builder_with_resolver.create_native_tools(config, llm_provider)
        mock_resolver.resolve.assert_called_once_with(
            ToolBuilder._DEFAULT_TOOL_NAMES
        )
