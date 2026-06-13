"""
Configuration Schema Validation

Pydantic models for validating agent and profile configurations.
Provides clear error messages with file and field context.

Part of Phase 5 refactoring: Config Schema & Validation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentSourceType(str, Enum):
    """Source/origin of an agent definition."""

    CUSTOM = "custom"
    PROFILE = "profile"
    PLUGIN = "plugin"
    COMMAND = "command"


class MCPServerConfigSchema(BaseModel):
    """Schema for MCP server configuration."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        ...,
        description="Server type: 'stdio' or 'sse'",
        pattern="^(stdio|sse)$",
    )
    command: str | None = Field(
        None,
        description="For stdio: command to run (e.g., 'npx')",
    )
    args: list[str] = Field(
        default_factory=list,
        description="For stdio: command arguments",
    )
    url: str | None = Field(
        None,
        description="For sse: server URL",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables",
    )
    description: str = Field(
        "",
        description="Human-readable description",
    )

    @model_validator(mode="after")
    def validate_server_config(self) -> MCPServerConfigSchema:
        """Validate that stdio has command and sse has url."""
        if self.type == "stdio" and not self.command:
            raise ValueError("stdio server requires 'command' field")
        if self.type == "sse" and not self.url:
            raise ValueError("sse server requires 'url' field")
        return self


class AgentConfigSchema(BaseModel):
    """
    Schema for unified agent configuration.

    Validates agent definitions from all sources (custom, profile, plugin, command).
    Tools must be specified as string list only (no dict format).
    """

    model_config = ConfigDict(extra="forbid")

    # Required identification
    agent_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Unique identifier for the agent",
        pattern="^[a-zA-Z0-9_:-]+$",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Human-readable display name",
    )

    # Optional descriptive fields
    description: str = Field(
        "",
        max_length=2048,
        description="Description of what the agent does",
    )
    source: AgentSourceType = Field(
        AgentSourceType.CUSTOM,
        description="Origin of the definition",
    )

    # Agent behavior configuration
    system_prompt: str = Field(
        "",
        max_length=65536,
        description="Custom system prompt",
    )
    specialist: str | None = Field(
        None,
        description="Specialist/role tag (coding, rag, wiki, butler, or a custom role name)",
        pattern="^[a-zA-Z0-9_-]+$",
    )
    planning_strategy: str = Field(
        "native_react",
        description="Planning strategy to use",
        pattern="^(native_react|plan_and_execute|plan_and_react|spar)$",
    )
    planning_strategy_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the planning strategy",
    )
    max_steps: int | None = Field(
        None,
        gt=0,
        le=1000,
        description="Maximum execution steps",
    )

    # Tools - ONLY string list
    tools: list[str] = Field(
        default_factory=list,
        description="List of tool names (strings only, no dicts)",
    )

    # MCP configuration
    mcp_servers: list[MCPServerConfigSchema] = Field(
        default_factory=list,
        description="MCP server configurations",
    )
    mcp_tool_filter: list[str] | None = Field(
        None,
        description="List of allowed MCP tool names (None = all allowed)",
    )

    # Infrastructure settings
    base_profile: str = Field(
        "dev",
        description="Base profile for LLM/persistence settings",
    )
    work_dir: str | None = Field(
        None,
        description="Override working directory",
    )

    # Plugin-specific fields
    plugin_path: str | None = Field(
        None,
        description="Path to plugin directory (for source=PLUGIN)",
    )
    tool_classes: list[str] = Field(
        default_factory=list,
        description="List of tool class names from plugin",
    )

    # Command-specific fields
    source_path: str | None = Field(
        None,
        description="Path to source file (for source=COMMAND)",
    )
    prompt_template: str | None = Field(
        None,
        description="Prompt template with $ARGUMENTS (for source=COMMAND)",
    )

    # Timestamps (for CUSTOM agents)
    created_at: datetime | None = Field(
        None,
        description="Creation timestamp",
    )
    updated_at: datetime | None = Field(
        None,
        description="Last update timestamp",
    )

    @field_validator("tools", mode="before")
    @classmethod
    def validate_tools_are_strings(cls, v: Any) -> list[str]:
        """Ensure tools are string list only, not dicts."""
        if not isinstance(v, list):
            raise ValueError("tools must be a list")

        validated = []
        for i, tool in enumerate(v):
            if isinstance(tool, str):
                validated.append(tool)
            elif isinstance(tool, dict):
                raise ValueError(
                    f"tools[{i}]: Tool must be a string (tool name), not a dict. "
                    f"Use the tool's registry name like 'web_search' or 'python'. "
                    f"Got: {tool}"
                )
            else:
                raise ValueError(f"tools[{i}]: Tool must be a string, got {type(tool).__name__}")
        return validated


