"""
File-Based Agent Registry
==========================

Provides CRUD operations for custom agent definitions stored as YAML files.

Responsibilities:
- Persist custom agents to ``configs/custom/{agent_id}.yaml``
- List all agents (custom + profile configs + plugin agents)
- Delegate atomic writes, serialization, and plugin discovery to focused modules

Story: 8.1 - Custom Agent Registry (CRUD + YAML Persistence)

Clean Architecture Notes:
- Uses Domain Models from core/domain/agent_models.py
- Accepts ToolMapperProtocol via dependency injection
- No direct imports from API or Application layers
"""

from datetime import UTC, datetime
from pathlib import Path

import structlog

from taskforce.core.domain.agent_models import (
    CustomAgentDefinition,
    CustomAgentInput,
    CustomAgentUpdateInput,
    PluginAgentDefinition,
    ProfileAgentDefinition,
)
from taskforce.core.interfaces.tool_mapping import ToolMapperProtocol
from taskforce.core.utils.paths import get_base_path
from taskforce.infrastructure.persistence.agent_serializer import (
    build_agent_yaml,
    parse_custom_agent_yaml,
    parse_profile_agent_yaml,
)
from taskforce.infrastructure.persistence.plugin_scanner import (
    discover_plugin_agents,
    find_plugin_agent,
)
from taskforce.infrastructure.persistence.yaml_io import (
    atomic_write_yaml,
    safe_load_yaml,
)

logger = structlog.get_logger()


