"""Agent role domain model.

An :class:`AgentRole` defines WHAT an agent is (persona, sub-agents, tools)
while the agent profile YAML defines HOW it runs (persistence, LLM,
scheduler, security).

Roles are loaded from YAML or ``.agent.md`` files via
:class:`taskforce.application.agent_role_loader.AgentRoleLoader` and
merged into the agent configuration at startup.

The pattern was originally developed for the Butler agent (ADR-013, ADR-017)
and generalised to the framework in ADR-027 so any agent-package can ship
role overlays.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentRole:
    """Defines an agent role — persona, capabilities, and behaviour.

    Attributes:
        name: Short identifier for the role (e.g. ``"accountant"``).
        description: Human-readable description of the role.
        persona_prompt: System prompt text that defines the agent's persona.
            May contain ``{{SUB_AGENTS_SECTION}}`` placeholder for dynamic
            sub-agent list injection.
        sub_agents: Sub-agent specifications with ``specialist`` and
            ``description`` keys.
        tools: Tool short names (strings) or tool config dicts.
        event_sources: Event-source configurations specific to this role.
        rules: Trigger-rule configurations specific to this role.
        mcp_servers: MCP-server configurations specific to this role.
    """

    name: str
    description: str = ""
    persona_prompt: str = ""
    sub_agents: tuple[dict[str, str], ...] = ()
    tools: tuple[str | dict[str, Any], ...] = ()
    event_sources: tuple[dict[str, Any], ...] = ()
    rules: tuple[dict[str, Any], ...] = ()
    mcp_servers: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialise the role for storage or transport."""
        return {
            "name": self.name,
            "description": self.description,
            "persona_prompt": self.persona_prompt,
            "sub_agents": list(self.sub_agents),
            "tools": list(self.tools),
            "event_sources": list(self.event_sources),
            "rules": list(self.rules),
            "mcp_servers": list(self.mcp_servers),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentRole:
        """Deserialise a role from a stored dict (e.g. parsed YAML)."""
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            persona_prompt=str(data.get("persona_prompt", "")),
            sub_agents=tuple(data.get("sub_agents", [])),
            tools=tuple(data.get("tools", [])),
            event_sources=tuple(data.get("event_sources", [])),
            rules=tuple(data.get("rules", [])),
            mcp_servers=tuple(data.get("mcp_servers", [])),
        )
