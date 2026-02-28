"""
Infrastructure Builder

Extracts infrastructure building logic from AgentFactory into a dedicated
service. Handles creation of:
- State managers (file or database)
- LLM providers
- MCP tools and connections
- Context policies

Part of Phase 4 refactoring: Simplified AgentFactory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml

from taskforce.application.tool_registry import get_tool_registry
from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.core.utils.paths import get_base_path

if TYPE_CHECKING:
    from taskforce.core.domain.agent_definition import AgentDefinition, MCPServerConfig


logger = structlog.get_logger(__name__)


class InfrastructureBuilder:
    """
    Builder for infrastructure components.

    Responsible for creating infrastructure adapters based on configuration:
    - StateManager (file or database persistence)
    - LLMProvider (multi-provider via LiteLLM)
    - MCP tools (stdio or SSE connections)
    - ContextPolicy (conversation context management)
    """

    def __init__(self, config_dir: Path | str | None = None) -> None:
        """
        Initialize the infrastructure builder.

        Args:
            config_dir: Path to configuration directory. If None, uses
                       'src/taskforce/configs/' relative to project root.
                       Falls back to 'configs/' for backward compatibility.
        """
        if config_dir is None:
            base_path = get_base_path()
            # Try new location first, then fall back to old location for compatibility
            new_config_dir = base_path / "src" / "taskforce" / "configs"
            old_config_dir = base_path / "configs"
            if new_config_dir.exists():
                self.config_dir = new_config_dir
            elif old_config_dir.exists():
                self.config_dir = old_config_dir
            else:
                # Default to new location even if it doesn't exist yet
                self.config_dir = new_config_dir
        else:
            self.config_dir = Path(config_dir)

        self._logger = logger.bind(component="InfrastructureBuilder")

    # -------------------------------------------------------------------------
    # Profile Loading
    # -------------------------------------------------------------------------

    def load_profile(self, profile_name: str) -> dict[str, Any]:
        """
        Load a configuration profile from YAML file.

        Searches in:
        1. configs/{profile}.yaml (standard profiles)
        2. configs/custom/{profile}.yaml (custom agents as fallback)

        Args:
            profile_name: Profile name (e.g., "dev", "prod", "my-custom-agent")

        Returns:
            Configuration dictionary

        Raises:
            FileNotFoundError: If profile YAML not found in either location
        """
        # First try standard profile location
        profile_path = self.config_dir / f"{profile_name}.yaml"

        if not profile_path.exists():
            # Fallback: check if it's a custom agent
            custom_path = self.config_dir / "custom" / f"{profile_name}.yaml"
            if custom_path.exists():
                self._logger.debug(
                    "profile_using_custom_agent",
                    profile=profile_name,
                    custom_path=str(custom_path),
                )
                profile_path = custom_path
            else:
                raise FileNotFoundError(f"Profile not found: {profile_path} or {custom_path}")

        with open(profile_path) as f:
            config = yaml.safe_load(f)

        self._logger.debug(
            "profile_loaded",
            profile=profile_name,
            config_keys=list(config.keys()) if config else [],
        )
        return config or {}

    def load_profile_safe(self, profile_name: str) -> dict[str, Any]:
        """
        Load a configuration profile, returning empty dict if not found.

        Args:
            profile_name: Profile name

        Returns:
            Configuration dictionary or empty dict if not found
        """
        try:
            return self.load_profile(profile_name)
        except FileNotFoundError:
            self._logger.debug("profile_not_found_using_defaults", profile=profile_name)
            return {}

    # -------------------------------------------------------------------------
    # Agent Registry
    # -------------------------------------------------------------------------

    def build_agent_registry(self):
        """Build a FileAgentRegistry instance.

        Centralises the infrastructure import so that API-layer code
        does not need to reference infrastructure directly.

        Returns:
            FileAgentRegistry wired with the tool registry and base path.
        """
        from taskforce.infrastructure.persistence.file_agent_registry import (
            FileAgentRegistry,
        )

        return FileAgentRegistry(
            tool_mapper=get_tool_registry(),
            base_path=get_base_path(),
        )

    # -------------------------------------------------------------------------
    # State Manager
    # -------------------------------------------------------------------------

    def build_state_manager(
        self,
        config: dict[str, Any],
        work_dir_override: str | None = None,
    ) -> StateManagerProtocol:
        """
        Build state manager based on configuration.

        Args:
            config: Profile configuration dictionary
            work_dir_override: Optional override for work directory

        Returns:
            StateManager implementation (file-based or database)

        Raises:
            ValueError: If persistence type is unknown or database URL not found
        """
        persistence_config = config.get("persistence", {})
        persistence_type = persistence_config.get("type", "file")

        if persistence_type == "file":
            from taskforce.infrastructure.persistence.file_state_manager import (
                FileStateManager,
            )

            work_dir = work_dir_override or persistence_config.get("work_dir", ".taskforce")
            return FileStateManager(work_dir=work_dir)

        elif persistence_type == "database":
            from taskforce.infrastructure.persistence.db_state import DbStateManager

            db_url_env = persistence_config.get("db_url_env", "DATABASE_URL")
            db_url = os.getenv(db_url_env)

            if not db_url:
                raise ValueError(f"Database URL not found in environment variable: {db_url_env}")

            return DbStateManager(db_url=db_url)

        else:
            raise ValueError(f"Unknown persistence type: {persistence_type}")

    # -------------------------------------------------------------------------
    # LLM Provider
    # -------------------------------------------------------------------------

    def build_llm_provider(self, config: dict[str, Any]) -> LLMProviderProtocol:
        """
        Build LLM provider based on configuration.

        Always wraps the provider with an ``LLMRouter`` for dynamic per-call
        model selection.  Routing rules are loaded from ``llm_config.yaml``
        (the ``routing`` section), not from the profile YAML.  When no rules
        are configured the router acts as a transparent pass-through that
        maps strategy phase hints back to the default model.

        Args:
            config: Profile configuration dictionary

        Returns:
            LLM provider wrapped with an LLMRouter.
        """
        from taskforce.infrastructure.llm.litellm_service import LiteLLMService
        from taskforce.infrastructure.llm.llm_router import build_llm_router

        llm_config = config.get("llm", {})
        config_path = llm_config.get(
            "config_path", "src/taskforce/configs/llm_config.yaml"
        )

        # Resolve relative paths against base path (handles frozen executables)
        config_path_obj = Path(config_path)
        if not config_path_obj.is_absolute():
            resolved_path = get_base_path() / config_path

            # Backward compatibility: if old path doesn't exist, try new location
            if not resolved_path.exists() and config_path.startswith("configs/"):
                new_path = get_base_path() / "src" / "taskforce" / config_path
                if new_path.exists():
                    resolved_path = new_path
                    self._logger.debug(
                        "llm_config_path_migrated",
                        old_path=config_path,
                        new_path=str(new_path),
                    )

            config_path = str(resolved_path)

        provider = LiteLLMService(config_path=config_path)

        # Wrap with LLMRouter for dynamic model routing.
        # Routing config lives in llm_config.yaml (alongside model aliases).
        # Always wraps: when no routing rules are configured the router
        # acts as a transparent pass-through that maps strategy phase
        # hints (e.g. "reasoning", "planning") back to the default model.
        routing_config = getattr(provider, "routing_config", {})
        default_model = llm_config.get("default_model", getattr(provider, "default_model", "main"))
        return build_llm_router(provider, routing_config, default_model)

    # -------------------------------------------------------------------------
    # MCP Tools
    # -------------------------------------------------------------------------

    async def build_mcp_tools(
        self,
        mcp_servers: list[MCPServerConfig],
        tool_filter: list[str] | None = None,
    ) -> tuple[list[ToolProtocol], list[Any]]:
        """
        Build MCP tools from server configurations.

        Connects to configured MCP servers (stdio or SSE), fetches available
        tools, and wraps them in MCPToolWrapper.

        Args:
            mcp_servers: List of MCP server configurations
            tool_filter: Optional list of allowed MCP tool names (None = all)

        Returns:
            Tuple of (tools, contexts) where contexts are the connection
            contexts that must be kept alive for the tools to work
        """
        from taskforce.infrastructure.tools.mcp.connection_manager import (
            create_default_connection_manager,
        )

        if not mcp_servers:
            return [], []

        # Use centralized connection manager
        manager = create_default_connection_manager()
        return await manager.connect_all(mcp_servers, tool_filter=tool_filter)

    # -------------------------------------------------------------------------
    # Context Policy
    # -------------------------------------------------------------------------

    def build_context_policy(self, config: dict[str, Any]) -> ContextPolicy:
        """
        Build context policy from configuration.

        Args:
            config: Profile configuration dictionary

        Returns:
            ContextPolicy instance
        """
        context_config = config.get("context_policy")

        if context_config:
            self._logger.debug(
                "creating_context_policy_from_config",
                config=context_config,
            )
            return ContextPolicy.from_dict(context_config)
        else:
            self._logger.debug("using_conservative_default_context_policy")
            return ContextPolicy.conservative_default()

    # -------------------------------------------------------------------------
    # Communication Gateway
    # -------------------------------------------------------------------------

    def build_gateway_components(self, work_dir: str = ".taskforce"):
        """Build Communication Gateway infrastructure components.

        Centralises the extensions-infrastructure import so that API-layer
        code does not reference infrastructure directly.

        Args:
            work_dir: Working directory for conversation persistence.

        Returns:
            GatewayComponents dataclass with stores, senders, and adapters.
        """
        from taskforce.infrastructure.communication.gateway_registry import (
            build_gateway_components,
        )

        return build_gateway_components(work_dir=work_dir)

    # -------------------------------------------------------------------------
    # Event Sources (Butler)
    # -------------------------------------------------------------------------

    def build_calendar_event_source(
        self,
        poll_interval_seconds: int = 300,
        lookahead_minutes: int = 60,
        calendar_id: str = "primary",
        credentials_file: str | None = None,
    ) -> Any:
        """Build a CalendarEventSource instance.

        Centralises the infrastructure import so that API-layer code
        does not reference infrastructure directly.

        Args:
            poll_interval_seconds: Polling interval in seconds.
            lookahead_minutes: How far ahead to look for events.
            calendar_id: Google Calendar ID to poll.
            credentials_file: Path to Google credentials file.

        Returns:
            CalendarEventSource instance implementing EventSourceProtocol.
        """
        from taskforce.infrastructure.event_sources.calendar_source import (
            CalendarEventSource,
        )

        return CalendarEventSource(
            poll_interval_seconds=poll_interval_seconds,
            lookahead_minutes=lookahead_minutes,
            calendar_id=calendar_id,
            credentials_file=credentials_file,
        )

    def build_webhook_event_source(self) -> Any:
        """Build a WebhookEventSource instance.

        Centralises the infrastructure import so that API-layer code
        does not reference infrastructure directly.

        Returns:
            WebhookEventSource instance implementing EventSourceProtocol.
        """
        from taskforce.infrastructure.event_sources.webhook_source import (
            WebhookEventSource,
        )

        return WebhookEventSource()

    # -------------------------------------------------------------------------
    # Scheduler / Job Store (Butler)
    # -------------------------------------------------------------------------

    def build_job_store(self, work_dir: str = ".taskforce") -> Any:
        """Build a FileJobStore instance.

        Centralises the infrastructure import so that API-layer code
        does not reference infrastructure directly.

        Args:
            work_dir: Working directory for job persistence.

        Returns:
            FileJobStore instance.
        """
        from taskforce.infrastructure.scheduler.job_store import FileJobStore

        return FileJobStore(work_dir=work_dir)

    # -------------------------------------------------------------------------
    # Runtime Tracker
    # -------------------------------------------------------------------------

    def build_runtime_tracker(
        self,
        config: dict[str, Any],
        work_dir_override: str | None = None,
    ) -> Any:
        """Build runtime tracker based on configuration.

        Centralises the extensions-infrastructure import so that callers
        do not reference infrastructure directly.

        Args:
            config: Profile configuration dictionary.
            work_dir_override: Optional override for work directory.

        Returns:
            AgentRuntimeTracker or None if runtime tracking is disabled.

        Raises:
            ValueError: If store type is unknown.
        """
        runtime_config = config.get("runtime", {})
        if not runtime_config.get("enabled", False):
            return None

        runtime_work_dir = (
            runtime_config.get("work_dir")
            or work_dir_override
            or config.get("persistence", {}).get("work_dir", ".taskforce")
        )
        store_type = runtime_config.get("store", "file")

        if store_type == "memory":
            from taskforce.infrastructure.runtime import (
                AgentRuntimeTracker,
                InMemoryCheckpointStore,
                InMemoryHeartbeatStore,
            )

            return AgentRuntimeTracker(
                heartbeat_store=InMemoryHeartbeatStore(),
                checkpoint_store=InMemoryCheckpointStore(),
            )
        if store_type == "file":
            from taskforce.infrastructure.runtime import (
                AgentRuntimeTracker,
                FileCheckpointStore,
                FileHeartbeatStore,
            )

            return AgentRuntimeTracker(
                heartbeat_store=FileHeartbeatStore(runtime_work_dir),
                checkpoint_store=FileCheckpointStore(runtime_work_dir),
            )
        raise ValueError(f"Unknown runtime store type: {store_type}")

    # -------------------------------------------------------------------------
    # Message Bus
    # -------------------------------------------------------------------------

    def build_message_bus(self) -> Any:
        """Build an InMemoryMessageBus instance.

        Centralises the extensions-infrastructure import so that
        application-layer code does not reference extensions directly.

        Returns:
            InMemoryMessageBus instance implementing MessageBusProtocol.
        """
        from taskforce.infrastructure.messaging import InMemoryMessageBus

        return InMemoryMessageBus()

    # -------------------------------------------------------------------------
    # Combined Infrastructure
    # -------------------------------------------------------------------------

    async def build_for_definition(
        self,
        definition: AgentDefinition,
    ) -> tuple[
        StateManagerProtocol,
        LLMProviderProtocol,
        list[ToolProtocol],
        list[Any],
        ContextPolicy,
    ]:
        """
        Build all infrastructure components for an agent definition.

        Args:
            definition: Agent definition containing configuration

        Returns:
            Tuple of (state_manager, llm_provider, mcp_tools, mcp_contexts, context_policy)
        """
        # Load base profile configuration
        base_config = self.load_profile_safe(definition.base_profile)

        # Build state manager
        state_manager = self.build_state_manager(
            base_config,
            work_dir_override=definition.work_dir,
        )

        # Build LLM provider
        llm_provider = self.build_llm_provider(base_config)

        # Build MCP tools
        mcp_tools, mcp_contexts = await self.build_mcp_tools(
            definition.mcp_servers,
            tool_filter=definition.mcp_tool_filter,
        )

        # Build context policy
        context_policy = self.build_context_policy(base_config)

        return state_manager, llm_provider, mcp_tools, mcp_contexts, context_policy
