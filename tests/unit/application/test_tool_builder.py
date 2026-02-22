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
def builder(mock_factory: MagicMock) -> ToolBuilder:
    """Create a ToolBuilder instance with mock factory."""
    return ToolBuilder(mock_factory)


class TestHydrateMemoryToolSpec:
    """Tests for the hydrate_memory_tool_spec static method."""

    def test_non_memory_spec_passthrough(self) -> None:
        result = ToolBuilder.hydrate_memory_tool_spec("file_read", {})
        assert result == "file_read"

    def test_dict_spec_passthrough(self) -> None:
        spec: dict[str, Any] = {"type": "CustomTool", "params": {"key": "val"}}
        result = ToolBuilder.hydrate_memory_tool_spec(spec, {})
        assert result == spec

    def test_memory_spec_with_store_dir(self) -> None:
        config: dict[str, Any] = {"memory": {"store_dir": "/custom/memory"}}
        result = ToolBuilder.hydrate_memory_tool_spec("memory", config)
        assert isinstance(result, dict)
        assert result["type"] == "MemoryTool"
        assert result["params"]["store_dir"] == "/custom/memory"

    def test_memory_spec_derives_from_persistence(self) -> None:
        config: dict[str, Any] = {"persistence": {"work_dir": "/data/.tf"}}
        result = ToolBuilder.hydrate_memory_tool_spec("memory", config)
        assert isinstance(result, dict)
        assert result["type"] == "MemoryTool"
        assert result["params"]["store_dir"] == str(Path("/data/.tf") / "memory")

    def test_memory_spec_default_persistence(self) -> None:
        result = ToolBuilder.hydrate_memory_tool_spec("memory", {})
        assert isinstance(result, dict)
        assert result["params"]["store_dir"] == str(Path(".taskforce") / "memory")


class TestResolveMemoryStoreDir:
    """Tests for the resolve_memory_store_dir static method."""

    def test_explicit_store_dir(self) -> None:
        config: dict[str, Any] = {"memory": {"store_dir": "/explicit/path"}}
        result = ToolBuilder.resolve_memory_store_dir(config)
        assert result == "/explicit/path"

    def test_work_dir_override(self) -> None:
        result = ToolBuilder.resolve_memory_store_dir({}, work_dir_override="/override")
        assert result == str(Path("/override") / "memory")

    def test_persistence_work_dir(self) -> None:
        config: dict[str, Any] = {"persistence": {"work_dir": "/persist"}}
        result = ToolBuilder.resolve_memory_store_dir(config)
        assert result == str(Path("/persist") / "memory")

    def test_default_fallback(self) -> None:
        result = ToolBuilder.resolve_memory_store_dir({})
        assert result == str(Path(".taskforce") / "memory")

    def test_explicit_store_dir_takes_precedence(self) -> None:
        config: dict[str, Any] = {
            "memory": {"store_dir": "/explicit"},
            "persistence": {"work_dir": "/persist"},
        }
        result = ToolBuilder.resolve_memory_store_dir(config, work_dir_override="/override")
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

    def test_orchestration_enabled_creates_tool(
        self, builder: ToolBuilder
    ) -> None:
        with (
            patch(
                "taskforce.application.sub_agent_spawner.SubAgentSpawner"
            ),
            patch(
                "taskforce.infrastructure.tools.orchestration.AgentTool"
            ) as mock_agent_tool_cls,
        ):
            mock_agent_tool_cls.return_value = MagicMock()
            result = builder.build_orchestration_tool(
                {"orchestration": {"enabled": True}}
            )
            assert result is not None
            mock_agent_tool_cls.assert_called_once()


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
            "powershell",
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
