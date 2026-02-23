"""
Agent Domain Models (Legacy)

.. deprecated::
    These models are superseded by the unified ``AgentDefinition`` model in
    ``taskforce.core.domain.agent_definition``.  New code should use
    ``AgentDefinition``, ``AgentDefinitionInput``, and ``AgentDefinitionUpdate``
    directly.  Each legacy class provides a ``to_unified()`` helper to convert
    an instance to the new unified model, easing incremental migration.

Core domain entities for agent definitions. These are used by:
- Infrastructure persistence (file_agent_registry)
- API schemas (as Pydantic wrapper base)

These dataclasses represent the domain's view of agents, independent
of API validation or persistence details.

Migration guide
---------------
+---------------------------+----------------------------------------------+
| Legacy class              | Unified replacement                          |
+===========================+==============================================+
| CustomAgentDefinition     | AgentDefinition(source=AgentSource.CUSTOM)   |
| ProfileAgentDefinition    | AgentDefinition(source=AgentSource.PROFILE)  |
| PluginAgentDefinition     | AgentDefinition(source=AgentSource.PLUGIN)   |
| CustomAgentInput          | AgentDefinitionInput                         |
| CustomAgentUpdateInput    | AgentDefinitionUpdate                        |
+---------------------------+----------------------------------------------+

Field mapping notes (legacy -> unified):
- tool_allowlist       -> tools
- mcp_tool_allowlist   -> mcp_tool_filter
- created_at (str)     -> created_at (datetime | None)
- updated_at (str)     -> updated_at (datetime | None)
- profile              -> agent_id / base_profile
- llm, persistence     -> (no direct equivalent; use base_profile to inherit)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from taskforce.core.domain.agent_definition import (
        AgentDefinition,
        AgentDefinitionInput,
        AgentDefinitionUpdate,
    )


def _parse_iso_timestamp(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp string, returning None for empty strings.

    Args:
        value: ISO-8601 timestamp string, or empty string.

    Returns:
        Parsed datetime or None if the input is empty/unparseable.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


@dataclass
class CustomAgentDefinition:
    """
    Domain model for a custom agent definition.

    Represents a user-created agent with custom system prompt and
    tool allowlist. This is the core entity stored and retrieved by
    the registry.

    .. deprecated::
        Use ``AgentDefinition`` with ``source=AgentSource.CUSTOM`` instead.
        Call ``to_unified()`` to convert this instance.
    """

    agent_id: str
    name: str
    description: str
    system_prompt: str
    tool_allowlist: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    mcp_tool_allowlist: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    source: str = "custom"

    def to_unified(self) -> AgentDefinition:
        """Convert to the unified ``AgentDefinition`` model.

        Returns:
            An ``AgentDefinition`` with ``source=AgentSource.CUSTOM`` and
            fields mapped from this legacy model.
        """
        from taskforce.core.domain.agent_definition import (
            AgentDefinition,
            AgentSource,
            MCPServerConfig,
        )

        return AgentDefinition(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            source=AgentSource.CUSTOM,
            system_prompt=self.system_prompt,
            tools=list(self.tool_allowlist),
            mcp_servers=[MCPServerConfig.from_dict(s) for s in self.mcp_servers],
            mcp_tool_filter=list(self.mcp_tool_allowlist) if self.mcp_tool_allowlist else None,
            created_at=_parse_iso_timestamp(self.created_at),
            updated_at=_parse_iso_timestamp(self.updated_at),
        )


@dataclass
class ProfileAgentDefinition:
    """
    Domain model for a profile-based agent.

    Represents an agent defined by a YAML profile configuration file.
    These are read-only agents defined by the project configuration.

    .. deprecated::
        Use ``AgentDefinition`` with ``source=AgentSource.PROFILE`` instead.
        Call ``to_unified()`` to convert this instance.
    """

    profile: str
    specialist: str | None = None
    tools: list[str | dict[str, Any]] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    llm: dict[str, Any] = field(default_factory=dict)
    persistence: dict[str, Any] = field(default_factory=dict)
    source: str = "profile"

    def to_unified(self) -> AgentDefinition:
        """Convert to the unified ``AgentDefinition`` model.

        Note:
            The ``llm`` and ``persistence`` dicts have no direct equivalent
            in ``AgentDefinition``. These settings are inherited when the
            agent is created through the factory using ``base_profile``.

        Returns:
            An ``AgentDefinition`` with ``source=AgentSource.PROFILE`` and
            fields mapped from this legacy model.
        """
        from taskforce.core.domain.agent_definition import (
            AgentDefinition,
            AgentSource,
            MCPServerConfig,
        )

        # Extract string tool names, skipping dict-style tool definitions
        tool_names: list[str] = []
        for t in self.tools:
            if isinstance(t, str):
                tool_names.append(t)

        return AgentDefinition(
            agent_id=self.profile,
            name=self.profile.replace("_", " ").title(),
            description=f"Agent from {self.profile} profile",
            source=AgentSource.PROFILE,
            specialist=self.specialist,
            tools=tool_names,
            mcp_servers=[MCPServerConfig.from_dict(s) for s in self.mcp_servers],
            base_profile=self.profile,
        )


@dataclass
class PluginAgentDefinition:
    """
    Domain model for a plugin-based agent.

    Represents an agent defined by an external plugin directory
    (e.g., examples/accounting_agent). These are read-only agents
    discovered from plugin directories.

    .. deprecated::
        Use ``AgentDefinition`` with ``source=AgentSource.PLUGIN`` instead.
        Call ``to_unified()`` to convert this instance.
    """

    agent_id: str
    """Agent identifier derived from plugin path or name."""

    name: str
    """Human-readable agent name (from plugin manifest or config)."""

    description: str
    """Agent description (from plugin config if available)."""

    plugin_path: str
    """Relative path to plugin directory."""

    tool_classes: list[str] = field(default_factory=list)
    """List of tool class names exported by the plugin."""

    specialist: str | None = None
    """Specialist type from plugin config (if available)."""

    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    """MCP server configurations from plugin config."""

    source: str = "plugin"

    def to_unified(self) -> AgentDefinition:
        """Convert to the unified ``AgentDefinition`` model.

        Returns:
            An ``AgentDefinition`` with ``source=AgentSource.PLUGIN`` and
            fields mapped from this legacy model.
        """
        from taskforce.core.domain.agent_definition import (
            AgentDefinition,
            AgentSource,
            MCPServerConfig,
        )

        return AgentDefinition(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            source=AgentSource.PLUGIN,
            specialist=self.specialist,
            mcp_servers=[MCPServerConfig.from_dict(s) for s in self.mcp_servers],
            plugin_path=self.plugin_path,
            tool_classes=list(self.tool_classes),
        )


@dataclass
class CustomAgentInput:
    """
    Input for creating a custom agent.

    Separates creation input from stored entity (no timestamps).

    .. deprecated::
        Use ``AgentDefinitionInput`` instead.
        Call ``to_unified()`` to convert this instance.
    """

    agent_id: str
    name: str
    description: str
    system_prompt: str
    tool_allowlist: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    mcp_tool_allowlist: list[str] = field(default_factory=list)

    def to_unified(self) -> AgentDefinitionInput:
        """Convert to the unified ``AgentDefinitionInput`` model.

        Returns:
            An ``AgentDefinitionInput`` with fields mapped from this
            legacy model.
        """
        from taskforce.core.domain.agent_definition import AgentDefinitionInput

        return AgentDefinitionInput(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            system_prompt=self.system_prompt,
            tools=list(self.tool_allowlist),
            mcp_servers=[dict(s) for s in self.mcp_servers],
            mcp_tool_filter=list(self.mcp_tool_allowlist) if self.mcp_tool_allowlist else None,
        )


@dataclass
class CustomAgentUpdateInput:
    """
    Input for updating a custom agent.

    Contains all mutable fields that can be updated.
    Does not include agent_id (immutable) or timestamps (managed by registry).

    .. deprecated::
        Use ``AgentDefinitionUpdate`` instead.
        Call ``to_unified()`` to convert this instance.
    """

    name: str
    description: str
    system_prompt: str
    tool_allowlist: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    mcp_tool_allowlist: list[str] = field(default_factory=list)

    def to_unified(self) -> AgentDefinitionUpdate:
        """Convert to the unified ``AgentDefinitionUpdate`` model.

        Returns:
            An ``AgentDefinitionUpdate`` with fields mapped from this
            legacy model.
        """
        from taskforce.core.domain.agent_definition import AgentDefinitionUpdate

        return AgentDefinitionUpdate(
            name=self.name,
            description=self.description,
            system_prompt=self.system_prompt,
            tools=list(self.tool_allowlist),
            mcp_servers=[dict(s) for s in self.mcp_servers],
            mcp_tool_filter=list(self.mcp_tool_allowlist) if self.mcp_tool_allowlist else None,
        )
