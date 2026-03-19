"""Tests for InfrastructureBuilder."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from taskforce.application.infrastructure_builder import InfrastructureBuilder
from taskforce.core.domain.context_policy import ContextPolicy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with a dev.yaml profile."""
    dev_config = {
        "profile": "dev",
        "persistence": {"type": "file", "work_dir": ".taskforce"},
        "agent": {"max_steps": 30},
        "tools": ["file_read", "file_write"],
    }
    (tmp_path / "dev.yaml").write_text(yaml.dump(dev_config))
    return tmp_path


@pytest.fixture
def builder(config_dir: Path) -> InfrastructureBuilder:
    """Create an InfrastructureBuilder with a temp config directory."""
    return InfrastructureBuilder(config_dir=config_dir)


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestInfrastructureBuilderInit:
    """Tests for InfrastructureBuilder.__init__."""

    def test_explicit_config_dir(self, tmp_path: Path) -> None:
        builder = InfrastructureBuilder(config_dir=tmp_path)
        assert builder.config_dir == tmp_path

    def test_explicit_config_dir_as_string(self, tmp_path: Path) -> None:
        builder = InfrastructureBuilder(config_dir=str(tmp_path))
        assert builder.config_dir == tmp_path

    def test_default_config_dir_uses_new_location(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "src" / "taskforce" / "configs"
        new_dir.mkdir(parents=True)
        with patch(
            "taskforce.application.infrastructure_builder.get_base_path",
            return_value=tmp_path,
        ):
            builder = InfrastructureBuilder()
        assert builder.config_dir == new_dir

    def test_default_config_dir_falls_back_to_old_location(self, tmp_path: Path) -> None:
        old_dir = tmp_path / "configs"
        old_dir.mkdir()
        with patch(
            "taskforce.application.infrastructure_builder.get_base_path",
            return_value=tmp_path,
        ):
            builder = InfrastructureBuilder()
        assert builder.config_dir == old_dir

    def test_default_config_dir_neither_exists(self, tmp_path: Path) -> None:
        with patch(
            "taskforce.application.infrastructure_builder.get_base_path",
            return_value=tmp_path,
        ):
            builder = InfrastructureBuilder()
        # Defaults to new location even if it doesn't exist
        assert builder.config_dir == tmp_path / "src" / "taskforce" / "configs"


# ---------------------------------------------------------------------------
# Profile Loading
# ---------------------------------------------------------------------------


class TestLoadProfile:
    """Tests for load_profile."""

    def test_load_existing_profile(self, builder: InfrastructureBuilder) -> None:
        config = builder.load_profile("dev")
        assert config["profile"] == "dev"
        assert config["persistence"]["type"] == "file"

    def test_load_missing_profile_raises(self, builder: InfrastructureBuilder) -> None:
        with pytest.raises(FileNotFoundError, match="Profile not found"):
            builder.load_profile("nonexistent")

    def test_load_custom_profile(self, config_dir: Path) -> None:
        custom_dir = config_dir / "custom"
        custom_dir.mkdir()
        custom_config = {"profile": "my_agent", "agent": {"max_steps": 5}}
        (custom_dir / "my_agent.yaml").write_text(yaml.dump(custom_config))

        builder = InfrastructureBuilder(config_dir=config_dir)
        config = builder.load_profile("my_agent")
        assert config["profile"] == "my_agent"

    def test_standard_profile_takes_precedence(self, config_dir: Path) -> None:
        (config_dir / "dup.yaml").write_text(yaml.dump({"source": "standard"}))
        custom_dir = config_dir / "custom"
        custom_dir.mkdir()
        (custom_dir / "dup.yaml").write_text(yaml.dump({"source": "custom"}))

        builder = InfrastructureBuilder(config_dir=config_dir)
        config = builder.load_profile("dup")
        assert config["source"] == "standard"

    def test_load_empty_yaml_returns_empty_dict(self, config_dir: Path) -> None:
        (config_dir / "empty.yaml").write_text("")
        builder = InfrastructureBuilder(config_dir=config_dir)
        config = builder.load_profile("empty")
        assert config == {}


class TestLoadProfileSafe:
    """Tests for load_profile_safe."""

    def test_existing_profile(self, builder: InfrastructureBuilder) -> None:
        config = builder.load_profile_safe("dev")
        assert config["profile"] == "dev"

    def test_missing_profile_returns_empty_dict(
        self, builder: InfrastructureBuilder
    ) -> None:
        config = builder.load_profile_safe("nonexistent")
        assert config == {}


# ---------------------------------------------------------------------------
# State Manager
# ---------------------------------------------------------------------------


class TestBuildStateManager:
    """Tests for build_state_manager."""

    def test_file_state_manager_default(self, builder: InfrastructureBuilder) -> None:
        config: dict[str, Any] = {"persistence": {"type": "file", "work_dir": ".tf"}}
        with patch(
            "taskforce.infrastructure.persistence.file_state_manager.FileStateManager",
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            sm = builder.build_state_manager(config)
            mock_cls.assert_called_once_with(work_dir=".tf")
            assert sm is mock_cls.return_value

    def test_file_state_manager_with_work_dir_override(
        self, builder: InfrastructureBuilder
    ) -> None:
        config: dict[str, Any] = {"persistence": {"type": "file", "work_dir": ".tf"}}
        with patch(
            "taskforce.infrastructure.persistence.file_state_manager.FileStateManager",
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            builder.build_state_manager(config, work_dir_override="/override")
            mock_cls.assert_called_once_with(work_dir="/override")

    def test_file_state_manager_defaults_work_dir(
        self, builder: InfrastructureBuilder
    ) -> None:
        config: dict[str, Any] = {}
        with patch(
            "taskforce.infrastructure.persistence.file_state_manager.FileStateManager",
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            builder.build_state_manager(config)
            mock_cls.assert_called_once_with(work_dir=".taskforce")

    def test_database_state_manager(self, builder: InfrastructureBuilder) -> None:
        config: dict[str, Any] = {
            "persistence": {"type": "database", "db_url_env": "TEST_DB_URL"}
        }
        import sys
        import types

        mock_db_module = types.ModuleType("taskforce.infrastructure.persistence.db_state")
        mock_db_cls = MagicMock()
        mock_db_module.DbStateManager = mock_db_cls  # type: ignore[attr-defined]

        with (
            patch.dict("os.environ", {"TEST_DB_URL": "postgresql://localhost/test"}),
            patch.dict(
                sys.modules,
                {"taskforce.infrastructure.persistence.db_state": mock_db_module},
            ),
        ):
            sm = builder.build_state_manager(config)
            mock_db_cls.assert_called_once_with(db_url="postgresql://localhost/test")
            assert sm is mock_db_cls.return_value

    def test_database_state_manager_missing_env_var(
        self, builder: InfrastructureBuilder
    ) -> None:
        config: dict[str, Any] = {
            "persistence": {"type": "database", "db_url_env": "MISSING_DB_URL"}
        }
        import os
        import sys
        import types

        mock_db_module = types.ModuleType("taskforce.infrastructure.persistence.db_state")
        mock_db_module.DbStateManager = MagicMock()  # type: ignore[attr-defined]

        os.environ.pop("MISSING_DB_URL", None)
        with (
            patch.dict(
                sys.modules,
                {"taskforce.infrastructure.persistence.db_state": mock_db_module},
            ),
            pytest.raises(ValueError, match="Database URL not found"),
        ):
            builder.build_state_manager(config)

    def test_database_state_manager_default_env_var(
        self, builder: InfrastructureBuilder
    ) -> None:
        """When no db_url_env is specified, defaults to DATABASE_URL."""
        config: dict[str, Any] = {"persistence": {"type": "database"}}
        import sys
        import types

        mock_db_module = types.ModuleType("taskforce.infrastructure.persistence.db_state")
        mock_db_cls = MagicMock()
        mock_db_module.DbStateManager = mock_db_cls  # type: ignore[attr-defined]

        with (
            patch.dict("os.environ", {"DATABASE_URL": "postgresql://localhost/default"}),
            patch.dict(
                sys.modules,
                {"taskforce.infrastructure.persistence.db_state": mock_db_module},
            ),
        ):
            builder.build_state_manager(config)
            mock_db_cls.assert_called_once_with(db_url="postgresql://localhost/default")

    def test_unknown_persistence_type_raises(
        self, builder: InfrastructureBuilder
    ) -> None:
        config: dict[str, Any] = {"persistence": {"type": "redis"}}
        with pytest.raises(ValueError, match="Unknown persistence type: redis"):
            builder.build_state_manager(config)


# ---------------------------------------------------------------------------
# LLM Provider
# ---------------------------------------------------------------------------


class TestBuildLlmProvider:
    """Tests for build_llm_provider."""

    def test_builds_llm_with_router(self, builder: InfrastructureBuilder) -> None:
        config: dict[str, Any] = {
            "llm": {
                "config_path": "/abs/path/llm_config.yaml",
                "default_model": "main",
            }
        }
        mock_service = MagicMock()
        mock_service.routing_config = {}
        mock_service.default_model = "main"
        mock_router = MagicMock()

        with (
            patch(
                "taskforce.infrastructure.llm.litellm_service.LiteLLMService",
                return_value=mock_service,
            ) as mock_svc_cls,
            patch(
                "taskforce.infrastructure.llm.llm_router.build_llm_router",
                return_value=mock_router,
            ) as mock_build_router,
        ):
            result = builder.build_llm_provider(config)
            mock_svc_cls.assert_called_once_with(config_path="/abs/path/llm_config.yaml")
            mock_build_router.assert_called_once_with(mock_service, {}, "main")
            assert result is mock_router

    def test_default_model_falls_back_to_provider_attribute(
        self, builder: InfrastructureBuilder
    ) -> None:
        config: dict[str, Any] = {"llm": {"config_path": "/abs/path/cfg.yaml"}}
        mock_service = MagicMock()
        mock_service.routing_config = {}
        mock_service.default_model = "fallback_model"

        with (
            patch(
                "taskforce.infrastructure.llm.litellm_service.LiteLLMService",
                return_value=mock_service,
            ),
            patch(
                "taskforce.infrastructure.llm.llm_router.build_llm_router",
                return_value=MagicMock(),
            ) as mock_build_router,
        ):
            builder.build_llm_provider(config)
            # default_model not in llm config, so falls back to provider attribute
            mock_build_router.assert_called_once_with(
                mock_service, {}, "fallback_model"
            )

    def test_relative_config_path_resolved(
        self, builder: InfrastructureBuilder, tmp_path: Path
    ) -> None:
        config: dict[str, Any] = {
            "llm": {"config_path": "src/taskforce/configs/llm_config.yaml"}
        }
        mock_service = MagicMock()
        mock_service.routing_config = {}
        mock_service.default_model = "main"

        with (
            patch(
                "taskforce.application.infrastructure_builder.get_base_path",
                return_value=tmp_path,
            ),
            patch(
                "taskforce.infrastructure.llm.litellm_service.LiteLLMService",
                return_value=mock_service,
            ) as mock_svc_cls,
            patch(
                "taskforce.infrastructure.llm.llm_router.build_llm_router",
                return_value=MagicMock(),
            ),
        ):
            builder.build_llm_provider(config)
            expected_path = str(tmp_path / "src/taskforce/configs/llm_config.yaml")
            mock_svc_cls.assert_called_once_with(config_path=expected_path)

    def test_default_llm_config_path_when_not_specified(
        self, builder: InfrastructureBuilder, tmp_path: Path
    ) -> None:
        """When no config_path is provided, uses default path."""
        config: dict[str, Any] = {}
        mock_service = MagicMock()
        mock_service.routing_config = {}
        mock_service.default_model = "main"

        with (
            patch(
                "taskforce.application.infrastructure_builder.get_base_path",
                return_value=tmp_path,
            ),
            patch(
                "taskforce.infrastructure.llm.litellm_service.LiteLLMService",
                return_value=mock_service,
            ) as mock_svc_cls,
            patch(
                "taskforce.infrastructure.llm.llm_router.build_llm_router",
                return_value=MagicMock(),
            ),
        ):
            builder.build_llm_provider(config)
            expected = str(tmp_path / "src/taskforce/configs/llm_config.yaml")
            mock_svc_cls.assert_called_once_with(config_path=expected)

    def test_backward_compat_config_path_migration(
        self, builder: InfrastructureBuilder, tmp_path: Path
    ) -> None:
        """Old configs/ path migrates to src/taskforce/configs/ if new path exists."""
        config: dict[str, Any] = {
            "llm": {"config_path": "configs/llm_config.yaml"}
        }
        # The old resolved path does NOT exist, but the new one does
        new_path = tmp_path / "src" / "taskforce" / "configs" / "llm_config.yaml"
        new_path.parent.mkdir(parents=True)
        new_path.touch()

        mock_service = MagicMock()
        mock_service.routing_config = {}
        mock_service.default_model = "main"

        with (
            patch(
                "taskforce.application.infrastructure_builder.get_base_path",
                return_value=tmp_path,
            ),
            patch(
                "taskforce.infrastructure.llm.litellm_service.LiteLLMService",
                return_value=mock_service,
            ) as mock_svc_cls,
            patch(
                "taskforce.infrastructure.llm.llm_router.build_llm_router",
                return_value=MagicMock(),
            ),
        ):
            builder.build_llm_provider(config)
            mock_svc_cls.assert_called_once_with(config_path=str(new_path))

    def test_provider_without_routing_config_attribute(
        self, builder: InfrastructureBuilder
    ) -> None:
        """Provider without routing_config attribute uses empty dict."""
        config: dict[str, Any] = {
            "llm": {"config_path": "/abs/path/cfg.yaml", "default_model": "main"}
        }
        mock_service = MagicMock(spec=[])  # No attributes at all
        mock_router = MagicMock()

        with (
            patch(
                "taskforce.infrastructure.llm.litellm_service.LiteLLMService",
                return_value=mock_service,
            ),
            patch(
                "taskforce.infrastructure.llm.llm_router.build_llm_router",
                return_value=mock_router,
            ) as mock_build_router,
        ):
            result = builder.build_llm_provider(config)
            # getattr(provider, "routing_config", {}) should return {}
            mock_build_router.assert_called_once_with(mock_service, {}, "main")
            assert result is mock_router


# ---------------------------------------------------------------------------
# Context Policy
# ---------------------------------------------------------------------------


class TestBuildContextPolicy:
    """Tests for build_context_policy."""

    def test_from_config(self, builder: InfrastructureBuilder) -> None:
        config: dict[str, Any] = {
            "context_policy": {
                "max_items": 5,
                "max_chars_per_item": 1000,
                "max_total_chars": 5000,
            }
        }
        policy = builder.build_context_policy(config)
        assert isinstance(policy, ContextPolicy)
        assert policy.max_items == 5
        assert policy.max_chars_per_item == 1000

    def test_defaults_when_no_context_policy(
        self, builder: InfrastructureBuilder
    ) -> None:
        config: dict[str, Any] = {}
        policy = builder.build_context_policy(config)
        assert isinstance(policy, ContextPolicy)
        # Should be conservative default
        default = ContextPolicy.conservative_default()
        assert policy.max_items == default.max_items

    def test_context_policy_none_value(self, builder: InfrastructureBuilder) -> None:
        """Explicit None value for context_policy uses conservative default."""
        config: dict[str, Any] = {"context_policy": None}
        policy = builder.build_context_policy(config)
        default = ContextPolicy.conservative_default()
        assert policy.max_items == default.max_items


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


class TestBuildMcpTools:
    """Tests for build_mcp_tools."""

    async def test_empty_servers_returns_empty(
        self, builder: InfrastructureBuilder
    ) -> None:
        tools, contexts = await builder.build_mcp_tools([])
        assert tools == []
        assert contexts == []

    async def test_delegates_to_connection_manager(
        self, builder: InfrastructureBuilder
    ) -> None:
        mock_manager = MagicMock()
        mock_manager.connect_all = AsyncMock(return_value=([MagicMock()], [MagicMock()]))
        servers = [MagicMock()]

        with patch(
            "taskforce.infrastructure.tools.mcp.connection_manager.create_default_connection_manager",
            return_value=mock_manager,
        ):
            tools, contexts = await builder.build_mcp_tools(servers, tool_filter=["t1"])
            mock_manager.connect_all.assert_awaited_once_with(
                servers, tool_filter=["t1"]
            )
            assert len(tools) == 1
            assert len(contexts) == 1

    async def test_no_tool_filter(self, builder: InfrastructureBuilder) -> None:
        """When tool_filter is None, all tools are returned."""
        mock_manager = MagicMock()
        mock_manager.connect_all = AsyncMock(return_value=([MagicMock(), MagicMock()], [MagicMock()]))
        servers = [MagicMock()]

        with patch(
            "taskforce.infrastructure.tools.mcp.connection_manager.create_default_connection_manager",
            return_value=mock_manager,
        ):
            tools, contexts = await builder.build_mcp_tools(servers, tool_filter=None)
            mock_manager.connect_all.assert_awaited_once_with(
                servers, tool_filter=None
            )
            assert len(tools) == 2


# ---------------------------------------------------------------------------
# Runtime Tracker
# ---------------------------------------------------------------------------


class TestBuildRuntimeTracker:
    """Tests for build_runtime_tracker."""

    def test_disabled_returns_none(self, builder: InfrastructureBuilder) -> None:
        config: dict[str, Any] = {"runtime": {"enabled": False}}
        assert builder.build_runtime_tracker(config) is None

    def test_missing_runtime_config_returns_none(
        self, builder: InfrastructureBuilder
    ) -> None:
        assert builder.build_runtime_tracker({}) is None

    def test_memory_store(self, builder: InfrastructureBuilder) -> None:
        config: dict[str, Any] = {"runtime": {"enabled": True, "store": "memory"}}
        with (
            patch(
                "taskforce.infrastructure.runtime.AgentRuntimeTracker"
            ) as mock_tracker,
            patch(
                "taskforce.infrastructure.runtime.InMemoryHeartbeatStore"
            ) as mock_hb,
            patch(
                "taskforce.infrastructure.runtime.InMemoryCheckpointStore"
            ) as mock_cp,
        ):
            mock_tracker.return_value = MagicMock()
            result = builder.build_runtime_tracker(config)
            mock_hb.assert_called_once()
            mock_cp.assert_called_once()
            mock_tracker.assert_called_once()
            assert result is mock_tracker.return_value

    def test_file_store(self, builder: InfrastructureBuilder) -> None:
        config: dict[str, Any] = {
            "runtime": {"enabled": True, "store": "file", "work_dir": "/tmp/rt"}
        }
        with (
            patch(
                "taskforce.infrastructure.runtime.AgentRuntimeTracker"
            ) as mock_tracker,
            patch(
                "taskforce.infrastructure.runtime.FileHeartbeatStore"
            ) as mock_hb,
            patch(
                "taskforce.infrastructure.runtime.FileCheckpointStore"
            ) as mock_cp,
        ):
            mock_tracker.return_value = MagicMock()
            result = builder.build_runtime_tracker(config)
            mock_hb.assert_called_once_with("/tmp/rt")
            mock_cp.assert_called_once_with("/tmp/rt")
            assert result is mock_tracker.return_value

    def test_file_store_work_dir_fallback_chain(
        self, builder: InfrastructureBuilder
    ) -> None:
        """Falls back to work_dir_override, then persistence.work_dir, then .taskforce."""
        config: dict[str, Any] = {
            "runtime": {"enabled": True, "store": "file"},
            "persistence": {"work_dir": ".from_persistence"},
        }
        with (
            patch(
                "taskforce.infrastructure.runtime.AgentRuntimeTracker"
            ),
            patch(
                "taskforce.infrastructure.runtime.FileHeartbeatStore"
            ) as mock_hb,
            patch(
                "taskforce.infrastructure.runtime.FileCheckpointStore"
            ),
        ):
            builder.build_runtime_tracker(config)
            mock_hb.assert_called_once_with(".from_persistence")

    def test_file_store_work_dir_override(
        self, builder: InfrastructureBuilder
    ) -> None:
        config: dict[str, Any] = {"runtime": {"enabled": True, "store": "file"}}
        with (
            patch(
                "taskforce.infrastructure.runtime.AgentRuntimeTracker"
            ),
            patch(
                "taskforce.infrastructure.runtime.FileHeartbeatStore"
            ) as mock_hb,
            patch(
                "taskforce.infrastructure.runtime.FileCheckpointStore"
            ),
        ):
            builder.build_runtime_tracker(config, work_dir_override="/override")
            mock_hb.assert_called_once_with("/override")

    def test_file_store_default_work_dir(
        self, builder: InfrastructureBuilder
    ) -> None:
        """When no work_dir is specified anywhere, defaults to .taskforce."""
        config: dict[str, Any] = {"runtime": {"enabled": True, "store": "file"}}
        with (
            patch(
                "taskforce.infrastructure.runtime.AgentRuntimeTracker"
            ),
            patch(
                "taskforce.infrastructure.runtime.FileHeartbeatStore"
            ) as mock_hb,
            patch(
                "taskforce.infrastructure.runtime.FileCheckpointStore"
            ),
        ):
            builder.build_runtime_tracker(config)
            mock_hb.assert_called_once_with(".taskforce")

    def test_unknown_store_type_raises(self, builder: InfrastructureBuilder) -> None:
        config: dict[str, Any] = {"runtime": {"enabled": True, "store": "redis"}}
        with pytest.raises(ValueError, match="Unknown runtime store type: redis"):
            builder.build_runtime_tracker(config)


# ---------------------------------------------------------------------------
# Simple Builder Methods (delegation tests)
# ---------------------------------------------------------------------------


class TestSimpleBuilders:
    """Tests for builder methods that delegate to infrastructure constructors."""

    def test_build_message_bus(self, builder: InfrastructureBuilder) -> None:
        with patch(
            "taskforce.infrastructure.messaging.InMemoryMessageBus"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            result = builder.build_message_bus()
            mock_cls.assert_called_once()
            assert result is mock_cls.return_value

    def test_build_memory_store(self, builder: InfrastructureBuilder) -> None:
        with patch(
            "taskforce.infrastructure.memory.file_memory_store.FileMemoryStore"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            result = builder.build_memory_store(work_dir="/data")
            mock_cls.assert_called_once_with("/data")
            assert result is mock_cls.return_value

    def test_build_memory_store_default_work_dir(
        self, builder: InfrastructureBuilder
    ) -> None:
        with patch(
            "taskforce.infrastructure.memory.file_memory_store.FileMemoryStore"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            builder.build_memory_store()
            mock_cls.assert_called_once_with(".taskforce")

    def test_build_experience_store(self, builder: InfrastructureBuilder) -> None:
        with patch(
            "taskforce.infrastructure.memory.file_experience_store.FileExperienceStore"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            result = builder.build_experience_store(work_dir="/exp")
            mock_cls.assert_called_once_with("/exp")
            assert result is mock_cls.return_value

    def test_build_experience_store_default_work_dir(
        self, builder: InfrastructureBuilder
    ) -> None:
        with patch(
            "taskforce.infrastructure.memory.file_experience_store.FileExperienceStore"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            builder.build_experience_store()
            mock_cls.assert_called_once_with(".taskforce/experiences")

    def test_build_job_store(self, builder: InfrastructureBuilder) -> None:
        with patch(
            "taskforce.infrastructure.scheduler.job_store.FileJobStore"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            result = builder.build_job_store(work_dir="/jobs")
            mock_cls.assert_called_once_with(work_dir="/jobs")
            assert result is mock_cls.return_value

    def test_build_job_store_default_work_dir(
        self, builder: InfrastructureBuilder
    ) -> None:
        with patch(
            "taskforce.infrastructure.scheduler.job_store.FileJobStore"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            builder.build_job_store()
            mock_cls.assert_called_once_with(work_dir=".taskforce")

    def test_build_agent_registry(self, builder: InfrastructureBuilder) -> None:
        with (
            patch(
                "taskforce.infrastructure.persistence.file_agent_registry.FileAgentRegistry"
            ) as mock_cls,
            patch(
                "taskforce.application.infrastructure_builder.get_tool_registry"
            ) as mock_get_tr,
            patch(
                "taskforce.application.infrastructure_builder.get_base_path"
            ) as mock_bp,
        ):
            mock_cls.return_value = MagicMock()
            mock_get_tr.return_value = MagicMock()
            mock_bp.return_value = Path("/base")
            result = builder.build_agent_registry()
            mock_cls.assert_called_once_with(
                tool_mapper=mock_get_tr.return_value, base_path=Path("/base")
            )
            assert result is mock_cls.return_value

    def test_build_gateway_components(self, builder: InfrastructureBuilder) -> None:
        with patch(
            "taskforce.infrastructure.communication.gateway_registry.build_gateway_components"
        ) as mock_fn:
            mock_fn.return_value = MagicMock()
            result = builder.build_gateway_components(work_dir="/gw")
            mock_fn.assert_called_once_with(work_dir="/gw")
            assert result is mock_fn.return_value

    def test_build_gateway_components_default_work_dir(
        self, builder: InfrastructureBuilder
    ) -> None:
        with patch(
            "taskforce.infrastructure.communication.gateway_registry.build_gateway_components"
        ) as mock_fn:
            mock_fn.return_value = MagicMock()
            builder.build_gateway_components()
            mock_fn.assert_called_once_with(work_dir=".taskforce")

    def test_build_calendar_event_source(self, builder: InfrastructureBuilder) -> None:
        with patch(
            "taskforce.infrastructure.event_sources.calendar_source.CalendarEventSource"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            result = builder.build_calendar_event_source(
                poll_interval_seconds=60,
                lookahead_minutes=30,
                calendar_id="test@cal",
                credentials_file="/creds.json",
            )
            mock_cls.assert_called_once_with(
                poll_interval_seconds=60,
                lookahead_minutes=30,
                calendar_id="test@cal",
                credentials_file="/creds.json",
            )
            assert result is mock_cls.return_value

    def test_build_calendar_event_source_defaults(
        self, builder: InfrastructureBuilder
    ) -> None:
        with patch(
            "taskforce.infrastructure.event_sources.calendar_source.CalendarEventSource"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            builder.build_calendar_event_source()
            mock_cls.assert_called_once_with(
                poll_interval_seconds=300,
                lookahead_minutes=60,
                calendar_id="primary",
                credentials_file=None,
            )

    def test_build_webhook_event_source(self, builder: InfrastructureBuilder) -> None:
        with patch(
            "taskforce.infrastructure.event_sources.webhook_source.WebhookEventSource"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            result = builder.build_webhook_event_source()
            mock_cls.assert_called_once()
            assert result is mock_cls.return_value


# ---------------------------------------------------------------------------
# build_for_definition
# ---------------------------------------------------------------------------


class TestBuildForDefinition:
    """Tests for build_for_definition."""

    async def test_builds_all_components(
        self, builder: InfrastructureBuilder
    ) -> None:
        definition = MagicMock()
        definition.base_profile = "dev"
        definition.work_dir = "/work"
        definition.mcp_servers = []
        definition.mcp_tool_filter = None

        mock_sm = MagicMock()
        mock_llm = MagicMock()
        mock_policy = MagicMock()

        with (
            patch.object(
                builder, "load_profile_safe", return_value={"profile": "dev"}
            ) as mock_load,
            patch.object(
                builder, "build_state_manager", return_value=mock_sm
            ) as mock_build_sm,
            patch.object(
                builder, "build_llm_provider", return_value=mock_llm
            ) as mock_build_llm,
            patch.object(
                builder,
                "build_mcp_tools",
                new_callable=AsyncMock,
                return_value=([], []),
            ) as mock_build_mcp,
            patch.object(
                builder, "build_context_policy", return_value=mock_policy
            ) as mock_build_cp,
        ):
            sm, llm, tools, ctxs, policy = await builder.build_for_definition(
                definition
            )

            mock_load.assert_called_once_with("dev")
            mock_build_sm.assert_called_once_with(
                {"profile": "dev"}, work_dir_override="/work"
            )
            mock_build_llm.assert_called_once_with({"profile": "dev"})
            mock_build_mcp.assert_awaited_once_with([], tool_filter=None)
            mock_build_cp.assert_called_once_with({"profile": "dev"})

            assert sm is mock_sm
            assert llm is mock_llm
            assert tools == []
            assert ctxs == []
            assert policy is mock_policy

    async def test_build_for_definition_with_mcp_servers(
        self, builder: InfrastructureBuilder
    ) -> None:
        """MCP servers and tool filter are passed through correctly."""
        definition = MagicMock()
        definition.base_profile = "dev"
        definition.work_dir = None
        definition.mcp_servers = [MagicMock()]
        definition.mcp_tool_filter = ["tool_a", "tool_b"]

        mock_mcp_tool = MagicMock()
        mock_mcp_ctx = MagicMock()

        with (
            patch.object(
                builder, "load_profile_safe", return_value={}
            ),
            patch.object(
                builder, "build_state_manager", return_value=MagicMock()
            ),
            patch.object(
                builder, "build_llm_provider", return_value=MagicMock()
            ),
            patch.object(
                builder,
                "build_mcp_tools",
                new_callable=AsyncMock,
                return_value=([mock_mcp_tool], [mock_mcp_ctx]),
            ) as mock_build_mcp,
            patch.object(
                builder, "build_context_policy", return_value=MagicMock()
            ),
        ):
            _, _, tools, ctxs, _ = await builder.build_for_definition(definition)

            mock_build_mcp.assert_awaited_once_with(
                definition.mcp_servers, tool_filter=["tool_a", "tool_b"]
            )
            assert tools == [mock_mcp_tool]
            assert ctxs == [mock_mcp_ctx]
