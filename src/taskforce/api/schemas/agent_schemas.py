"""
Agent Registry API Schemas
===========================

Pydantic models for Custom Agent Registry API (Story 8.1).

Defines request/response schemas for CRUD operations on custom agents
and profile agents.

Clean Architecture Notes:
- These schemas wrap core domain models for API validation
- Provides to_domain() and from_domain() conversion methods
"""

from typing import Any, Literal, Optional

import re
from pydantic import BaseModel, Field, field_validator

from taskforce.core.domain.agent_models import (
    CustomAgentDefinition,
    CustomAgentInput,
    CustomAgentUpdateInput,
    PluginAgentDefinition,
    ProfileAgentDefinition,
)


class CustomAgentCreate(BaseModel):
    """Request schema for creating a custom agent."""

    agent_id: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description=(
            "Unique identifier (lowercase alphanumeric, "
            "hyphens, underscores)"
        ),
    )
    name: str = Field(
        ..., min_length=1, description="Human-readable agent name"
    )
    description: str = Field(
        ..., min_length=1, description="Agent purpose/capabilities"
    )
    system_prompt: str = Field(
        ..., min_length=1, description="LLM system prompt"
    )
    tool_allowlist: list[str] = Field(
        default_factory=list, description="List of allowed tool names"
    )
    mcp_servers: list[dict[str, Any]] = Field(
        default_factory=list, description="MCP server configurations"
    )
    mcp_tool_allowlist: list[str] = Field(
        default_factory=list, description="List of allowed MCP tool names"
    )

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        """Validate agent_id matches filename rules."""
        if not re.match(r"^[a-z0-9_-]{3,64}$", v):
            raise ValueError(
                "agent_id must be lowercase alphanumeric with "
                "hyphens/underscores, 3-64 chars"
            )
        return v

    def to_domain(self) -> CustomAgentInput:
        """Convert to domain input model."""
        return CustomAgentInput(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            system_prompt=self.system_prompt,
            tool_allowlist=self.tool_allowlist,
            mcp_servers=self.mcp_servers,
            mcp_tool_allowlist=self.mcp_tool_allowlist,
        )


class CustomAgentUpdate(BaseModel):
    """Request schema for updating a custom agent."""

    name: str = Field(
        ..., min_length=1, description="Human-readable agent name"
    )
    description: str = Field(
        ..., min_length=1, description="Agent purpose/capabilities"
    )
    system_prompt: str = Field(
        ..., min_length=1, description="LLM system prompt"
    )
    tool_allowlist: list[str] = Field(
        default_factory=list, description="List of allowed tool names"
    )
    mcp_servers: list[dict[str, Any]] = Field(
        default_factory=list, description="MCP server configurations"
    )
    mcp_tool_allowlist: list[str] = Field(
        default_factory=list, description="List of allowed MCP tool names"
    )

    def to_domain(self) -> CustomAgentUpdateInput:
        """Convert to domain update input model."""
        return CustomAgentUpdateInput(
            name=self.name,
            description=self.description,
            system_prompt=self.system_prompt,
            tool_allowlist=self.tool_allowlist,
            mcp_servers=self.mcp_servers,
            mcp_tool_allowlist=self.mcp_tool_allowlist,
        )


class CustomAgentResponse(BaseModel):
    """Response schema for custom agent (with timestamps)."""

    source: Literal["custom"] = "custom"
    agent_id: str
    name: str
    description: str
    system_prompt: str
    tool_allowlist: list[str]
    mcp_servers: list[dict[str, Any]]
    mcp_tool_allowlist: list[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(
        cls, domain: CustomAgentDefinition
    ) -> "CustomAgentResponse":
        """Create response from domain model."""
        return cls(
            agent_id=domain.agent_id,
            name=domain.name,
            description=domain.description,
            system_prompt=domain.system_prompt,
            tool_allowlist=domain.tool_allowlist,
            mcp_servers=domain.mcp_servers,
            mcp_tool_allowlist=domain.mcp_tool_allowlist,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
        )


class ProfileAgentResponse(BaseModel):
    """Response schema for profile agent (from YAML config)."""

    source: Literal["profile"] = "profile"
    profile: str
    specialist: Optional[str] = None
    tools: list[str | dict[str, Any]]
    mcp_servers: list[dict[str, Any]]
    llm: dict[str, Any]
    persistence: dict[str, Any]

    @classmethod
    def from_domain(
        cls, domain: ProfileAgentDefinition
    ) -> "ProfileAgentResponse":
        """Create response from domain model."""
        return cls(
            profile=domain.profile,
            specialist=domain.specialist,
            tools=domain.tools,
            mcp_servers=domain.mcp_servers,
            llm=domain.llm,
            persistence=domain.persistence,
        )


class PluginAgentResponse(BaseModel):
    """Response schema for plugin agent (from external plugin dir)."""

    source: Literal["plugin"] = "plugin"
    agent_id: str
    name: str
    description: str
    plugin_path: str
    tool_classes: list[str]
    specialist: Optional[str] = None
    mcp_servers: list[dict[str, Any]]

    @classmethod
    def from_domain(
        cls, domain: PluginAgentDefinition
    ) -> "PluginAgentResponse":
        """Create response from domain model."""
        return cls(
            agent_id=domain.agent_id,
            name=domain.name,
            description=domain.description,
            plugin_path=domain.plugin_path,
            tool_classes=domain.tool_classes,
            specialist=domain.specialist,
            mcp_servers=domain.mcp_servers,
        )


class AgentListResponse(BaseModel):
    """Response schema for listing all agents."""

    agents: list[
        CustomAgentResponse | ProfileAgentResponse | PluginAgentResponse
    ]
