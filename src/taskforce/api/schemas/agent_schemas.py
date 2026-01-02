"""
Agent Registry API Schemas
===========================

Pydantic models for Custom Agent Registry API (Story 8.1).

Defines request/response schemas for CRUD operations on custom agents
and profile agents.
"""

from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator
import re


class CustomAgentCreate(BaseModel):
    """Request schema for creating a custom agent."""

    agent_id: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Unique identifier (lowercase alphanumeric, hyphens, underscores)",
    )
    name: str = Field(..., min_length=1, description="Human-readable agent name")
    description: str = Field(..., min_length=1, description="Agent purpose/capabilities")
    system_prompt: str = Field(..., min_length=1, description="LLM system prompt")
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
                "agent_id must be lowercase alphanumeric with hyphens/underscores, 3-64 chars"
            )
        return v


class CustomAgentUpdate(BaseModel):
    """Request schema for updating a custom agent."""

    name: str = Field(..., min_length=1, description="Human-readable agent name")
    description: str = Field(..., min_length=1, description="Agent purpose/capabilities")
    system_prompt: str = Field(..., min_length=1, description="LLM system prompt")
    tool_allowlist: list[str] = Field(
        default_factory=list, description="List of allowed tool names"
    )
    mcp_servers: list[dict[str, Any]] = Field(
        default_factory=list, description="MCP server configurations"
    )
    mcp_tool_allowlist: list[str] = Field(
        default_factory=list, description="List of allowed MCP tool names"
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


class ProfileAgentResponse(BaseModel):
    """Response schema for profile agent (from YAML config)."""

    source: Literal["profile"] = "profile"
    profile: str
    specialist: Optional[str] = None
    tools: list[dict[str, Any]]
    mcp_servers: list[dict[str, Any]]
    llm: dict[str, Any]
    persistence: dict[str, Any]


class AgentListResponse(BaseModel):
    """Response schema for listing all agents."""

    agents: list[CustomAgentResponse | ProfileAgentResponse]

