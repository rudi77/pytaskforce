"""
Unified Agent Registry

Aggregates all agent sources (custom, profile, plugin, command) into a
single registry with unified API.

Part of Phase 3 refactoring: Unified AgentRegistry.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from taskforce.core.domain.agent_definition import (
    AgentDefinition,
    AgentDefinitionInput,
    AgentDefinitionUpdate,
    AgentSource,
    MCPServerConfig,
)
from taskforce.core.utils.paths import get_base_path

logger = structlog.get_logger(__name__)


class AgentRegistry:
    """
    Unified registry for all agent definitions.

    Aggregates agents from:
    - Custom agents (configs/custom/*.yaml) - mutable
    - Profile agents (configs/*.yaml) - read-only
    - Plugin agents (examples/, plugins/) - read-only
    - Command agents (.taskforce/commands/**/*.md) - read-only

    All agents are normalized to AgentDefinition model.

    Directory structure:
        configs/custom/{agent_id}.yaml - Custom agents
        configs/*.yaml - Profile agents (excluding llm_config.yaml)
        examples/*/ - Example plugin agents
        plugins/*/ - User plugin agents
        .taskforce/commands/**/*.md - Slash command agents

    Thread Safety:
        Not thread-safe. Use appropriate locking if concurrent access needed.

    Example:
        >>> registry = AgentRegistry()
        >>> agents = registry.list_all()
        >>> agent = registry.get("my-agent")
        >>> if agent and agent.is_mutable:
        ...     registry.save(agent.copy_with(name="New Name"))
    """

    def __init__(
        self,
        config_dir: Path | str | None = None,
        base_path: Path | None = None,
    ) -> None:
        """
        Initialize the unified agent registry.

        Args:
            config_dir: Root directory for configuration files. If None, uses
                       'src/taskforce/configs/' relative to project root.
                       Falls back to 'configs/' for backward compatibility.
            base_path: Base path for plugin discovery (defaults to config_dir parent)
        """
        if config_dir is None:
            base_path_obj = get_base_path()
            # Try new location first, then fall back to old location for compatibility
            new_config_dir = base_path_obj / "src" / "taskforce" / "configs"
            old_config_dir = base_path_obj / "configs"
            if new_config_dir.exists():
                self.config_dir = new_config_dir
            elif old_config_dir.exists():
                self.config_dir = old_config_dir
            else:
                # Default to new location even if it doesn't exist yet
                self.config_dir = new_config_dir
        else:
            self.config_dir = Path(config_dir)
        self.custom_dir = self.config_dir / "custom"
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        self.base_path = base_path or self.config_dir.parent
        self._logger = logger.bind(component="AgentRegistry")

        # Cache for performance (invalidate on mutations)
        self._cache: dict[str, AgentDefinition] = {}
        self._cache_valid = False

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def list_all(self, sources: list[AgentSource] | None = None) -> list[AgentDefinition]:
        """
        List all agents from all sources.

        Args:
            sources: Optional filter by source types. If None, returns all.

        Returns:
            List of all valid agent definitions
        """
        self._ensure_cache()

        agents = list(self._cache.values())

        if sources:
            agents = [a for a in agents if a.source in sources]

        self._logger.debug("agents.listed", count=len(agents), sources=sources)
        return agents

    def get(self, agent_id: str) -> AgentDefinition | None:
        """
        Get an agent by ID.

        Searches all sources. If multiple sources have the same ID,
        priority is: custom > profile > plugin > command.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentDefinition if found, None otherwise
        """
        self._ensure_cache()

        agent = self._cache.get(agent_id)
        if agent:
            return agent

        # Also try cmd: prefix for command agents
        if not agent_id.startswith("cmd:"):
            agent = self._cache.get(f"cmd:{agent_id}")

        return agent

    def save(self, definition: AgentDefinition) -> AgentDefinition:
        """
        Save an agent definition.

        Only CUSTOM agents can be saved. Other sources are read-only.

        Args:
            definition: Agent definition to save

        Returns:
            Saved AgentDefinition with updated timestamps

        Raises:
            ValueError: If agent source is not CUSTOM
            FileExistsError: If creating new agent and ID already exists
        """
        if definition.source != AgentSource.CUSTOM:
            raise ValueError(
                f"Cannot save agent with source '{definition.source.value}'. "
                "Only CUSTOM agents can be saved."
            )

        path = self._get_custom_agent_path(definition.agent_id)
        is_update = path.exists()

        # Update timestamps
        now = datetime.now(UTC)
        if is_update:
            definition = definition.copy_with(updated_at=now)
        else:
            definition = definition.copy_with(created_at=now, updated_at=now)

        # Serialize and save
        data = self._definition_to_yaml(definition)
        self._atomic_write_yaml(path, data)

        # Invalidate cache
        self._invalidate_cache()

        event = "agent.updated" if is_update else "agent.created"
        self._logger.info(event, agent_id=definition.agent_id, path=str(path))

        return definition

    def create(self, input_def: AgentDefinitionInput) -> AgentDefinition:
        """
        Create a new custom agent.

        Args:
            input_def: Input definition for the new agent

        Returns:
            Created AgentDefinition with timestamps

        Raises:
            FileExistsError: If agent_id already exists
        """
        path = self._get_custom_agent_path(input_def.agent_id)
        if path.exists():
            raise FileExistsError(f"Agent '{input_def.agent_id}' already exists")

        # Check if ID conflicts with other sources
        existing = self.get(input_def.agent_id)
        if existing:
            raise FileExistsError(
                f"Agent ID '{input_def.agent_id}' conflicts with existing "
                f"{existing.source.value} agent"
            )

        definition = input_def.to_definition()
        return self.save(definition)

    def update(self, agent_id: str, updates: AgentDefinitionUpdate) -> AgentDefinition:
        """
        Update an existing custom agent.

        Args:
            agent_id: Agent identifier to update
            updates: Fields to update

        Returns:
            Updated AgentDefinition

        Raises:
            FileNotFoundError: If agent doesn't exist
            ValueError: If agent is not CUSTOM source
        """
        existing = self.get(agent_id)
        if not existing:
            raise FileNotFoundError(f"Agent '{agent_id}' not found")

        if existing.source != AgentSource.CUSTOM:
            raise ValueError(
                f"Cannot update agent with source '{existing.source.value}'. "
                "Only CUSTOM agents can be updated."
            )

        # Apply updates - build kwargs for copy_with
        update_kwargs: dict[str, Any] = {}
        if updates.name is not None:
            update_kwargs["name"] = updates.name
        if updates.description is not None:
            update_kwargs["description"] = updates.description
        if updates.system_prompt is not None:
            update_kwargs["system_prompt"] = updates.system_prompt
        if updates.specialist is not None:
            update_kwargs["specialist"] = updates.specialist
        if updates.planning_strategy is not None:
            update_kwargs["planning_strategy"] = updates.planning_strategy
        if updates.tools is not None:
            update_kwargs["tools"] = updates.tools
        if updates.mcp_servers is not None:
            update_kwargs["mcp_servers"] = [
                MCPServerConfig.from_dict(s) if isinstance(s, dict) else s
                for s in updates.mcp_servers
            ]
        if updates.mcp_tool_filter is not None:
            update_kwargs["mcp_tool_filter"] = updates.mcp_tool_filter
        if updates.base_profile is not None:
            update_kwargs["base_profile"] = updates.base_profile
        if updates.work_dir is not None:
            update_kwargs["work_dir"] = updates.work_dir

        updated = existing.copy_with(**update_kwargs)
        return self.save(updated)

    def delete(self, agent_id: str) -> None:
        """
        Delete a custom agent.

        Args:
            agent_id: Agent identifier to delete

        Raises:
            FileNotFoundError: If agent doesn't exist
            ValueError: If agent is not CUSTOM source
        """
        existing = self.get(agent_id)
        if not existing:
            raise FileNotFoundError(f"Agent '{agent_id}' not found")

        if existing.source != AgentSource.CUSTOM:
            raise ValueError(
                f"Cannot delete agent with source '{existing.source.value}'. "
                "Only CUSTOM agents can be deleted."
            )

        path = self._get_custom_agent_path(agent_id)
        path.unlink()

        # Invalidate cache
        self._invalidate_cache()

        self._logger.info("agent.deleted", agent_id=agent_id, path=str(path))

    def exists(self, agent_id: str) -> bool:
        """Check if an agent exists."""
        return self.get(agent_id) is not None

    def refresh(self) -> None:
        """Force refresh of all agent sources."""
        self._invalidate_cache()
        self._ensure_cache()

    # -------------------------------------------------------------------------
    # Source Loaders
    # -------------------------------------------------------------------------

    def _ensure_cache(self) -> None:
        """Ensure cache is populated."""
        if self._cache_valid:
            return

        self._cache.clear()

        # Load in priority order (later sources don't override earlier)
        self._load_custom_agents()
        self._load_profile_agents()
        self._load_plugin_agents()

        self._cache_valid = True

    def _invalidate_cache(self) -> None:
        """Invalidate the cache."""
        self._cache_valid = False

    def _load_custom_agents(self) -> None:
        """Load custom agents from configs/custom/*.yaml."""
        if not self.custom_dir.exists():
            return

        for yaml_file in self.custom_dir.glob("*.yaml"):
            agent_id = yaml_file.stem
            try:
                agent = self._parse_custom_agent_file(yaml_file, agent_id)
                if agent and agent.agent_id not in self._cache:
                    self._cache[agent.agent_id] = agent
            except Exception as e:
                self._logger.warning(
                    "agent.yaml.corrupt",
                    agent_id=agent_id,
                    path=str(yaml_file),
                    error=str(e),
                )

    def _load_profile_agents(self) -> None:
        """Load profile agents from configs/*.yaml."""
        if not self.config_dir.exists():
            return

        for yaml_file in self.config_dir.glob("*.yaml"):
            # Skip llm_config.yaml and custom directory
            if yaml_file.name == "llm_config.yaml":
                continue
            if yaml_file.parent.name == "custom":
                continue

            profile_name = yaml_file.stem
            try:
                agent = self._parse_profile_agent_file(yaml_file, profile_name)
                if agent and agent.agent_id not in self._cache:
                    self._cache[agent.agent_id] = agent
            except Exception as e:
                self._logger.warning(
                    "profile.yaml.corrupt",
                    profile=profile_name,
                    path=str(yaml_file),
                    error=str(e),
                )

    def _load_plugin_agents(self) -> None:
        """Load plugin agents from examples/ and plugins/ (check new location first)."""
        plugin_dirs = [
            self.base_path / "src" / "taskforce" / "plugins",
            self.base_path / "examples",
            self.base_path / "plugins",  # Old location for backward compatibility
        ]

        for plugin_base_dir in plugin_dirs:
            if not plugin_base_dir.exists():
                continue

            for plugin_dir in plugin_base_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue

                # Skip hidden directories
                if plugin_dir.name.startswith(".") or plugin_dir.name.startswith("__"):
                    continue

                try:
                    agent = self._parse_plugin_agent(plugin_dir)
                    if agent and agent.agent_id not in self._cache:
                        self._cache[agent.agent_id] = agent
                except Exception as e:
                    self._logger.debug(
                        "plugin.discovery.skipped",
                        plugin_dir=str(plugin_dir),
                        error=str(e),
                    )

    # -------------------------------------------------------------------------
    # Parsing Helpers
    # -------------------------------------------------------------------------

    def _parse_custom_agent_file(
        self, yaml_file: Path, agent_id: str
    ) -> AgentDefinition | None:
        """Parse a custom agent YAML file."""
        with open(yaml_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Extract tools as string list
        tools = self._extract_tool_names(data)

        # Parse timestamps
        created_at = None
        updated_at = None
        if data.get("created_at"):
            if isinstance(data["created_at"], str):
                created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            elif isinstance(data["created_at"], datetime):
                created_at = data["created_at"]
        if data.get("updated_at"):
            if isinstance(data["updated_at"], str):
                updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
            elif isinstance(data["updated_at"], datetime):
                updated_at = data["updated_at"]

        # Parse MCP servers
        mcp_servers = [
            MCPServerConfig.from_dict(s) for s in data.get("mcp_servers", [])
        ]

        # Support both 'tools' and 'tool_allowlist' for backwards compatibility
        mcp_tool_filter = data.get("mcp_tool_allowlist")

        return AgentDefinition(
            agent_id=data.get("agent_id", agent_id),
            name=data.get("name", agent_id),
            description=data.get("description", ""),
            source=AgentSource.CUSTOM,
            system_prompt=data.get("system_prompt", ""),
            specialist=data.get("specialist"),
            planning_strategy=data.get("planning_strategy", "native_react"),
            tools=tools,
            mcp_servers=mcp_servers,
            mcp_tool_filter=mcp_tool_filter,
            base_profile=data.get("base_profile", "dev"),
            work_dir=data.get("work_dir") or data.get("persistence", {}).get("work_dir"),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _parse_profile_agent_file(
        self, yaml_file: Path, profile_name: str
    ) -> AgentDefinition | None:
        """Parse a profile agent YAML file."""
        with open(yaml_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return AgentDefinition.from_profile(profile_name, data)

    def _parse_plugin_agent(self, plugin_dir: Path) -> AgentDefinition | None:
        """Parse a plugin agent from directory."""
        try:
            from taskforce.application.plugin_loader import PluginLoader

            loader = PluginLoader()
            manifest = loader.discover_plugin(str(plugin_dir))
            plugin_config = loader.load_config(manifest)

            return AgentDefinition.from_plugin(
                plugin_path=str(plugin_dir),
                manifest=plugin_config,
                tool_classes=manifest.tool_classes,
            )

        except (FileNotFoundError, Exception) as e:
            self._logger.debug(
                "plugin.load.failed",
                plugin_dir=str(plugin_dir),
                error=str(e),
            )
            return None

    def _extract_tool_names(self, data: dict[str, Any]) -> list[str]:
        """Extract tool names from YAML data, handling multiple formats."""
        tools = []

        # Check 'tools' key first
        if "tools" in data:
            for tool_def in data["tools"]:
                if isinstance(tool_def, str):
                    tools.append(tool_def)
                elif isinstance(tool_def, dict):
                    # Extract type from dict
                    tool_type = tool_def.get("type", "")
                    if tool_type:
                        # Convert class name to registry name
                        tools.append(self._class_name_to_tool_name(tool_type))

        # Also check 'tool_allowlist' for backwards compatibility
        if "tool_allowlist" in data:
            tools.extend(data["tool_allowlist"])

        # Remove duplicates while preserving order
        seen = set()
        unique_tools = []
        for t in tools:
            if t and t not in seen:
                seen.add(t)
                unique_tools.append(t)

        return unique_tools

    def _class_name_to_tool_name(self, class_name: str) -> str:
        """Convert a tool class name to registry name."""
        from taskforce.infrastructure.tools.registry import get_tool_name_for_type

        tool_name = get_tool_name_for_type(class_name)
        return tool_name or class_name.lower().replace("tool", "")

    # -------------------------------------------------------------------------
    # Serialization Helpers
    # -------------------------------------------------------------------------

    def _get_custom_agent_path(self, agent_id: str) -> Path:
        """Get the file path for a custom agent definition."""
        return self.custom_dir / f"{agent_id}.yaml"

    def _definition_to_yaml(self, definition: AgentDefinition) -> dict[str, Any]:
        """Convert AgentDefinition to YAML-serializable dict."""
        data: dict[str, Any] = {
            "agent_id": definition.agent_id,
            "name": definition.name,
        }

        if definition.description:
            data["description"] = definition.description
        if definition.system_prompt:
            data["system_prompt"] = definition.system_prompt
        if definition.specialist:
            data["specialist"] = definition.specialist
        if definition.planning_strategy != "native_react":
            data["planning_strategy"] = definition.planning_strategy
        if definition.tools:
            data["tools"] = definition.tools
        if definition.mcp_servers:
            data["mcp_servers"] = [s.to_dict() for s in definition.mcp_servers]
        if definition.mcp_tool_filter is not None:
            data["mcp_tool_allowlist"] = definition.mcp_tool_filter
        if definition.base_profile != "dev":
            data["base_profile"] = definition.base_profile
        if definition.work_dir:
            data["work_dir"] = definition.work_dir
        if definition.created_at:
            data["created_at"] = definition.created_at.isoformat()
        if definition.updated_at:
            data["updated_at"] = definition.updated_at.isoformat()

        return data

    def _atomic_write_yaml(self, path: Path, data: dict[str, Any]) -> None:
        """Write YAML atomically using temp file + rename."""
        temp_fd, temp_path = tempfile.mkstemp(
            dir=path.parent, suffix=".tmp", prefix=".agent_"
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )

            # Windows: must delete target before rename
            if path.exists():
                path.unlink()

            # Atomic rename
            Path(temp_path).rename(path)

        except Exception:
            if Path(temp_path).exists():
                Path(temp_path).unlink()
            raise
