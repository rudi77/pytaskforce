"""
Unified Agent Definition Model

This module provides a single, unified model for all agent definitions,
regardless of their source (custom, profile, plugin, or slash command).

Part of the refactoring to unify slash commands, plugins, and configs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class AgentSource(str, Enum):
    """Source/origin of an agent definition."""

    CUSTOM = "custom"  # configs/custom/*.yaml - user-created, mutable
    PROFILE = "profile"  # configs/*.yaml - project config, read-only
    PLUGIN = "plugin"  # examples/, plugins/ - external plugins, read-only
    COMMAND = "command"  # .taskforce/commands/**/*.md - slash commands, read-only


def _class_name_to_tool_name(class_name: str) -> str:
    """
    Convert a tool class name to registry name.

    Args:
        class_name: Class name like "WebSearchTool" or "FileReadTool"

    Returns:
        Registry name like "web_search" or "file_read"
    """
    # Remove "Tool" suffix if present
    name = class_name
    if name.endswith("Tool"):
        name = name[:-4]

    # Convert CamelCase to snake_case
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.lower())

    return "".join(result)


@dataclass
class MCPServerConfig:
    """
    Configuration for an MCP (Model Context Protocol) server.

    MCP servers provide additional tools to agents via stdio or SSE connections.
    """

    type: str  # "stdio" or "sse"
    command: str | None = None  # For stdio: command to run (e.g., "npx")
    args: list[str] = field(default_factory=list)  # For stdio: command args
    url: str | None = None  # For sse: server URL
    env: dict[str, str] = field(default_factory=dict)  # Environment variables
    description: str = ""  # Human-readable description

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServerConfig:
        """Create MCPServerConfig from a dictionary."""
        return cls(
            type=data.get("type", "stdio"),
            command=data.get("command"),
            args=data.get("args", []),
            url=data.get("url"),
            env=data.get("env", {}),
            description=data.get("description", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {"type": self.type}
        if self.command:
            result["command"] = self.command
        if self.args:
            result["args"] = self.args
        if self.url:
            result["url"] = self.url
        if self.env:
            result["env"] = self.env
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class AgentDefinition:
    """
    Unified model for all agent definitions.

    This replaces the separate CustomAgentDefinition, ProfileAgentDefinition,
    PluginAgentDefinition, and agent-type SlashCommandDefinition models.

    Attributes:
        agent_id: Unique identifier for the agent
        name: Human-readable display name
        description: Description of what the agent does
        source: Origin of the definition (custom, profile, plugin, command)

        # Agent behavior
        system_prompt: Custom system prompt (if any)
        specialist: Specialist type (coding, rag, wiki, or None)
        planning_strategy: Planning strategy to use
        planning_strategy_params: Parameters for the planning strategy
        max_steps: Maximum execution steps (None = use default)

        # Tools - ONLY string list (no dicts!)
        tools: List of tool names from the registry

        # MCP servers
        mcp_servers: List of MCP server configurations
        mcp_tool_filter: List of allowed MCP tool names (None = all allowed)

        # Infrastructure
        base_profile: Base profile for LLM/persistence settings
        work_dir: Override working directory

        # Plugin-specific
        plugin_path: Path to plugin directory (for source=PLUGIN)
        tool_classes: List of tool class names from plugin

        # Command-specific
        source_path: Path to source file (for source=COMMAND)
        prompt_template: Prompt template with $ARGUMENTS (for source=COMMAND)

        # Metadata
        created_at: Creation timestamp (for source=CUSTOM)
        updated_at: Last update timestamp (for source=CUSTOM)
    """

    # Required fields
    agent_id: str
    name: str

    # Optional descriptive fields
    description: str = ""
    source: AgentSource = AgentSource.CUSTOM

    # Agent behavior configuration
    system_prompt: str = ""
    specialist: str | None = None  # coding, rag, wiki, None
    planning_strategy: str = "native_react"
    planning_strategy_params: dict[str, Any] = field(default_factory=dict)
    max_steps: int | None = None

    # Tools - ONLY string list
    tools: list[str] = field(default_factory=list)

    # MCP configuration
    mcp_servers: list[MCPServerConfig] = field(default_factory=list)
    mcp_tool_filter: list[str] | None = None  # None = all MCP tools allowed

    # Infrastructure settings
    base_profile: str = "dev"
    work_dir: str | None = None

    # Plugin-specific fields
    plugin_path: str | None = None
    tool_classes: list[str] = field(default_factory=list)

    # Command-specific fields
    source_path: str | None = None
    prompt_template: str | None = None

    # Timestamps (only for CUSTOM agents)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate and normalize the definition after initialization."""
        # Ensure source is an AgentSource enum
        if isinstance(self.source, str):
            self.source = AgentSource(self.source)

        # Normalize mcp_servers from dicts if needed
        normalized_servers = []
        for server in self.mcp_servers:
            if isinstance(server, dict):
                normalized_servers.append(MCPServerConfig.from_dict(server))
            else:
                normalized_servers.append(server)
        self.mcp_servers = normalized_servers

    @property
    def is_mutable(self) -> bool:
        """Check if this definition can be modified (only CUSTOM agents)."""
        return self.source == AgentSource.CUSTOM

    @property
    def has_custom_prompt(self) -> bool:
        """Check if this agent has a custom system prompt."""
        return bool(self.system_prompt and self.system_prompt.strip())

    @property
    def has_mcp_servers(self) -> bool:
        """Check if this agent has MCP server configurations."""
        return len(self.mcp_servers) > 0

    @classmethod
    def from_custom(
        cls,
        agent_id: str,
        name: str,
        description: str = "",
        system_prompt: str = "",
        tools: list[str] | None = None,
        mcp_servers: list[dict[str, Any] | MCPServerConfig] | None = None,
        mcp_tool_filter: list[str] | None = None,
        base_profile: str = "dev",
    ) -> AgentDefinition:
        """
        Create a custom agent definition.

        This is the factory method for user-created agents.
        """
        now = datetime.now()
        return cls(
            agent_id=agent_id,
            name=name,
            description=description,
            source=AgentSource.CUSTOM,
            system_prompt=system_prompt,
            tools=tools or [],
            mcp_servers=[
                MCPServerConfig.from_dict(s) if isinstance(s, dict) else s
                for s in (mcp_servers or [])
            ],
            mcp_tool_filter=mcp_tool_filter,
            base_profile=base_profile,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def from_profile(
        cls,
        profile_name: str,
        config: dict[str, Any],
    ) -> AgentDefinition:
        """
        Create an agent definition from a profile configuration.

        Args:
            profile_name: Name of the profile (e.g., "dev", "coding_agent")
            config: Parsed YAML configuration
        """
        agent_config = config.get("agent", {})

        # Extract tools as string list
        tools = config.get("tools", [])
        # Filter out any dict-style tools and convert to registry names
        tool_names = []
        for t in tools:
            if isinstance(t, str):
                tool_names.append(t)
            elif isinstance(t, dict):
                # Convert class name to registry name
                class_name = t.get("type", "")
                if class_name:
                    tool_names.append(_class_name_to_tool_name(class_name))
        tool_names = [t for t in tool_names if t]  # Remove empty

        # Extract MCP servers
        mcp_servers = [
            MCPServerConfig.from_dict(s) for s in config.get("mcp_servers", [])
        ]

        return cls(
            agent_id=profile_name,
            name=agent_config.get("name", profile_name.replace("_", " ").title()),
            description=agent_config.get("description", f"Agent from {profile_name} profile"),
            source=AgentSource.PROFILE,
            specialist=agent_config.get("specialist"),
            planning_strategy=agent_config.get("planning_strategy", "native_react"),
            planning_strategy_params=agent_config.get("planning_strategy_params", {}),
            max_steps=agent_config.get("max_steps"),
            tools=tool_names,
            mcp_servers=mcp_servers,
            base_profile=profile_name,
        )

    @classmethod
    def from_plugin(
        cls,
        plugin_path: str,
        manifest: dict[str, Any],
        tool_classes: list[str] | None = None,
    ) -> AgentDefinition:
        """
        Create an agent definition from a plugin.

        Args:
            plugin_path: Path to the plugin directory
            manifest: Plugin manifest/config data
            tool_classes: List of tool class names from the plugin
        """
        import os

        agent_id = os.path.basename(plugin_path.rstrip("/\\"))
        agent_config = manifest.get("agent", {})

        # Extract tools from manifest (native tools to include)
        tools = manifest.get("tools", [])
        tool_names = []
        for t in tools:
            if isinstance(t, str):
                tool_names.append(t)
            elif isinstance(t, dict):
                class_name = t.get("type", "")
                if class_name:
                    tool_names.append(_class_name_to_tool_name(class_name))
        tool_names = [t for t in tool_names if t]

        # Extract MCP servers
        mcp_servers = [
            MCPServerConfig.from_dict(s) for s in manifest.get("mcp_servers", [])
        ]

        return cls(
            agent_id=agent_id,
            name=manifest.get("name", agent_id.replace("_", " ").title()),
            description=manifest.get("description", f"Plugin agent from {plugin_path}"),
            source=AgentSource.PLUGIN,
            system_prompt=agent_config.get("system_prompt", ""),
            specialist=agent_config.get("specialist"),
            planning_strategy=agent_config.get("planning_strategy", "native_react"),
            tools=tool_names,
            mcp_servers=mcp_servers,
            base_profile=manifest.get("base_profile", "dev"),
            work_dir=manifest.get("work_dir"),
            plugin_path=plugin_path,
            tool_classes=tool_classes or [],
        )

    @classmethod
    def from_command(
        cls,
        name: str,
        source_path: str,
        agent_config: dict[str, Any],
        prompt_template: str = "",
        description: str = "",
    ) -> AgentDefinition:
        """
        Create an agent definition from a slash command.

        Args:
            name: Command name (e.g., "agents:dev")
            source_path: Path to the .md file
            agent_config: Agent configuration from frontmatter
            prompt_template: Prompt template with $ARGUMENTS
            description: Command description
        """
        # Extract tools as string list
        tools = agent_config.get("tools", [])
        tool_names = []
        for t in tools:
            if isinstance(t, str):
                tool_names.append(t)
            elif isinstance(t, dict):
                class_name = t.get("type", "")
                if class_name:
                    tool_names.append(_class_name_to_tool_name(class_name))
        tool_names = [t for t in tool_names if t]

        # Extract MCP servers
        mcp_servers = [
            MCPServerConfig.from_dict(s) for s in agent_config.get("mcp_servers", [])
        ]

        return cls(
            agent_id=f"cmd:{name}",
            name=name.replace(":", " - ").title(),
            description=description,
            source=AgentSource.COMMAND,
            system_prompt=agent_config.get("system_prompt", ""),
            specialist=agent_config.get("specialist"),
            tools=tool_names,
            mcp_servers=mcp_servers,
            base_profile=agent_config.get("profile", "dev"),
            source_path=source_path,
            prompt_template=prompt_template,
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation suitable for YAML/JSON serialization.
        """
        result: dict[str, Any] = {
            "agent_id": self.agent_id,
            "name": self.name,
            "source": self.source.value,
        }

        # Add optional fields only if they have values
        if self.description:
            result["description"] = self.description
        if self.system_prompt:
            result["system_prompt"] = self.system_prompt
        if self.specialist:
            result["specialist"] = self.specialist
        if self.planning_strategy != "native_react":
            result["planning_strategy"] = self.planning_strategy
        if self.planning_strategy_params:
            result["planning_strategy_params"] = self.planning_strategy_params
        if self.max_steps:
            result["max_steps"] = self.max_steps
        if self.tools:
            result["tools"] = self.tools
        if self.mcp_servers:
            result["mcp_servers"] = [s.to_dict() for s in self.mcp_servers]
        if self.mcp_tool_filter is not None:
            result["mcp_tool_filter"] = self.mcp_tool_filter
        if self.base_profile != "dev":
            result["base_profile"] = self.base_profile
        if self.work_dir:
            result["work_dir"] = self.work_dir
        if self.plugin_path:
            result["plugin_path"] = self.plugin_path
        if self.tool_classes:
            result["tool_classes"] = self.tool_classes
        if self.source_path:
            result["source_path"] = self.source_path
        if self.prompt_template:
            result["prompt_template"] = self.prompt_template
        if self.created_at:
            result["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            result["updated_at"] = self.updated_at.isoformat()

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentDefinition:
        """
        Create from dictionary.

        Args:
            data: Dictionary with agent definition fields

        Returns:
            AgentDefinition instance
        """
        # Parse timestamps if present
        created_at = None
        updated_at = None
        if data.get("created_at"):
            if isinstance(data["created_at"], str):
                created_at = datetime.fromisoformat(data["created_at"])
            else:
                created_at = data["created_at"]
        if data.get("updated_at"):
            if isinstance(data["updated_at"], str):
                updated_at = datetime.fromisoformat(data["updated_at"])
            else:
                updated_at = data["updated_at"]

        # Parse source
        source = data.get("source", "custom")
        if isinstance(source, str):
            source = AgentSource(source)

        # Parse MCP servers
        mcp_servers = [
            MCPServerConfig.from_dict(s) if isinstance(s, dict) else s
            for s in data.get("mcp_servers", [])
        ]

        return cls(
            agent_id=data["agent_id"],
            name=data.get("name", data["agent_id"]),
            description=data.get("description", ""),
            source=source,
            system_prompt=data.get("system_prompt", ""),
            specialist=data.get("specialist"),
            planning_strategy=data.get("planning_strategy", "native_react"),
            planning_strategy_params=data.get("planning_strategy_params", {}),
            max_steps=data.get("max_steps"),
            tools=data.get("tools", []),
            mcp_servers=mcp_servers,
            mcp_tool_filter=data.get("mcp_tool_filter"),
            base_profile=data.get("base_profile", "dev"),
            work_dir=data.get("work_dir"),
            plugin_path=data.get("plugin_path"),
            tool_classes=data.get("tool_classes", []),
            source_path=data.get("source_path"),
            prompt_template=data.get("prompt_template"),
            created_at=created_at,
            updated_at=updated_at,
        )

    def copy_with(self, **updates: Any) -> AgentDefinition:
        """
        Create a copy with updated fields.

        Args:
            **updates: Fields to update

        Returns:
            New AgentDefinition with updates applied
        """
        data = self.to_dict()
        data.update(updates)
        return AgentDefinition.from_dict(data)


@dataclass
class AgentDefinitionInput:
    """
    Input for creating a new agent definition.

    This is the input model used by APIs - it excludes computed
    fields like timestamps and source.
    """

    agent_id: str
    name: str
    description: str = ""
    system_prompt: str = ""
    specialist: str | None = None
    planning_strategy: str = "native_react"
    tools: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    mcp_tool_filter: list[str] | None = None
    base_profile: str = "dev"
    work_dir: str | None = None

    def to_definition(self) -> AgentDefinition:
        """Convert input to a full AgentDefinition."""
        return AgentDefinition.from_custom(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            system_prompt=self.system_prompt,
            tools=self.tools,
            mcp_servers=self.mcp_servers,
            mcp_tool_filter=self.mcp_tool_filter,
            base_profile=self.base_profile,
        )


@dataclass
class AgentDefinitionUpdate:
    """
    Input for updating an agent definition.

    All fields are optional - only provided fields will be updated.
    """

    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    specialist: str | None = None
    planning_strategy: str | None = None
    tools: list[str] | None = None
    mcp_servers: list[dict[str, Any]] | None = None
    mcp_tool_filter: list[str] | None = None
    base_profile: str | None = None
    work_dir: str | None = None