class AcpAuthSchema(BaseModel):
    """ACP peer authentication block."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        "none",
        pattern="^(none|bearer|mtls)$",
        description="Auth scheme: none, bearer or mtls",
    )
    token_env: str | None = Field(
        None,
        description="Environment variable holding the bearer token",
    )
    token: str | None = Field(
        None,
        description="Literal bearer token (prefer token_env)",
    )
    cert_path: str | None = Field(None, description="mTLS client certificate path")
    key_path: str | None = Field(None, description="mTLS client key path")


class AcpPeerSchema(BaseModel):
    """Remote ACP peer descriptor."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, pattern="^[a-zA-Z0-9_:-]+$")
    base_url: str = Field(..., min_length=1)
    agent: str = Field(..., min_length=1)
    description: str = Field("", max_length=1024)
    tenant_id: str = "default"
    allow_cross_tenant: bool = False
    auth: AcpAuthSchema = Field(default_factory=AcpAuthSchema)


class AcpServerSchema(BaseModel):
    """Local ACP server settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = Field(8800, gt=0, lt=65536)
    agent_name: str | None = Field(
        None,
        description="Name under which the profile agent is exposed (defaults to profile name)",
    )
    expose_profile: bool = Field(
        True,
        description="Expose the configured profile agent as an ACP agent",
    )
    expose_bus_topics: list[str] = Field(
        default_factory=list,
        description="Message bus topics to expose as ACP agents (bus_<topic>)",
    )


class AcpMessageBusSchema(BaseModel):
    """Message bus transport selector."""

    model_config = ConfigDict(extra="forbid")

    transport: str = Field(
        "in_memory",
        pattern="^(in_memory|acp)$",
        description="Bus transport: in_memory (default) or acp",
    )
    publish_peers: list[str] = Field(
        default_factory=list,
        description="Peer names that receive published messages",
    )
    subscribe_topics: list[str] = Field(
        default_factory=list,
        description="Topics this instance subscribes to",
    )


class AcpConfigSchema(BaseModel):
    """Top-level ACP configuration block for a profile."""

    model_config = ConfigDict(extra="forbid")

    server: AcpServerSchema = Field(default_factory=AcpServerSchema)
    peers: list[AcpPeerSchema] = Field(default_factory=list)
    message_bus: AcpMessageBusSchema = Field(default_factory=AcpMessageBusSchema)


class A2aAuthSchema(BaseModel):
    """A2A peer authentication block.

    Extends the ACP auth schema with OAuth2/OIDC fields: ``provider``
    resolves through the existing ``AuthManager``, ``scopes`` declares
    the scopes the client must request, and ``client_id_env`` /
    ``token_url`` are escape hatches for non-OAuth providers.
    """

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        "none",
        pattern="^(none|api_key|bearer|oauth2|oidc|mtls)$",
        description="A2A auth scheme",
    )
    token_env: str | None = Field(None, description="Env var holding the bearer token / API key")
    token: str | None = Field(None, description="Literal token (prefer token_env)")
    api_key_header: str | None = Field(
        None, description="Header name for api_key scheme (e.g. X-API-Key)"
    )
    provider: str | None = Field(None, description="AuthManager provider id for oauth2/oidc")
    scopes: list[str] = Field(default_factory=list, description="OAuth2 scopes")
    client_id_env: str | None = Field(None, description="Env var for OAuth2 client id")
    token_url: str | None = Field(None, description="OAuth2 token endpoint")
    cert_path: str | None = Field(None, description="mTLS client certificate path")
    key_path: str | None = Field(None, description="mTLS client key path")


class A2aPeerSchema(BaseModel):
    """Remote A2A peer descriptor."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, pattern="^[a-zA-Z0-9_:-]+$")
    base_url: str = Field(..., min_length=1)
    agent_card_url: str | None = Field(
        None,
        description=(
            "Override for the agent card URL (default: " "{base_url}/.well-known/agent-card.json)"
        ),
    )
    description: str = Field("", max_length=1024)
    tenant_id: str = "default"
    allow_cross_tenant: bool = False
    preferred_transport: str = Field(
        "json_rpc",
        pattern="^(json_rpc|rest|grpc)$",
        description="Transport selector (iter 1: json_rpc supported)",
    )
    poll_interval_seconds: int = Field(
        5, gt=0, le=300, description="Polling fallback interval when push is unavailable"
    )
    auth: A2aAuthSchema = Field(default_factory=A2aAuthSchema)