class FileAgentRegistry:
    """
    File-based agent registry with YAML persistence.

    Manages custom agent definitions and scans profile configurations.

    Directory structure:
        configs/custom/{agent_id}.yaml - Custom agents
        configs/*.yaml - Profile agents (excluding llm_config.yaml)

    Thread Safety:
        Not thread-safe. Use appropriate locking if concurrent access needed.

    Example:
        >>> from taskforce.application.tool_mapper import get_tool_mapper
        >>> registry = FileAgentRegistry(tool_mapper=get_tool_mapper())
        >>> agent = CustomAgentInput(
        ...     agent_id="test-agent",
        ...     name="Test Agent",
        ...     description="Test",
        ...     system_prompt="You are a test agent",
        ...     tool_allowlist=["python"]
        ... )
        >>> created = registry.create_agent(agent)
        >>> assert created.agent_id == "test-agent"
    """

    def __init__(
        self,
        configs_dir: str | None = None,
        tool_mapper: ToolMapperProtocol | None = None,
        base_path: Path | None = None,
    ):
        """
        Initialize the agent registry.

        Args:
            configs_dir: Root directory for configuration files.
                        If None, auto-detects: tries 'src/taskforce/configs/'
                        first, falls back to 'configs/' for backward compatibility.
            tool_mapper: Optional tool mapper for tool name resolution.
                        If not provided, tool mapping features are disabled.
            base_path: Optional base path for plugin discovery.
                      If not provided, uses configs_dir parent as base.
        """
        if configs_dir is None:
            detected_base = get_base_path()
            new_config_dir = detected_base / "src" / "taskforce" / "configs"
            old_config_dir = detected_base / "configs"
            if new_config_dir.exists():
                self.configs_dir = new_config_dir
            elif old_config_dir.exists():
                self.configs_dir = old_config_dir
            else:
                # Default to new location even if it doesn't exist yet
                self.configs_dir = new_config_dir
        else:
            self.configs_dir = Path(configs_dir)

        self.custom_dir = self.configs_dir / "custom"
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        self._tool_mapper = tool_mapper
        self.base_path = base_path or self.configs_dir.parent
        self.logger = logger.bind(component="file_agent_registry")

    def _get_agent_path(self, agent_id: str) -> Path:
        """Get the file path for an agent definition."""
        return self.custom_dir / f"{agent_id}.yaml"

    def _load_custom_agent(self, agent_id: str) -> CustomAgentDefinition | None:
        """
        Load a custom agent from YAML file.

        Args:
            agent_id: Agent identifier

        Returns:
            CustomAgentDefinition if found and valid, None otherwise
        """
        path = self._get_agent_path(agent_id)
        data = safe_load_yaml(path)
        if data is None:
            if path.exists():
                self.logger.warning(
                    "agent.yaml.corrupt",
                    agent_id=agent_id,
                    path=str(path),
                )
            return None

        try:
            return parse_custom_agent_yaml(data, agent_id, self._tool_mapper)
        except Exception as e:
            self.logger.warning(
                "agent.yaml.corrupt",
                agent_id=agent_id,
                path=str(path),
                error=str(e),
            )
            return None

    def create_agent(self, agent_input: CustomAgentInput) -> CustomAgentDefinition:
        """
        Create a new custom agent.

        Args:
            agent_input: Agent definition input to create

        Returns:
            CustomAgentDefinition with timestamps

        Raises:
            FileExistsError: If agent_id already exists
        """
        path = self._get_agent_path(agent_input.agent_id)

        if path.exists():
            raise FileExistsError(f"Agent '{agent_input.agent_id}' already exists")

        # Add timestamps
        now = datetime.now(UTC).isoformat()
        data = build_agent_yaml(
            agent_id=agent_input.agent_id,
            name=agent_input.name,
            description=agent_input.description,
            system_prompt=agent_input.system_prompt,
            tool_allowlist=agent_input.tool_allowlist,
            mcp_servers=agent_input.mcp_servers,
            created_at=now,
            updated_at=now,
            tool_mapper=self._tool_mapper,
        )

        atomic_write_yaml(path, data)

        self.logger.info("agent.created", agent_id=agent_input.agent_id, path=str(path))

        # Return domain model
        return CustomAgentDefinition(
            agent_id=agent_input.agent_id,
            name=agent_input.name,
            description=agent_input.description,
            system_prompt=agent_input.system_prompt,
            tool_allowlist=agent_input.tool_allowlist,
            mcp_servers=agent_input.mcp_servers,
            mcp_tool_allowlist=agent_input.mcp_tool_allowlist,
            created_at=now,
            updated_at=now,
        )

    def get_agent(
        self, agent_id: str
    ) -> CustomAgentDefinition | ProfileAgentDefinition | PluginAgentDefinition | None:
        """
        Get an agent by ID.

        Searches custom agents first, then profile agents, then plugin agents.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent definition if found, None otherwise
        """
        # Try custom agents first
        custom = self._load_custom_agent(agent_id)
        if custom:
            return custom

        # Try profile agents (agent_id matches profile name)
        profile_path = self.configs_dir / f"{agent_id}.yaml"
        if profile_path.exists() and agent_id != "llm_config":
            return parse_profile_agent_yaml(profile_path)

        # Try plugin agents
        plugin = find_plugin_agent(agent_id, self.base_path)
        if plugin:
            return plugin

        return None

    def list_agents(
        self,
    ) -> list[CustomAgentDefinition | ProfileAgentDefinition | PluginAgentDefinition]:
        """
        List all agents (custom + profile + plugin).

        Scans:
        - configs/custom/*.yaml (custom agents)
        - configs/*.yaml (profile agents, excluding llm_config.yaml)
        - examples/*/ and plugins/*/ (plugin agents)

        Corrupt YAML files are skipped with warning logged.

        Returns:
            List of all valid agent definitions
        """
        agents: list[CustomAgentDefinition | ProfileAgentDefinition | PluginAgentDefinition] = []

        # Load custom agents
        if self.custom_dir.exists():
            for yaml_file in self.custom_dir.glob("*.yaml"):
                agent_id = yaml_file.stem
                agent = self._load_custom_agent(agent_id)
                if agent:
                    agents.append(agent)

        # Load profile agents
        if self.configs_dir.exists():
            for yaml_file in self.configs_dir.glob("*.yaml"):
                # Skip llm_config.yaml and custom directory
                if yaml_file.name == "llm_config.yaml":
                    continue
                if yaml_file.parent.name == "custom":
                    continue

                profile = parse_profile_agent_yaml(yaml_file)
                if profile:
                    agents.append(profile)

        # Load plugin agents
        plugin_agents = discover_plugin_agents(self.base_path)
        agents.extend(plugin_agents)

        self.logger.debug("agents.listed", count=len(agents))
        return agents

    def update_agent(
        self, agent_id: str, update_input: CustomAgentUpdateInput
    ) -> CustomAgentDefinition:
        """
        Update an existing custom agent.

        Args:
            agent_id: Agent identifier to update
            update_input: New agent definition values

        Returns:
            Updated CustomAgentDefinition

        Raises:
            FileNotFoundError: If agent doesn't exist
        """
        path = self._get_agent_path(agent_id)

        if not path.exists():
            raise FileNotFoundError(f"Agent '{agent_id}' not found")

        # Load existing to preserve created_at
        existing = self._load_custom_agent(agent_id)
        if not existing:
            raise FileNotFoundError(f"Agent '{agent_id}' is corrupt")

        # Update with new data
        now = datetime.now(UTC).isoformat()
        data = build_agent_yaml(
            agent_id=agent_id,
            name=update_input.name,
            description=update_input.description,
            system_prompt=update_input.system_prompt,
            tool_allowlist=update_input.tool_allowlist,
            mcp_servers=update_input.mcp_servers,
            created_at=existing.created_at,
            updated_at=now,
            tool_mapper=self._tool_mapper,
        )

        atomic_write_yaml(path, data)

        self.logger.info("agent.updated", agent_id=agent_id, path=str(path))

        # Return domain model
        return CustomAgentDefinition(
            agent_id=agent_id,
            name=update_input.name,
            description=update_input.description,
            system_prompt=update_input.system_prompt,
            tool_allowlist=update_input.tool_allowlist,
            mcp_servers=update_input.mcp_servers,
            mcp_tool_allowlist=update_input.mcp_tool_allowlist,
            created_at=existing.created_at,
            updated_at=now,
        )

    def delete_agent(self, agent_id: str) -> None:
        """
        Delete a custom agent.

        Args:
            agent_id: Agent identifier to delete

        Raises:
            FileNotFoundError: If agent doesn't exist
        """
        path = self._get_agent_path(agent_id)

        if not path.exists():
            raise FileNotFoundError(f"Agent '{agent_id}' not found")

        path.unlink()

        self.logger.info("agent.deleted", agent_id=agent_id, path=str(path))
