"""Application Layer - Agent Factory.

Dependency injection factory for creating Agent instances with infrastructure
adapters based on configuration profiles (dev/staging/prod).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from taskforce.core.domain.agent_definition import AgentDefinition

import aiofiles
import structlog
import yaml

from taskforce.application.planning_strategy_factory import select_planning_strategy
from taskforce.application.plugin_loader import PluginLoader
from taskforce.application.profile_loader import DEFAULT_TOOL_NAMES, ProfileLoader
from taskforce.application.skill_manager import (
    SkillManager,
    create_skill_manager_from_manifest,
)
from taskforce.application.system_prompt_assembler import SystemPromptAssembler
from taskforce.application.tool_builder import ToolBuilder
from taskforce.core.domain.agent import Agent
from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.domain.errors import ConfigError
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.runtime import AgentRuntimeTrackerProtocol
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.core.utils.paths import get_base_path


def _set_mcp_contexts(agent: Agent, mcp_contexts: list[Any]) -> None:
    """Store MCP contexts on an agent for lifecycle management.

    Uses setattr to avoid mypy errors since _mcp_contexts is a
    dynamic attribute consumed via getattr in LeanAgent.close().
    """
    agent._mcp_contexts = mcp_contexts


def _set_plugin_manifest(agent: Agent, manifest: Any) -> None:
    """Store plugin manifest on an agent for lifecycle management.

    Uses setattr to avoid mypy errors since _plugin_manifest is a
    dynamic attribute consumed via getattr in CLI commands.
    """
    agent._plugin_manifest = manifest


def _set_merged_config(agent: Agent, config: dict[str, Any]) -> None:
    """Store the merged profile config on an agent.

    This allows downstream consumers (e.g. the executor's consolidation
    initializer) to access the fully resolved config for plugin agents
    where the profile name alone is not loadable.
    """
    agent._merged_config = config


# Type for factory extension callbacks
FactoryExtensionCallback = Any  # Callable[[AgentFactory, dict, Agent], Agent]

# Global registry for factory extensions from plugins
_factory_extensions: list[FactoryExtensionCallback] = []


def register_factory_extension(extension: FactoryExtensionCallback) -> None:
    """Register a factory extension callback (called after agent creation)."""
    _factory_extensions.append(extension)


def unregister_factory_extension(extension: FactoryExtensionCallback) -> None:
    """Unregister a factory extension callback."""
    if extension in _factory_extensions:
        _factory_extensions.remove(extension)


def clear_factory_extensions() -> None:
    """Clear all registered factory extensions."""
    _factory_extensions.clear()


class AgentFactory:
    """Factory for creating Agent instances with dependency injection.

    Wires core domain objects with infrastructure adapters based on
    configuration profiles (dev/staging/prod).
    """

    def __init__(self, config_dir: str | None = None):
        """Initialize AgentFactory.

        Args:
            config_dir: Path to directory containing profile YAML files.
                       Defaults to ``src/taskforce/configs/``.
        """
        self.config_dir = self._resolve_config_dir(config_dir)
        self.logger = structlog.get_logger().bind(component="agent_factory")
        self.profile_loader = ProfileLoader(self.config_dir)
        self.prompt_assembler = SystemPromptAssembler()
        self._tool_builder = ToolBuilder(self)
        self._infra_builder: Any = None  # Lazy-initialised InfrastructureBuilder
        self._gateway: Any = None  # Optional CommunicationGateway for SendNotificationTool
        self._scheduler: Any = None  # Optional scheduler for ScheduleTool/ReminderTool
        self._auth_manager: Any = None  # Optional AuthManager for AuthTool

    def set_gateway(self, gateway: Any) -> None:
        """Set the communication gateway for SendNotificationTool injection.

        Args:
            gateway: CommunicationGateway instance.
        """
        self._gateway = gateway

    def set_scheduler(self, scheduler: Any) -> None:
        """Set the scheduler for ScheduleTool and ReminderTool injection.

        Args:
            scheduler: SchedulerService instance.
        """
        self._scheduler = scheduler

    def set_auth_manager(self, auth_manager: Any) -> None:
        """Set the auth manager for AuthTool injection.

        Args:
            auth_manager: AuthManager instance.
        """
        self._auth_manager = auth_manager

    def _ensure_auth_manager(self) -> Any:
        """Lazily create an AuthManager if none was explicitly set.

        Returns the existing or newly created AuthManager, or None if
        the required packages (cryptography) are not installed.
        """
        if self._auth_manager is not None:
            return self._auth_manager

        try:
            from taskforce.application.auth_manager import AuthManager
            from taskforce.infrastructure.auth.oauth2_device_flow import (
                OAuth2DeviceFlow,
            )

            auth_flows: dict[str, Any] = {"oauth2_device": OAuth2DeviceFlow()}
            try:
                from taskforce.infrastructure.auth.oauth2_auth_code_flow import (
                    OAuth2AuthCodeFlow,
                )

                auth_flows["oauth2_auth_code"] = OAuth2AuthCodeFlow()
            except ImportError:
                pass

            # Try to extract Google client credentials from legacy token file
            # so the authenticate tool can run device flows.
            provider_configs = self._load_google_provider_config()

            # Route token-store construction through the InfrastructureBuilder
            # so plugins (e.g. taskforce-enterprise) can install a
            # per-(tenant, user) backend via set_token_store_override.
            # Defaults to the legacy ``~/.taskforce/auth`` EncryptedTokenStore
            # when no override is installed.
            self._auth_manager = AuthManager(
                token_store=self.infra_builder.build_token_store(),
                auth_flows=auth_flows,
                gateway=self._gateway,
                provider_configs=provider_configs,
            )
            self.logger.info("auth_manager.auto_created")
        except ImportError:
            self.logger.debug("auth_manager.auto_create_skipped", reason="missing_deps")
        return self._auth_manager

    def _load_google_provider_config(self) -> dict[str, Any]:
        """Extract Google OAuth client credentials from legacy token file.

        Reads ``client_id`` and ``client_secret`` from the existing
        ``~/.taskforce/google_token.json`` so the ``authenticate`` tool
        can run device/auth-code flows without separate configuration.
        """
        import json
        from pathlib import Path

        provider_configs: dict[str, Any] = {}
        token_path = Path.home() / ".taskforce" / "google_token.json"
        if token_path.exists():
            try:
                data = json.loads(token_path.read_text(encoding="utf-8"))
                client_id = data.get("client_id", "")
                client_secret = data.get("client_secret", "")
                if client_id and client_secret:
                    provider_configs["google"] = {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "default_flow": "oauth2_auth_code",
                        "default_scopes": [
                            "https://www.googleapis.com/auth/gmail.modify",
                            "https://www.googleapis.com/auth/calendar",
                            "https://www.googleapis.com/auth/drive.readonly",
                        ],
                    }
                    self.logger.info("auth_manager.google_config_loaded")
            except Exception:
                pass
        return provider_configs

    @property
    def infra_builder(self) -> Any:
        """Cached ``InfrastructureBuilder`` instance.

        Lazily created on first access to avoid import-time overhead.
        """
        if self._infra_builder is None:
            from taskforce.application.infrastructure_builder import InfrastructureBuilder

            self._infra_builder = InfrastructureBuilder(self.config_dir)
        return self._infra_builder

    @staticmethod
    def _resolve_config_dir(config_dir: str | None) -> Path:
        """Resolve the configuration directory path."""
        if config_dir is not None:
            return Path(config_dir)

        base_path = get_base_path()
        new_config_dir = base_path / "src" / "taskforce" / "configs"
        old_config_dir = base_path / "configs"
        if new_config_dir.exists():
            return new_config_dir
        if old_config_dir.exists():
            return old_config_dir
        return new_config_dir

    def _apply_extensions(self, config: dict[str, Any], agent: Agent) -> Agent:
        """Apply registered factory extensions to the agent."""
        for extension in _factory_extensions:
            try:
                result = extension(self, config, agent)
                if result is not None:
                    agent = result
                self.logger.debug(
                    "factory_extension_applied",
                    extension=str(extension),
                )
            except Exception as e:
                self.logger.warning(
                    "factory_extension_failed",
                    extension=str(extension),
                    error=str(e),
                    error_type=type(e).__name__,
                )
        return agent

    # -------------------------------------------------------------------------
    # New Unified API (Phase 4 Refactoring)
    # -------------------------------------------------------------------------

    async def create(
        self,
        definition: AgentDefinition,
        user_context: dict[str, Any] | None = None,
        base_config_override: dict[str, Any] | None = None,
    ) -> Agent:
        """Create an Agent from a unified AgentDefinition.

        Args:
            definition: Unified agent definition containing all configuration.
            user_context: Optional user context for RAG tools.
            base_config_override: Optional pre-loaded base profile config.

        Returns:
            Agent instance with injected dependencies.
        """
        self.logger.info(
            "creating_agent_from_definition",
            agent_id=definition.agent_id,
            source=definition.source.value,
            base_profile=definition.base_profile,
            specialist=definition.specialist,
            tools=definition.tools,
            has_mcp_servers=definition.has_mcp_servers,
            has_custom_prompt=definition.has_custom_prompt,
        )

        base_config = await self._resolve_base_config(definition, base_config_override)
        infra = self._build_infrastructure(base_config, definition)
        all_tools = await self._collect_tools_for_definition(
            definition, base_config, infra, user_context
        )

        sub_agents = base_config.get("sub_agents")
        system_prompt = self.prompt_assembler.assemble(
            all_tools,
            specialist=definition.specialist,
            custom_prompt=definition.system_prompt if definition.has_custom_prompt else None,
            sub_agents=sub_agents,
        )
        agent_settings = self._extract_agent_settings(
            base_config,
            definition,
            definition.planning_strategy,
            definition.planning_strategy_params,
        )

        self.logger.debug(
            "agent_created",
            agent_id=definition.agent_id,
            tools_count=len(all_tools),
            tool_names=[t.name for t in all_tools],
            model_alias=agent_settings["model_alias"],
            planning_strategy=agent_settings["planning_strategy"].name,
        )

        skill_manager = self._build_default_skill_manager(
            project_root=definition.work_dir
        )
        activate_skill_tool = self._maybe_add_skill_tool_for_profile(skill_manager, all_tools)
        if activate_skill_tool is not None:
            # Re-assemble system prompt to include new tool description
            system_prompt = self.prompt_assembler.assemble(
                all_tools,
                specialist=definition.specialist,
                custom_prompt=definition.system_prompt if definition.has_custom_prompt else None,
                sub_agents=sub_agents,
            )

        context_mgmt = base_config.get("context_management", {})
        agent = self._instantiate_agent(
            infra=infra,
            all_tools=all_tools,
            system_prompt=system_prompt,
            settings=agent_settings,
            skill_manager=skill_manager,
            summary_threshold=context_mgmt.get("summary_threshold"),
            compression_trigger=context_mgmt.get("compression_trigger"),
            max_input_tokens=context_mgmt.get("max_input_tokens"),
            agent_id=definition.agent_id or definition.specialist or definition.base_profile,
        )

        if activate_skill_tool is not None:
            activate_skill_tool.set_agent_ref(agent)

        _set_mcp_contexts(agent, infra["mcp_contexts"])
        _set_merged_config(agent, base_config)
        return self._apply_extensions(base_config, agent)

    async def _resolve_base_config(
        self,
        definition: AgentDefinition,
        base_config_override: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Resolve the base configuration for a definition."""
        if base_config_override:
            return base_config_override

        return self.infra_builder.load_profile_safe(definition.base_profile)

    def _build_infrastructure(
        self,
        base_config: dict[str, Any],
        definition: AgentDefinition,
    ) -> dict[str, Any]:
        """Build core infrastructure components (state manager, LLM, runtime, wiki).

        Returns:
            Dict with keys: state_manager, llm_provider, context_policy,
            runtime_tracker, wiki_store, wiki_context_config,
            mcp_contexts (populated later).
        """
        ib = self.infra_builder
        wiki_store, wiki_context_config = self._build_wiki_injection(
            base_config, work_dir_override=definition.work_dir
        )
        work_dir = definition.work_dir or base_config.get("persistence", {}).get(
            "work_dir", ".taskforce"
        )
        return {
            "state_manager": ib.build_state_manager(
                base_config, work_dir_override=definition.work_dir
            ),
            "llm_provider": ib.build_llm_provider(base_config),
            "context_policy": ib.build_context_policy(base_config),
            "runtime_tracker": self._create_runtime_tracker(
                base_config, work_dir_override=definition.work_dir
            ),
            "model_alias": base_config.get("llm", {}).get("default_model", "main"),
            "wiki_store": wiki_store,
            "wiki_context_config": wiki_context_config,
            "tool_result_store": self._build_tool_result_store(work_dir),
            "mcp_contexts": [],
        }

    def _build_wiki_injection(
        self,
        config: dict[str, Any],
        work_dir_override: str | None = None,
    ) -> tuple[Any, Any]:
        """Build wiki store and context config for auto-injection.

        Returns ``(wiki_store, wiki_context_config)`` — both ``None`` when
        the agent has no ``wiki`` tool configured.
        """
        from taskforce.core.domain.lean_agent_components.wiki_context_loader import (
            WikiContextConfig,
        )

        tool_names = [
            (t if isinstance(t, str) else t.get("name", "")) for t in config.get("tools", [])
        ]
        if "wiki" not in tool_names:
            return None, None

        # Route through InfrastructureBuilder so the wiki store override
        # (installed by enterprise plugin for per-tenant/user scoping) is
        # consulted. Without an override this falls back to a flat
        # FileWikiStore at ``<work_dir>/memory/wiki`` — bit-for-bit
        # single-tenant behaviour.
        work_dir = work_dir_override or config.get("persistence", {}).get(
            "work_dir", ".taskforce"
        )
        wiki_store = self.infra_builder.build_wiki_store(work_dir=work_dir)
        injection_cfg = config.get("wiki", {}).get("context_injection")
        wiki_context_config = (
            WikiContextConfig.from_dict(injection_cfg) if injection_cfg else WikiContextConfig()
        )
        return wiki_store, wiki_context_config

    def _build_tool_result_store(self, work_dir: str) -> Any:
        """Build a FileToolResultStore for caching large tool outputs.

        Routed through ``InfrastructureBuilder`` so enterprise plugins
        can install a per-(tenant, user) override via
        ``set_tool_result_store_override`` (issue #196). Caching
        across users is a privacy leak — A's ``python`` result must
        not be served to B even if the args look identical.
        """
        return self.infra_builder.build_tool_result_store(work_dir=work_dir)

    async def _collect_tools_for_definition(
        self,
        definition: AgentDefinition,
        base_config: dict[str, Any],
        infra: dict[str, Any],
        user_context: dict[str, Any] | None,
    ) -> list[ToolProtocol]:
        """Collect all tools (native, plugin, MCP, sub-agent) for a definition."""
        from taskforce.application.tool_registry import ToolRegistry
        from taskforce.core.domain.agent_definition import AgentSource

        infra_builder = self.infra_builder
        llm_provider = infra["llm_provider"]

        mcp_tools, mcp_contexts = await infra_builder.build_mcp_tools(
            definition.mcp_servers, tool_filter=definition.mcp_tool_filter
        )
        infra["mcp_contexts"] = mcp_contexts

        wiki_store_dir = ToolBuilder.resolve_wiki_store_dir(
            base_config, work_dir_override=definition.work_dir
        )

        # Auto-create AuthManager when auth-aware tools are requested.
        _AUTH_TOOLS = {"authenticate", "gmail", "calendar", "google_drive"}
        requested_names = {t if isinstance(t, str) else t.get("type", "") for t in definition.tools}
        if requested_names & _AUTH_TOOLS:
            self._ensure_auth_manager()

        from taskforce.application.acp_service import build_acp_runtime_for_tools

        acp_runtime = build_acp_runtime_for_tools(base_config)
        tool_registry = ToolRegistry(
            llm_provider=llm_provider,
            user_context=user_context,
            wiki_store_dir=wiki_store_dir,
            gateway=self._gateway,
            notification_defaults=base_config.get("notifications"),
            scheduler=self._scheduler,
            auth_manager=self._auth_manager,
            tool_result_store=infra.get("tool_result_store"),
            acp_runtime=acp_runtime,
        )
        self._tool_builder.set_resolver(tool_registry)
        native_tools = tool_registry.resolve(definition.tools)
        self._add_orchestration_tool(native_tools, base_config)
        self._add_sub_agent_tools(native_tools, definition.sub_agent_specs)

        plugin_tools: list[ToolProtocol] = []
        if definition.source == AgentSource.PLUGIN and definition.plugin_path:
            plugin_tools = await self._load_plugin_tools_for_definition(
                definition, llm_provider, base_config
            )

        return plugin_tools + native_tools + mcp_tools

    def _add_orchestration_tool(self, tools: list[ToolProtocol], config: dict[str, Any]) -> None:
        """Add orchestration tool to tool list if enabled and not duplicate."""
        orchestration_tool = self._tool_builder.build_orchestration_tool(config)
        if orchestration_tool and not any(t.name == orchestration_tool.name for t in tools):
            tools.append(orchestration_tool)

    def _add_sub_agent_tools(
        self,
        tools: list[ToolProtocol],
        sub_agent_specs: list[dict[str, Any]],
    ) -> None:
        """Instantiate and add sub-agent and parallel-agent tools from definition specs."""
        for spec in sub_agent_specs:
            if spec.get("type") == "parallel_agent":
                tool = self._tool_builder.instantiate_parallel_agent_tool(spec)
            else:
                tool = self._tool_builder.instantiate_sub_agent_tool(spec)
            if tool:
                tools.append(tool)

    def _extract_agent_settings(
        self,
        config: dict[str, Any],
        definition: AgentDefinition | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Extract agent settings (max_steps, strategy, etc.) from config and definition."""
        agent_config = config.get("agent", {})
        def_max_steps = definition.max_steps if definition else None
        max_steps = def_max_steps or agent_config.get("max_steps")
        strategy_name = planning_strategy or agent_config.get("planning_strategy")
        strategy_params = planning_strategy_params or agent_config.get("planning_strategy_params")
        return {
            "max_steps": max_steps,
            "max_parallel_tools": agent_config.get("max_parallel_tools"),
            "planning_strategy": select_planning_strategy(strategy_name, strategy_params),
            "model_alias": config.get("llm", {}).get("default_model", "main"),
            "tool_result_store_threshold": agent_config.get("tool_result_store_threshold"),
            "tool_message_max_chars": agent_config.get("tool_message_max_chars"),
            "assistant_message_max_chars": agent_config.get("assistant_message_max_chars"),
            "approval_bypass_tools": agent_config.get("approval_bypass_tools"),
            "react_no_progress_threshold": agent_config.get("react_no_progress_threshold"),
            "react_signature_repeat_threshold": agent_config.get(
                "react_signature_repeat_threshold"
            ),
        }

    def _instantiate_agent(
        self,
        *,
        infra: dict[str, Any],
        all_tools: list[ToolProtocol],
        system_prompt: str,
        settings: dict[str, Any],
        skill_manager: Any | None = None,
        summary_threshold: int | None = None,
        compression_trigger: int | None = None,
        max_input_tokens: int | None = None,
        agent_id: str | None = None,
    ) -> Agent:
        """Create an Agent instance from resolved infrastructure and settings."""
        agent_logger = structlog.get_logger().bind(
            component="agent",
            agent_id=agent_id or "default",
        )
        return Agent(
            state_manager=infra["state_manager"],
            llm_provider=infra["llm_provider"],
            tools=all_tools,
            logger=agent_logger,
            system_prompt=system_prompt,
            model_alias=settings["model_alias"],
            context_policy=infra["context_policy"],
            max_steps=settings["max_steps"],
            max_parallel_tools=settings["max_parallel_tools"],
            planning_strategy=settings["planning_strategy"],
            runtime_tracker=infra["runtime_tracker"],
            skill_manager=skill_manager,
            summary_threshold=summary_threshold,
            compression_trigger=compression_trigger,
            max_input_tokens=max_input_tokens,
            wiki_store=infra.get("wiki_store"),
            wiki_context_config=infra.get("wiki_context_config"),
            tool_result_store=infra.get("tool_result_store"),
            tool_result_store_threshold=settings.get("tool_result_store_threshold"),
            tool_message_max_chars=settings.get("tool_message_max_chars"),
            assistant_message_max_chars=settings.get("assistant_message_max_chars"),
            approval_bypass_tools=settings.get("approval_bypass_tools"),
            react_no_progress_threshold=settings.get("react_no_progress_threshold"),
            react_signature_repeat_threshold=settings.get("react_signature_repeat_threshold"),
        )

    async def _load_plugin_tools_for_definition(
        self,
        definition: AgentDefinition,
        llm_provider: LLMProviderProtocol,
        base_config: dict[str, Any] | None = None,
    ) -> list[ToolProtocol]:
        """Load plugin tools for a plugin-source agent definition."""
        if not definition.plugin_path:
            return []

        plugin_loader = PluginLoader()
        manifest = plugin_loader.discover_plugin(definition.plugin_path)

        # Load plugin config for tool params and embedding service
        plugin_config = plugin_loader.load_config(manifest)
        tool_configs = plugin_config.get("tools", [])

        # Create embedding service from plugin config if available
        embedding_service = self._create_embedding_service(
            plugin_config.get("embeddings"), manifest
        )

        plugin_tools = plugin_loader.load_tools(
            manifest,
            tool_configs=tool_configs,
            llm_provider=llm_provider,
            embedding_service=embedding_service,
        )
        self.logger.debug(
            "plugin_tools_loaded",
            plugin_path=definition.plugin_path,
            tools=[t.name for t in plugin_tools],
            has_embedding_service=embedding_service is not None,
        )
        return plugin_tools

    # -------------------------------------------------------------------------
    # Legacy API (maintained for backwards compatibility)
    # -------------------------------------------------------------------------

    async def create_agent(
        self,
        *,
        profile: str | None = None,
        # Option 1: Config file path
        config: str | None = None,
        # Option 2: Inline parameters
        system_prompt: str | None = None,
        tools: list[str] | None = None,
        llm: dict[str, Any] | None = None,
        persistence: dict[str, Any] | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        max_steps: int | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
        context_policy: dict[str, Any] | None = None,
        # Shared optional parameters
        work_dir: str | None = None,
        user_context: dict[str, Any] | None = None,
        specialist: str | None = None,
    ) -> Agent:
        """Create an Agent instance.

        Supports two mutually exclusive modes: config file (``config`` or
        ``profile``) **or** inline parameters.  Mixing both raises ``ValueError``.

        Args:
            profile: Profile name to load from configs/{profile}.yaml.
            config: Path to YAML configuration file.
            system_prompt: Custom system prompt for the agent.
            tools: List of tool names to enable.
            llm: LLM configuration dict.
            persistence: Persistence configuration.
            mcp_servers: List of MCP server configurations.
            max_steps: Maximum execution steps for the agent.
            planning_strategy: Planning strategy name.
            planning_strategy_params: Parameters for the planning strategy.
            context_policy: Context policy configuration dict.
            work_dir: Override for work directory (applies to both modes).
            user_context: User context for RAG tools.
            specialist: Specialist profile.

        Returns:
            Agent instance with injected dependencies.

        Raises:
            ValueError: If both config and inline parameters are provided.
            FileNotFoundError: If config file not found.
        """
        self._validate_create_agent_params(
            profile,
            config,
            system_prompt,
            tools,
            llm,
            persistence,
            mcp_servers,
            max_steps,
            context_policy,
        )
        return await self._dispatch_create_agent(
            profile=profile,
            config=config,
            system_prompt=system_prompt,
            tools=tools,
            llm=llm,
            persistence=persistence,
            mcp_servers=mcp_servers,
            max_steps=max_steps,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            context_policy=context_policy,
            work_dir=work_dir,
            user_context=user_context,
            specialist=specialist,
        )

    @staticmethod
    def _validate_create_agent_params(
        profile: str | None,
        config: str | None,
        system_prompt: str | None,
        tools: list[str] | None,
        llm: dict[str, Any] | None,
        persistence: dict[str, Any] | None,
        mcp_servers: list[dict[str, Any]] | None,
        max_steps: int | None,
        context_policy: dict[str, Any] | None,
    ) -> None:
        """Validate mutually exclusive parameter groups for create_agent."""
        has_inline_params = any(
            [
                system_prompt is not None,
                tools is not None,
                llm is not None,
                persistence is not None,
                mcp_servers is not None,
                max_steps is not None,
                context_policy is not None,
            ]
        )

        if profile and config:
            raise ValueError(
                "Cannot use 'profile' with 'config'. "
                "Provide either a profile name or a config file path."
            )
        if profile and has_inline_params:
            raise ValueError(
                "Cannot use 'profile' with inline parameters. "
                "Provide either a profile name or inline parameters."
            )
        if config and has_inline_params:
            raise ValueError(
                "Cannot use 'config' with inline parameters. "
                "Either provide a config file path OR inline parameters, not both."
            )

    async def _dispatch_create_agent(
        self,
        *,
        profile: str | None,
        config: str | None,
        system_prompt: str | None,
        tools: list[str] | None,
        llm: dict[str, Any] | None,
        persistence: dict[str, Any] | None,
        mcp_servers: list[dict[str, Any]] | None,
        max_steps: int | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
        context_policy: dict[str, Any] | None,
        work_dir: str | None,
        user_context: dict[str, Any] | None,
        specialist: str | None,
    ) -> Agent:
        """Dispatch to the appropriate agent creation method based on params."""
        if profile:
            profile_config = self._load_profile(profile)
            return await self._create_agent_from_profile_config(
                profile=profile,
                config=profile_config,
                work_dir=work_dir,
                user_context=user_context,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
            )

        if config:
            return await self._create_agent_from_config_file(
                config_path=config,
                work_dir=work_dir,
                user_context=user_context,
                planning_strategy=planning_strategy,
                planning_strategy_params=planning_strategy_params,
            )

        return await self._create_agent_from_inline_params(
            system_prompt=system_prompt,
            tools=tools,
            llm=llm,
            persistence=persistence,
            mcp_servers=mcp_servers,
            max_steps=max_steps,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            context_policy=context_policy,
            work_dir=work_dir,
            user_context=user_context,
            specialist=specialist,
        )

    def _extract_tool_names(self, tools_config: list[Any]) -> list[str]:
        """Extract tool names from mixed config entries (excludes sub_agent specs)."""
        from taskforce.core.domain.agent_definition import _class_name_to_tool_name

        tool_names: list[str] = []
        for tool_entry in tools_config:
            if isinstance(tool_entry, str):
                tool_names.append(tool_entry)
            elif isinstance(tool_entry, dict):
                name = self._resolve_dict_tool_name(tool_entry)
                if name:
                    tool_names.append(
                        _class_name_to_tool_name(name)
                        if (name.endswith("Tool") or any(c.isupper() for c in name))
                        else name.lower()
                    )
        return tool_names

    @staticmethod
    def _resolve_dict_tool_name(tool_entry: dict[str, Any]) -> str | None:
        """Resolve a tool name from a dict config entry, skipping sub-agents."""
        if tool_entry.get("type") in {"sub_agent", "agent", "parallel_agent"}:
            return None
        name = tool_entry.get("name") or tool_entry.get("type", "")
        return name if name else None

    def _extract_sub_agent_specs(self, tools_config: list[Any]) -> list[dict[str, Any]]:
        """Extract sub-agent and parallel-agent tool specs from mixed config entries."""
        return [
            entry
            for entry in tools_config
            if isinstance(entry, dict)
            and entry.get("type") in {"sub_agent", "agent", "parallel_agent"}
        ]

    def _build_definition_from_config(
        self,
        profile_name: str,
        config: dict[str, Any],
        work_dir: str | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
        config_dir: Path | None = None,
    ) -> AgentDefinition:
        """Build AgentDefinition from a loaded profile config.

        Args:
            profile_name: Name of the profile.
            config: Parsed YAML configuration.
            work_dir: Override working directory.
            planning_strategy: Override planning strategy.
            planning_strategy_params: Override planning strategy parameters.
            config_dir: Directory containing the config file, used to resolve
                relative ``plugin_path`` values. If None, relative paths are
                resolved against the current working directory.
        """
        from taskforce.core.domain.agent_definition import (
            AgentDefinition,
            AgentSource,
            MCPServerConfig,
        )

        tools_config = config.get("tools", [])
        mcp_servers_config = config.get("mcp_servers", [])
        agent_config = config.get("agent", {})

        # Determine source and plugin_path: if the config declares a
        # plugin_path, treat this as a plugin agent so the PluginLoader
        # discovers and instantiates the plugin's tools.
        raw_plugin_path = config.get("plugin_path")
        if raw_plugin_path:
            source = AgentSource.PLUGIN
            plugin_path_obj = Path(raw_plugin_path)
            if not plugin_path_obj.is_absolute():
                base = config_dir or Path.cwd()
                plugin_path_obj = (base / plugin_path_obj).resolve()
            plugin_path: str | None = str(plugin_path_obj)
        else:
            source = AgentSource.PROFILE
            plugin_path = None

        return AgentDefinition(
            agent_id=f"config-{profile_name}",
            name=f"Config Agent ({profile_name})",
            source=source,
            specialist=config.get("specialist"),
            base_profile=profile_name,
            work_dir=work_dir,
            tools=self._extract_tool_names(tools_config),
            sub_agent_specs=self._extract_sub_agent_specs(tools_config),
            mcp_servers=(
                [MCPServerConfig.from_dict(server) for server in mcp_servers_config]
                if mcp_servers_config
                else []
            ),
            planning_strategy=planning_strategy or agent_config.get("planning_strategy"),
            planning_strategy_params=(
                planning_strategy_params or agent_config.get("planning_strategy_params")
            ),
            max_steps=agent_config.get("max_steps"),
            system_prompt=config.get("system_prompt"),
            plugin_path=plugin_path,
        )

    async def _create_agent_from_profile_config(
        self,
        profile: str,
        config: dict[str, Any],
        work_dir: str | None,
        user_context: dict[str, Any] | None,
        planning_strategy: str | None,
        planning_strategy_params: dict[str, Any] | None,
    ) -> Agent:
        """Create Agent from an in-memory profile configuration."""
        self.logger.info("creating_agent_from_profile", profile=profile)
        definition = self._build_definition_from_config(
            profile_name=config.get("profile", profile),
            config=config,
            work_dir=work_dir,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
        )
        return await self.create(
            definition,
            user_context=user_context,
            base_config_override=config,
        )

    async def _create_agent_from_config_file(
        self,
        config_path: str,
        work_dir: str | None = None,
        user_context: dict[str, Any] | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
    ) -> Agent:
        """Create Agent from a config file (``.yaml`` or ``.agent.md``)."""
        config_path_obj = self._resolve_config_path(config_path)
        config = await self._load_config_file(config_path_obj)

        self.logger.info(
            "creating_agent_from_config_file",
            config_path=str(config_path_obj),
        )

        profile_name = config.get("profile", config_path_obj.stem)
        definition = self._build_definition_from_config(
            profile_name=profile_name,
            config=config,
            work_dir=work_dir,
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            config_dir=config_path_obj.parent,
        )
        # Pass the loaded config as base_config_override so sections the
        # AgentDefinition doesn't model (notifications, memory, context_policy,
        # logging, …) still reach downstream builders. Without this,
        # _resolve_base_config falls back to load_profile_safe(profile_name)
        # which returns defaults and silently drops these settings.
        return await self.create(
            definition,
            user_context=user_context,
            base_config_override=config,
        )

    def _resolve_config_path(self, config_path: str) -> Path:
        """Resolve a config name or path to an absolute file path.

        Probes, for each candidate directory:
        ``{name}.agent.md`` → ``{name}.yaml`` → verbatim ``{name}``.
        Candidate directories are: the factory's ``config_dir``, the current
        working directory, and every ``agents/*/configs/`` package dir
        (including their ``custom/`` subfolder).
        """
        config_path_obj = Path(config_path)
        if not config_path_obj.is_absolute():

            def _probe(base: Path, name: str) -> list[Path]:
                return [
                    base / f"{name}.agent.md",
                    base / f"{name}.yaml",
                    base / name,
                ]

            candidates: list[Path] = _probe(self.config_dir, config_path) + [
                Path(f"{config_path}.agent.md"),
                Path(f"{config_path}.yaml"),
            ]

            # Also search agent package config directories (agents/*/configs/).
            agents_dir = get_base_path() / "agents"
            if agents_dir.is_dir():
                for agent_dir in agents_dir.iterdir():
                    agent_configs = agent_dir / "configs"
                    if agent_configs.is_dir():
                        candidates.extend(_probe(agent_configs, config_path))
                        candidates.extend(_probe(agent_configs / "custom", config_path))

            for candidate in candidates:
                if candidate.exists():
                    config_path_obj = candidate
                    break

        if not config_path_obj.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        return config_path_obj

    async def _load_config_file(self, path: Path) -> dict[str, Any]:
        """Load either a ``.agent.md`` or a YAML config file into a dict."""
        if path.name.endswith(".agent.md"):
            return self._load_agent_md_config(path)
        return await self._load_yaml_config(path)

    def _load_agent_md_config(self, path: Path) -> dict[str, Any]:
        """Load an ``.agent.md`` file with framework defaults + preset resolution."""
        from taskforce.application.agent_file_loader import (
            agent_file_to_config,
            load_agent_md,
        )

        agent_file = load_agent_md(path)
        preset_dirs = self._discover_preset_dirs()
        defaults = self._load_framework_defaults()
        return agent_file_to_config(
            agent_file,
            preset_dirs=preset_dirs,
            defaults=defaults,
        )

    def _discover_preset_dirs(self) -> list[Path]:
        """Preset directories searched when resolving ``extends:`` references."""
        dirs: list[Path] = []
        primary = self.config_dir / "presets"
        if primary.is_dir():
            dirs.append(primary)
        agents_dir = get_base_path() / "agents"
        if agents_dir.is_dir():
            for agent_dir in agents_dir.iterdir():
                presets = agent_dir / "configs" / "presets"
                if presets.is_dir():
                    dirs.append(presets)
        return dirs

    def _load_framework_defaults(self) -> dict[str, Any]:
        """Load ``{config_dir}/defaults.yaml`` or an empty dict."""
        defaults_path = self.config_dir / "defaults.yaml"
        if not defaults_path.is_file():
            return {}
        with open(defaults_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}

    async def _load_yaml_config(self, path: Path) -> dict[str, Any]:
        """Load and parse a YAML config file asynchronously."""
        try:
            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()
            config = yaml.safe_load(content)
        except yaml.YAMLError as e:
            self.logger.error(
                "yaml_parse_failed",
                config_path=str(path),
                error=str(e),
            )
            raise ConfigError(
                f"Failed to parse YAML config file: {path}",
                details={"path": str(path), "error": str(e)},
            ) from e
        except OSError as e:
            self.logger.error(
                "config_file_read_failed",
                config_path=str(path),
                error=str(e),
            )
            raise ConfigError(
                f"Failed to read config file: {path}",
                details={"path": str(path), "error": str(e)},
            ) from e

        if not isinstance(config, dict):
            raise ConfigError(
                f"Config file must contain a YAML mapping, got {type(config).__name__}",
                details={"path": str(path)},
            )
        return config

    async def _create_agent_from_inline_params(
        self,
        system_prompt: str | None = None,
        tools: list[str] | None = None,
        llm: dict[str, Any] | None = None,
        persistence: dict[str, Any] | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        max_steps: int | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
        context_policy: dict[str, Any] | None = None,
        work_dir: str | None = None,
        user_context: dict[str, Any] | None = None,
        specialist: str | None = None,
    ) -> Agent:
        """Create Agent from inline parameters.

        Builds an ``AgentDefinition`` from the inline arguments and delegates
        to :meth:`create`, so there is a single agent construction pipeline.
        """
        from taskforce.core.domain.agent_definition import (
            AgentDefinition,
            AgentSource,
            MCPServerConfig,
        )

        self.logger.info(
            "creating_agent_from_inline_params",
            has_system_prompt=system_prompt is not None,
            tools=tools,
            specialist=specialist,
        )

        default_config = self.profile_loader.get_defaults()

        effective_persistence = persistence or default_config.get(
            "persistence", {"type": "file", "work_dir": ".taskforce"}
        )
        if work_dir:
            effective_persistence = {**effective_persistence, "work_dir": work_dir}

        effective_llm = llm or default_config.get(
            "llm",
            {
                "config_path": "src/taskforce/configs/llm_config.yaml",
                "default_model": "main",
            },
        )

        agent_defaults = default_config.get("agent", {})
        effective_tools = tools if tools is not None else list(DEFAULT_TOOL_NAMES)

        # Inline callers never provide a YAML profile; the override carries
        # every section `create()` would otherwise load from disk.
        base_config_override: dict[str, Any] = {
            "persistence": effective_persistence,
            "llm": effective_llm,
            "context_policy": context_policy or default_config.get("context_policy"),
            "tools": effective_tools,
            "mcp_servers": mcp_servers or [],
            "agent": {
                "max_steps": max_steps or agent_defaults.get("max_steps", 30),
                "max_parallel_tools": agent_defaults.get("max_parallel_tools"),
                "planning_strategy": planning_strategy,
                "planning_strategy_params": planning_strategy_params,
                # Carry context-engineering caps from defaults so
                # programmatic ``create_agent(...)`` callers inherit
                # the same behaviour as profile-based agents (and
                # operators can tune the defaults globally).
                "tool_result_store_threshold": agent_defaults.get("tool_result_store_threshold"),
                "tool_message_max_chars": agent_defaults.get("tool_message_max_chars"),
                "assistant_message_max_chars": agent_defaults.get("assistant_message_max_chars"),
                "approval_bypass_tools": agent_defaults.get("approval_bypass_tools"),
                "react_no_progress_threshold": agent_defaults.get(
                    "react_no_progress_threshold"
                ),
                "react_signature_repeat_threshold": agent_defaults.get(
                    "react_signature_repeat_threshold"
                ),
            },
        }

        definition = AgentDefinition(
            agent_id=f"inline-{specialist or 'agent'}",
            name=f"Inline Agent ({specialist or 'default'})",
            source=AgentSource.PROFILE,
            specialist=specialist,
            # Inline-Agent ohne Profil-Bezug: "default" ist die framework-
            # eigene Fallback-Profile (src/taskforce/configs/default.yaml) und
            # immer verfügbar. Früher stand hier "butler" — das hat auf
            # Setups ohne taskforce-butler-Package Post-Mission-Learning-
            # Warnings produziert ("Profile 'butler' not found").
            base_profile="default",
            work_dir=work_dir,
            tools=effective_tools,
            mcp_servers=[MCPServerConfig.from_dict(s) for s in (mcp_servers or [])],
            planning_strategy=planning_strategy,
            planning_strategy_params=planning_strategy_params,
            max_steps=max_steps,
            system_prompt=system_prompt,
        )

        agent = await self.create(
            definition,
            user_context=user_context,
            base_config_override=base_config_override,
        )

        # Issue #382: inline-built agents opt out of post-mission-learning by
        # default. The executor reads learning.enabled from the on-disk profile
        # (default.yaml has it true), so the inline path used to silently write
        # wiki pages no caller asked for. The executor checks this attribute
        # before falling back to the profile config.
        agent._learning_enabled = False
        return agent

    async def create_agent_with_plugin(
        self,
        plugin_path: str,
        profile: str = "butler",
        user_context: dict[str, Any] | None = None,
        planning_strategy: str | None = None,
        planning_strategy_params: dict[str, Any] | None = None,
    ) -> Agent:
        """Create Agent with external plugin tools.

        Args:
            plugin_path: Path to plugin directory (relative or absolute).
            profile: Base profile for infrastructure settings.
            user_context: Optional user context for RAG tools.
            planning_strategy: Optional planning strategy override.
            planning_strategy_params: Optional planning strategy parameters.

        Returns:
            Agent instance with plugin tools loaded.

        Raises:
            FileNotFoundError: If plugin path doesn't exist.
            PluginError: If plugin structure is invalid or tools fail validation.
        """
        plugin_loader = PluginLoader()
        manifest = plugin_loader.discover_plugin(plugin_path)

        # Load and merge configs
        base_config = self.profile_loader.load_safe(profile)
        plugin_config = plugin_loader.load_config(manifest)
        merged_config = self.profile_loader.merge_plugin_config(base_config, plugin_config)

        # Resolve ${PLUGIN_PATH} in LLM config path
        llm_config_path = merged_config.get("llm", {}).get("config_path", "")
        if "${PLUGIN_PATH}" in llm_config_path:
            merged_config["llm"]["config_path"] = llm_config_path.replace(
                "${PLUGIN_PATH}", str(manifest.path)
            )

        self.logger.info(
            "creating_agent_with_plugin",
            plugin=manifest.name,
            plugin_path=str(manifest.path),
            profile=profile,
            tool_classes=manifest.tool_classes,
            has_plugin_config=bool(plugin_config),
        )

        state_manager = self._create_state_manager(merged_config)
        llm_provider = self._create_llm_provider(merged_config)

        # Build tools: plugin + native + MCP
        tool_configs = plugin_config.get("tools", [])
        embedding_service = self._create_embedding_service(
            plugin_config.get("embeddings"), manifest
        )
        plugin_tools = plugin_loader.load_tools(
            manifest,
            tool_configs=tool_configs,
            llm_provider=llm_provider,
            embedding_service=embedding_service,
        )
        native_tools = self._resolve_plugin_native_tools(tool_configs, llm_provider, merged_config)
        all_tools = plugin_tools + native_tools

        mcp_tools, mcp_contexts = await self._tool_builder.create_mcp_tools(merged_config)
        all_tools.extend(mcp_tools)

        activate_skill_tool = self._maybe_add_skill_tool(manifest, all_tools)

        # Build system prompt and agent settings
        system_prompt = self.prompt_assembler.assemble(
            all_tools,
            specialist=plugin_config.get("specialist"),
            custom_prompt=plugin_config.get("system_prompt"),
        )
        agent_config = merged_config.get("agent", {})
        strategy_name = planning_strategy or agent_config.get("planning_strategy")
        strategy_params = planning_strategy_params or agent_config.get("planning_strategy_params")
        settings = {
            "max_steps": agent_config.get("max_steps"),
            "max_parallel_tools": agent_config.get("max_parallel_tools"),
            "planning_strategy": select_planning_strategy(strategy_name, strategy_params),
            "model_alias": merged_config.get("llm", {}).get("default_model", "main"),
            "tool_result_store_threshold": agent_config.get("tool_result_store_threshold"),
            "tool_message_max_chars": agent_config.get("tool_message_max_chars"),
            "assistant_message_max_chars": agent_config.get("assistant_message_max_chars"),
            "approval_bypass_tools": agent_config.get("approval_bypass_tools"),
            "react_no_progress_threshold": agent_config.get("react_no_progress_threshold"),
            "react_signature_repeat_threshold": agent_config.get(
                "react_signature_repeat_threshold"
            ),
        }
        plugin_work_dir = merged_config.get("persistence", {}).get("work_dir")
        plugin_wiki_store, plugin_wiki_cfg = self._build_wiki_injection(
            merged_config, work_dir_override=plugin_work_dir
        )
        infra = {
            "state_manager": state_manager,
            "llm_provider": llm_provider,
            "context_policy": self._create_context_policy(merged_config),
            "runtime_tracker": self._create_runtime_tracker(
                merged_config,
                work_dir_override=plugin_work_dir,
            ),
            "wiki_store": plugin_wiki_store,
            "wiki_context_config": plugin_wiki_cfg,
            "mcp_contexts": [],
        }

        self.logger.debug(
            "plugin_agent_created",
            plugin=manifest.name,
            tools_count=len(all_tools),
            tool_names=[t.name for t in all_tools],
            mcp_tools=[t.name for t in mcp_tools],
            model_alias=settings["model_alias"],
            planning_strategy=settings["planning_strategy"].name,
        )

        # Build skill manager
        skill_manager = self._build_plugin_skill_manager(manifest, plugin_config)

        context_mgmt = merged_config.get("context_management", {})
        agent = self._instantiate_agent(
            infra=infra,
            all_tools=all_tools,
            system_prompt=system_prompt,
            settings=settings,
            skill_manager=skill_manager,
            summary_threshold=context_mgmt.get("summary_threshold"),
            compression_trigger=context_mgmt.get("compression_trigger"),
            max_input_tokens=context_mgmt.get("max_input_tokens"),
            agent_id=manifest.name,
        )

        _set_mcp_contexts(agent, mcp_contexts)
        _set_plugin_manifest(agent, manifest)
        _set_merged_config(agent, merged_config)

        if activate_skill_tool is not None:
            activate_skill_tool.set_agent_ref(agent)
            self.logger.debug("activate_skill_tool_agent_ref_set", plugin=manifest.name)

        return self._apply_extensions(merged_config, agent)

    def _resolve_plugin_native_tools(
        self,
        tool_configs: list[Any],
        llm_provider: LLMProviderProtocol,
        merged_config: dict[str, Any] | None = None,
    ) -> list[ToolProtocol]:
        """Resolve native tools referenced in plugin tool configs."""
        from taskforce.application.tool_builder import ToolBuilder
        from taskforce.application.tool_registry import ToolRegistry

        native_tool_names: list[str] = []
        for tool_cfg in tool_configs:
            if isinstance(tool_cfg, str):
                native_tool_names.append(tool_cfg)
            elif isinstance(tool_cfg, dict) and "name" in tool_cfg:
                native_tool_names.append(tool_cfg["name"])

        if not native_tool_names:
            return []

        wiki_store_dir = None
        if merged_config:
            wiki_store_dir = ToolBuilder.resolve_wiki_store_dir(merged_config)

        registry = ToolRegistry(
            llm_provider=llm_provider,
            wiki_store_dir=wiki_store_dir,
            gateway=self._gateway,
            scheduler=self._scheduler,
            auth_manager=self._auth_manager,
        )
        self._tool_builder.set_resolver(registry)
        # Only resolve names the registry actually knows about —
        # plugin-specific tool names are handled by plugin_loader, not here.
        available = set(registry.get_available_tools())
        names_to_resolve = [n for n in native_tool_names if n in available]
        if not names_to_resolve:
            return []
        return registry.resolve(names_to_resolve)

    def _maybe_add_skill_tool(self, manifest: Any, all_tools: list[ToolProtocol]) -> Any:
        """Add ActivateSkillTool if plugin has skills. Returns the tool or None."""
        if not manifest.skills_path:
            return None

        from taskforce.infrastructure.tools.native.activate_skill_tool import (
            ActivateSkillTool,
        )

        activate_skill_tool = ActivateSkillTool()
        all_tools.append(activate_skill_tool)
        self.logger.debug("activate_skill_tool_added", plugin=manifest.name)
        return activate_skill_tool

    def _maybe_add_skill_tool_for_profile(
        self,
        skill_manager: SkillManager | None,
        all_tools: list[ToolProtocol],
    ) -> Any:
        """Add ActivateSkillTool for profile-based agents with skills.

        Returns the tool instance or None.
        """
        if not skill_manager or not skill_manager.has_skills:
            return None

        from taskforce.infrastructure.tools.native.activate_skill_tool import (
            ActivateSkillTool,
        )

        activate_skill_tool = ActivateSkillTool()
        all_tools.append(activate_skill_tool)
        self.logger.debug(
            "activate_skill_tool_added_for_profile_agent",
            skills=skill_manager.list_skills(),
        )
        return activate_skill_tool

    def _build_plugin_skill_manager(
        self, manifest: Any, plugin_config: dict[str, Any]
    ) -> SkillManager | None:
        """Build a SkillManager for a plugin if it has skills."""
        if not manifest.skills_path:
            return None

        skill_configs = plugin_config.get("skills", {}).get("available", [])
        skill_manager = create_skill_manager_from_manifest(manifest, skill_configs=skill_configs)
        if not (skill_manager and skill_manager.has_skills):
            return None

        self.logger.info(
            "plugin_skills_loaded",
            plugin=manifest.name,
            skills=skill_manager.list_skills(),
        )
        skills_config = plugin_config.get("skills", {})
        if skills_config.get("activation", {}).get("auto_switch", True):
            self._configure_skill_switch_conditions(skill_manager, manifest.skill_names)
        return skill_manager

    def _build_default_skill_manager(
        self, project_root: str | None = None
    ) -> SkillManager | None:
        """Build a SkillManager for profile-based agents with project/user skills.

        When ``project_root`` is given (project-scoped conversation per
        #273), skills under ``<project_root>/.taskforce/skills/`` and
        ``<project_root>/.claude/skills/`` are discovered in addition to
        the user-global directory — so per-project workflows can ship
        their own skills without polluting other projects.
        """
        manager = SkillManager(
            include_global_skills=True,
            project_root=project_root,
        )
        if manager.has_skills:
            return manager
        return None

    def _configure_skill_switch_conditions(
        self, skill_manager: SkillManager, skill_names: list[str]
    ) -> None:
        """Configure default skill switch conditions for smart-booking skills."""
        from taskforce.application.skill_manager import SkillSwitchCondition

        if "smart-booking-auto" not in skill_names:
            return
        if "smart-booking-hitl" not in skill_names:
            return

        skill_manager.add_switch_condition(
            SkillSwitchCondition(
                from_skill="smart-booking-auto",
                to_skill="smart-booking-hitl",
                trigger_tool="confidence_evaluator",
                condition_key="recommendation",
                condition_check=lambda v: v == "hitl_review",
            )
        )
        skill_manager.add_switch_condition(
            SkillSwitchCondition(
                from_skill="smart-booking-auto",
                to_skill="smart-booking-hitl",
                trigger_tool="confidence_evaluator",
                condition_key="triggered_hard_gates",
                condition_check=lambda v: bool(v) if isinstance(v, list) else False,
            )
        )
        self.logger.debug(
            "skill_switch_conditions_configured",
            pattern="smart-booking",
        )

    def _load_profile(self, profile: str) -> dict[str, Any]:
        """Delegates to :class:`ProfileLoader`."""
        return self.profile_loader.load(profile)

    def _create_context_policy(self, config: dict[str, Any]) -> ContextPolicy:
        """Create ContextPolicy from configuration."""
        context_config = config.get("context_policy")
        if context_config:
            return ContextPolicy.from_dict(context_config)
        return ContextPolicy.conservative_default()

    def _create_state_manager(self, config: dict[str, Any]) -> StateManagerProtocol:
        """Create state manager based on configuration."""
        return self.infra_builder.build_state_manager(config)

    def _create_runtime_tracker(
        self,
        config: dict[str, Any],
        work_dir_override: str | None = None,
    ) -> AgentRuntimeTrackerProtocol | None:
        """Create runtime tracker based on configuration."""
        return self.infra_builder.build_runtime_tracker(config, work_dir_override)

    def _create_llm_provider(self, config: dict[str, Any]) -> LLMProviderProtocol:
        """Create LLM provider based on configuration."""
        return self.infra_builder.build_llm_provider(config)

    def _create_embedding_service(
        self,
        embeddings_config: dict[str, Any] | None,
        manifest: PluginManifest | None = None,
    ) -> Any | None:
        """Create embedding service from config using dynamic plugin imports.

        Uses the plugin's manifest to resolve embedding service classes
        without hardcoding imports from plugin-specific packages.

        Args:
            embeddings_config: Embeddings section from plugin/profile config.
                Expected keys: provider, model, cache_enabled, cache_max_size.
            manifest: Plugin manifest for resolving import paths.

        Returns:
            Embedding service instance, or None if not configured.
        """
        if not embeddings_config:
            return None

        provider = embeddings_config.get("provider", "")
        if not provider:
            return None

        # Map provider names to module paths within the plugin package
        provider_modules = {
            "litellm": (".infrastructure.embeddings.litellm_embeddings", "LiteLLMEmbeddingService"),
            "azure": (".infrastructure.embeddings.azure_embeddings", "AzureEmbeddingService"),
        }

        if provider not in provider_modules:
            self.logger.warning("embedding_service_unknown_provider", provider=provider)
            return None

        module_suffix, class_name = provider_modules[provider]

        # Resolve the full module name from the plugin's package
        if manifest is None:
            self.logger.warning(
                "embedding_service_no_manifest",
                provider=provider,
                hint="Cannot resolve embedding service without plugin manifest",
            )
            return None

        package_name = manifest.package_path.name
        module_name = f"{package_name}{module_suffix}"

        # Temporarily add plugin path to sys.path for import
        import importlib

        plugin_path_str = str(manifest.path)
        added_to_path = False
        if plugin_path_str not in sys.path:
            sys.path.insert(0, plugin_path_str)
            added_to_path = True

        try:
            module = importlib.import_module(module_name)
            service_class = getattr(module, class_name)

            # Build kwargs based on provider type
            kwargs: dict[str, Any] = {
                "cache_enabled": embeddings_config.get("cache_enabled", True),
                "cache_max_size": embeddings_config.get("cache_max_size", 1000),
            }
            if provider == "litellm":
                kwargs["model"] = embeddings_config.get("model", "text-embedding-3-small")
                # Pass cache_dir for persistent disk-backed embedding cache.
                # When set, embeddings survive process restarts (avoids ~8s API calls).
                cache_dir = embeddings_config.get("cache_dir")
                if cache_dir:
                    kwargs["cache_dir"] = cache_dir
            elif provider == "azure":
                kwargs["deployment_name"] = embeddings_config.get("deployment_name")
                kwargs["api_version"] = embeddings_config.get("api_version", "2024-02-01")

            service = service_class(**kwargs)
            self.logger.info(
                "embedding_service_created",
                provider=provider,
                module=module_name,
            )
            return service

        except (ImportError, AttributeError) as e:
            self.logger.warning(
                "embedding_service_import_failed",
                provider=provider,
                module=module_name,
                error=str(e),
            )
            return None

        finally:
            if added_to_path and plugin_path_str in sys.path:
                sys.path.remove(plugin_path_str)