class A2aArtifactSchema(BaseModel):
    """Artifact retention policy."""

    model_config = ConfigDict(extra="forbid")

    retention_days: int = Field(
        7, ge=0, le=3650, description="Days to keep artifacts (0 = forever)"
    )
    work_dir: str | None = Field(
        None,
        description="Override directory for stored artifacts (default: <work_dir>/a2a_artifacts)",
    )


class A2aPushSchema(BaseModel):
    """Push-notification webhook settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(False, description="Enable webhook reception")
    public_callback_url: str | None = Field(
        None,
        description=(
            "Publicly reachable URL pytaskforce advertises to remote peers as its "
            "push-notification target (default: derived from server.host:port)"
        ),
    )


class A2aServerSchema(BaseModel):
    """Local A2A server settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = Field(9000, gt=0, lt=65536)
    public_url: str | None = Field(
        None,
        description=(
            "Externally-reachable origin advertised in the AgentCard "
            "(e.g. https://agent.example.com). Required when ``host`` is "
            "0.0.0.0 — otherwise remote peers cannot route to the "
            "published base_url."
        ),
    )
    agent_name: str | None = Field(
        None,
        description="Card name (defaults to the profile name)",
    )
    agent_description: str | None = Field(
        None, description="Card description (defaults to the profile description)"
    )
    expose_profile: bool = Field(
        True,
        description="Expose the configured profile agent over A2A",
    )
    auth: A2aAuthSchema = Field(
        default_factory=A2aAuthSchema,
        description="Auth scheme advertised in our AgentCard",
    )


class A2aConfigSchema(BaseModel):
    """Top-level A2A configuration block for a profile."""

    model_config = ConfigDict(extra="forbid")

    server: A2aServerSchema = Field(default_factory=A2aServerSchema)
    peers: list[A2aPeerSchema] = Field(default_factory=list)
    artifacts: A2aArtifactSchema = Field(default_factory=A2aArtifactSchema)
    push: A2aPushSchema = Field(default_factory=A2aPushSchema)


