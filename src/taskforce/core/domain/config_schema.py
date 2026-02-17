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
from typing import Any, Optional

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
    command: Optional[str] = Field(
        None,
        description="For stdio: command to run (e.g., 'npx')",
    )
    args: list[str] = Field(
        default_factory=list,
        description="For stdio: command arguments",
    )
    url: Optional[str] = Field(
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
    def validate_server_config(self) -> "MCPServerConfigSchema":
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
    specialist: Optional[str] = Field(
        None,
        description="Specialist type (coding, rag, wiki, or None)",
        pattern="^(coding|rag|wiki)$",
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
    max_steps: Optional[int] = Field(
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
    mcp_tool_filter: Optional[list[str]] = Field(
        None,
        description="List of allowed MCP tool names (None = all allowed)",
    )

    # Infrastructure settings
    base_profile: str = Field(
        "dev",
        description="Base profile for LLM/persistence settings",
    )
    work_dir: Optional[str] = Field(
        None,
        description="Override working directory",
    )

    # Plugin-specific fields
    plugin_path: Optional[str] = Field(
        None,
        description="Path to plugin directory (for source=PLUGIN)",
    )
    tool_classes: list[str] = Field(
        default_factory=list,
        description="List of tool class names from plugin",
    )

    # Command-specific fields
    source_path: Optional[str] = Field(
        None,
        description="Path to source file (for source=COMMAND)",
    )
    prompt_template: Optional[str] = Field(
        None,
        description="Prompt template with $ARGUMENTS (for source=COMMAND)",
    )

    # Timestamps (for CUSTOM agents)
    created_at: Optional[datetime] = Field(
        None,
        description="Creation timestamp",
    )
    updated_at: Optional[datetime] = Field(
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
                raise ValueError(
                    f"tools[{i}]: Tool must be a string, got {type(tool).__name__}"
                )
        return validated


class AutoEpicConfig(BaseModel):
    """Configuration for automatic epic orchestration detection.

    Controls whether the agent automatically classifies mission complexity
    and escalates to epic orchestration (planner/worker/judge) when needed.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description="Enable automatic epic detection.",
    )
    confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to escalate to epic mode.",
    )
    classifier_model: Optional[str] = Field(
        default=None,
        description="LLM model alias for classifier (None = default model).",
    )
    default_worker_count: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Default number of worker agents for epic runs.",
    )
    default_max_rounds: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Default maximum rounds for epic runs.",
    )
    planner_profile: str = Field(
        default="planner",
        description="Profile for the planner agent.",
    )
    worker_profile: str = Field(
        default="worker",
        description="Profile for worker agents.",
    )
    judge_profile: str = Field(
        default="judge",
        description="Profile for the judge agent.",
    )


class ProfileConfigSchema(BaseModel):
    """
    Schema for profile configuration files (configs/*.yaml).

    Validates the structure of profile YAML files.
    """

    model_config = ConfigDict(extra="allow")  # Allow extra fields in profiles

    # Agent settings
    agent: Optional[dict[str, Any]] = Field(
        None,
        description="Agent configuration section",
    )
    specialist: Optional[str] = Field(
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
    persistence: Optional[dict[str, Any]] = Field(
        None,
        description="Persistence configuration",
    )
    llm: Optional[dict[str, Any]] = Field(
        None,
        description="LLM configuration",
    )
    logging: Optional[dict[str, Any]] = Field(
        None,
        description="Logging configuration",
    )
    context_policy: Optional[dict[str, Any]] = Field(
        None,
        description="Context policy configuration",
    )
    orchestration: Optional[dict[str, Any]] = Field(
        None,
        description="Orchestration configuration",
    )


class ConfigValidationError(Exception):
    """
    Error raised when configuration validation fails.

    Includes file path and detailed error message.
    """

    def __init__(
        self,
        message: str,
        file_path: Optional[Path] = None,
        field_path: Optional[str] = None,
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
    file_path: Optional[Path] = None,
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
    file_path: Optional[Path] = None,
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
