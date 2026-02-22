"""
Agent Serializer
================

Serialization and deserialization helpers for agent YAML definitions.

Converts between raw YAML dictionaries and domain model objects
(CustomAgentDefinition, ProfileAgentDefinition).

Clean Architecture Notes:
- Infrastructure layer: converts external format (YAML dicts) to domain models
- Depends on core/domain/agent_models.py for domain types
- Depends on core/interfaces/tool_mapping.py for tool resolution
"""

from pathlib import Path
from typing import Any

import structlog
import yaml

from taskforce.core.domain.agent_models import (
    CustomAgentDefinition,
    ProfileAgentDefinition,
)
from taskforce.core.interfaces.tool_mapping import ToolMapperProtocol

logger = structlog.get_logger()


def parse_custom_agent_yaml(
    data: dict[str, Any],
    agent_id: str,
    tool_mapper: ToolMapperProtocol | None = None,
) -> CustomAgentDefinition:
    """
    Parse a custom agent YAML payload into a domain object.

    Handles two tool definition formats:
    - String tool names (e.g., "python", "file_read")
    - Dict tool definitions with a "type" field (resolved via tool_mapper)

    The ``tool_allowlist`` key takes precedence over ``tools`` if both exist.

    Args:
        data: YAML payload dictionary.
        agent_id: Agent identifier fallback when ``agent_id`` key is missing.
        tool_mapper: Optional tool mapper for resolving dict-style tool definitions.

    Returns:
        Parsed CustomAgentDefinition.
    """
    tool_names: list[str] = []
    if "tools" in data:
        for tool_def in data["tools"]:
            if isinstance(tool_def, str):
                tool_names.append(tool_def)
            elif isinstance(tool_def, dict) and tool_mapper:
                tool_type = tool_def.get("type")
                if tool_type is not None:
                    tool_name = tool_mapper.get_tool_name(tool_type)
                    if tool_name:
                        tool_names.append(tool_name)

    if "tool_allowlist" in data:
        tool_names = data["tool_allowlist"]

    return CustomAgentDefinition(
        agent_id=data.get("agent_id", agent_id),
        name=data.get("name", agent_id),
        description=data.get("description", ""),
        system_prompt=data.get("system_prompt", ""),
        tool_allowlist=tool_names,
        mcp_servers=data.get("mcp_servers", []),
        mcp_tool_allowlist=data.get("mcp_tool_allowlist", []),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


def parse_profile_agent_yaml(
    profile_path: Path,
) -> ProfileAgentDefinition | None:
    """
    Load and parse a profile agent from a YAML config file.

    Args:
        profile_path: Path to profile YAML file.

    Returns:
        ProfileAgentDefinition if valid, None if the file is corrupt or unreadable.
    """
    try:
        with open(profile_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        profile_name = profile_path.stem

        return ProfileAgentDefinition(
            profile=profile_name,
            specialist=data.get("specialist"),
            tools=data.get("tools", []),
            mcp_servers=data.get("mcp_servers", []),
            llm=data.get("llm", {}),
            persistence=data.get("persistence", {}),
        )

    except Exception as e:
        logger.warning(
            "profile.yaml.corrupt",
            profile=profile_path.name,
            path=str(profile_path),
            error=str(e),
        )
        return None


def build_agent_yaml(
    *,
    agent_id: str,
    name: str,
    description: str,
    system_prompt: str,
    tool_allowlist: list[str],
    mcp_servers: list[dict[str, Any]],
    created_at: str,
    updated_at: str,
    tool_mapper: ToolMapperProtocol | None = None,
) -> dict[str, Any]:
    """
    Build a YAML-serializable dictionary for a custom agent definition.

    Produces the canonical on-disk format used by ``FileAgentRegistry``.

    Args:
        agent_id: Unique agent identifier.
        name: Human-readable agent name.
        description: Agent description text.
        system_prompt: System prompt for the agent.
        tool_allowlist: List of short tool names.
        mcp_servers: MCP server configurations.
        created_at: ISO-8601 creation timestamp.
        updated_at: ISO-8601 last-update timestamp.
        tool_mapper: Optional tool mapper to expand short names into full defs.

    Returns:
        Dictionary ready for YAML serialization.
    """
    tools: list[dict[str, Any]] = []
    if tool_mapper:
        tools = tool_mapper.map_tools(tool_allowlist)

    return {
        "agent_id": agent_id,
        "name": name,
        "description": description,
        "created_at": created_at,
        "updated_at": updated_at,
        "profile": agent_id,
        "specialist": "generic",
        "agent": {
            "enable_fast_path": True,
            "router": {
                "use_llm_classification": True,
                "max_follow_up_length": 100,
            },
        },
        "persistence": {
            "type": "file",
            "work_dir": f".taskforce_{agent_id}",
        },
        "llm": {
            "config_path": "src/taskforce_extensions/configs/llm_config.yaml",
            "default_model": "main",
        },
        "logging": {"level": "DEBUG", "format": "console"},
        "tools": tools,
        "mcp_servers": mcp_servers,
        "system_prompt": system_prompt,
    }