class ProfileConfigSchema(BaseModel):
    """
    Schema for profile configuration files (configs/*.yaml).

    Validates the structure of profile YAML files.
    """

    model_config = ConfigDict(extra="allow")  # Allow extra fields in profiles

    # Agent settings
    agent: dict[str, Any] | None = Field(
        None,
        description="Agent configuration section",
    )
    specialist: str | None = Field(
        None,
        description="Specialist type",
    )

    # Tools - can be string list or legacy dict format (for backwards compatibility)
    tools: list[str | dict[str, Any]] = Field(
        default_factory=list,
        description="List of tools",
    )

    # MCP servers
    mcp_servers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="MCP server configurations",
    )

    # Infrastructure
    persistence: dict[str, Any] | None = Field(
        None,
        description="Persistence configuration",
    )
    llm: dict[str, Any] | None = Field(
        None,
        description="LLM configuration",
    )
    logging: dict[str, Any] | None = Field(
        None,
        description="Logging configuration",
    )
    context_policy: dict[str, Any] | None = Field(
        None,
        description="Context policy configuration",
    )
    orchestration: dict[str, Any] | None = Field(
        None,
        description="Orchestration configuration",
    )
    acp: AcpConfigSchema | None = Field(
        None,
        description="ACP (Agent Communication Protocol) configuration",
    )
    a2a: A2aConfigSchema | None = Field(
        None,
        description="A2A (Agent-to-Agent protocol) configuration",
    )

    # Agent-runtime selector (multi-runtime support).
    # Default ``"taskforce"`` keeps existing profiles unchanged. Foreign
    # runtimes (Hermes, OpenClaw, …) ship their own adapter and register
    # themselves with ``agent_runtime_registry`` at import time; profiles
    # then opt in via ``runtime: hermes`` (etc.).
    runtime: str = Field(
        "taskforce",
        description="Top-level agent runtime selector (taskforce, hermes, openclaw, ...)",
        pattern="^[a-zA-Z0-9_:-]+$",
    )
    runtime_config: dict[str, Any] | None = Field(
        None,
        description="Adapter-specific configuration passed verbatim to the runtime factory",
    )
    # Runtime-tracking (heartbeats / checkpoints) config. Distinct from the
    # ``runtime`` selector above — kept as a separate key to avoid the
    # type collision that previously warned on every butler load (issue #456).
    # Consumed by InfrastructureBuilder.build_runtime_tracker (enabled/store/
    # work_dir). A legacy dict-valued ``runtime`` is still honoured there.
    runtime_tracking: dict[str, Any] | None = Field(
        None,
        description="Runtime tracking (heartbeats/checkpoints) config: enabled, store, work_dir",
    )

    # Raw technical block (used by .agent.md files before the loader flattens
    # it onto the top level). Retained so Pydantic doesn't reject it during
    # post-flattening validation of mid-pipeline configs.
    technical: dict[str, Any] | None = Field(
        None,
        description="Technical settings block (flattened onto top level by loader)",
    )
    extends: str | list[str] | None = Field(
        None,
        description="Preset name(s) to inherit from (resolved via configs/presets/)",
    )


class ConfigValidationError(Exception):
    """
    Error raised when configuration validation fails.

    Includes file path and detailed error message.
    """

    def __init__(
        self,
        message: str,
        file_path: Path | None = None,
        field_path: str | None = None,
    ):
        self.file_path = file_path
        self.field_path = field_path

        # Build detailed message
        parts = []
        if file_path:
            parts.append(f"File: {file_path}")
        if field_path:
            parts.append(f"Field: {field_path}")
        parts.append(message)

        super().__init__(" | ".join(parts))


def validate_agent_config(
    data: dict[str, Any],
    file_path: Path | None = None,
) -> AgentConfigSchema:
    """
    Validate agent configuration data.

    Args:
        data: Configuration dictionary
        file_path: Optional file path for error messages

    Returns:
        Validated AgentConfigSchema

    Raises:
        ConfigValidationError: If validation fails
    """
    try:
        return AgentConfigSchema(**data)
    except Exception as e:
        raise ConfigValidationError(
            str(e),
            file_path=file_path,
        ) from e


def validate_profile_config(
    data: dict[str, Any],
    file_path: Path | None = None,
) -> ProfileConfigSchema:
    """
    Validate profile configuration data.

    Args:
        data: Configuration dictionary
        file_path: Optional file path for error messages

    Returns:
        Validated ProfileConfigSchema

    Raises:
        ConfigValidationError: If validation fails
    """
    try:
        return ProfileConfigSchema(**data)
    except Exception as e:
        raise ConfigValidationError(
            str(e),
            file_path=file_path,
        ) from e


def extract_tool_names(tools: list[str | dict[str, Any]]) -> list[str]:
    """
    Extract tool names from a mixed list of strings and dicts.

    For backwards compatibility with legacy dict-style tool configs.

    Args:
        tools: List of tool specs (strings or dicts)

    Returns:
        List of tool names as strings
    """
    names = []
    for tool in tools:
        if isinstance(tool, str):
            names.append(tool)
        elif isinstance(tool, dict):
            # Try to extract name from dict
            tool_type = tool.get("type", "")
            if tool_type:
                # Convert class name to snake_case tool name
                # e.g., "WebSearchTool" -> "web_search"
                name = _class_name_to_tool_name(tool_type)
                if name:
                    names.append(name)
    return names


def _class_name_to_tool_name(class_name: str) -> str:
    """
    Convert a tool class name to registry name.

    Args:
        class_name: Class name like "WebSearchTool"

    Returns:
        Registry name like "web_search"
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
