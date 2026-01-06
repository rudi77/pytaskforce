"""
Agent Domain Models

Core domain entities for agent definitions. These are used by:
- Infrastructure persistence (file_agent_registry)
- API schemas (as Pydantic wrapper base)

These dataclasses represent the domain's view of agents, independent
of API validation or persistence details.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CustomAgentDefinition:
    """
    Domain model for a custom agent definition.

    Represents a user-created agent with custom system prompt and tool allowlist.
    This is the core entity stored and retrieved by the registry.
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


@dataclass
class ProfileAgentDefinition:
    """
    Domain model for a profile-based agent.

    Represents an agent defined by a YAML profile configuration file.
    These are read-only agents defined by the project configuration.
    """

    profile: str
    specialist: str | None = None
    tools: list[str | dict[str, Any]] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    llm: dict[str, Any] = field(default_factory=dict)
    persistence: dict[str, Any] = field(default_factory=dict)
    source: str = "profile"


@dataclass
class CustomAgentInput:
    """
    Input for creating a custom agent.

    Separates creation input from stored entity (no timestamps).
    """

    agent_id: str
    name: str
    description: str
    system_prompt: str
    tool_allowlist: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    mcp_tool_allowlist: list[str] = field(default_factory=list)


@dataclass
class CustomAgentUpdateInput:
    """
    Input for updating a custom agent.

    Contains all mutable fields that can be updated.
    Does not include agent_id (immutable) or timestamps (managed by registry).
    """

    name: str
    description: str
    system_prompt: str
    tool_allowlist: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    mcp_tool_allowlist: list[str] = field(default_factory=list)
