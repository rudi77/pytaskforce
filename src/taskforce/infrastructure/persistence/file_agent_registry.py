"""
File-Based Agent Registry
==========================

Provides CRUD operations for custom agent definitions stored as YAML files.

Responsibilities:
- Persist custom agents to `configs/custom/{agent_id}.yaml`
- List all agents (custom + profile configs)
- Atomic writes for Windows compatibility
- Graceful handling of corrupt YAML files

Story: 8.1 - Custom Agent Registry (CRUD + YAML Persistence)

Clean Architecture Notes:
- Uses Domain Models from core/domain/agent_models.py
- Accepts ToolMapperProtocol via dependency injection
- No direct imports from API or Application layers
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import structlog
import yaml

from taskforce.core.domain.agent_models import (
    CustomAgentDefinition,
    CustomAgentInput,
    CustomAgentUpdateInput,
    ProfileAgentDefinition,
)
from taskforce.core.interfaces.tool_mapping import ToolMapperProtocol

logger = structlog.get_logger()


class FileAgentRegistry:
    """
    File-based agent registry with YAML persistence.

    Manages custom agent definitions and scans profile configurations.

    Directory structure:
        configs/custom/{agent_id}.yaml - Custom agents
        configs/*.yaml - Profile agents (excluding llm_config.yaml)

    Thread Safety:
        Not thread-safe. Use appropriate locking if concurrent access needed.

    Example:
        >>> from taskforce.application.tool_mapper import get_tool_mapper
        >>> registry = FileAgentRegistry(tool_mapper=get_tool_mapper())
        >>> agent = CustomAgentInput(
        ...     agent_id="test-agent",
        ...     name="Test Agent",
        ...     description="Test",
        ...     system_prompt="You are a test agent",
        ...     tool_allowlist=["python"]
        ... )
        >>> created = registry.create_agent(agent)
        >>> assert created.agent_id == "test-agent"
    """

    def __init__(
        self,
        configs_dir: str = "configs",
        tool_mapper: Optional[ToolMapperProtocol] = None,
    ):
        """
        Initialize the agent registry.

        Args:
            configs_dir: Root directory for configuration files.
                        Defaults to "configs" relative to current directory.
            tool_mapper: Optional tool mapper for tool name resolution.
                        If not provided, tool mapping features are disabled.
        """
        self.configs_dir = Path(configs_dir)
        self.custom_dir = self.configs_dir / "custom"
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        self._tool_mapper = tool_mapper
        self.logger = logger.bind(component="file_agent_registry")

    def _get_agent_path(self, agent_id: str) -> Path:
        """Get the file path for an agent definition."""
        return self.custom_dir / f"{agent_id}.yaml"

    def _atomic_write_yaml(self, path: Path, data: dict[str, Any]) -> None:
        """
        Write YAML atomically using temp file + rename.

        Windows-safe implementation:
        1. Write to temp file in same directory
        2. If target exists, delete it first (Windows requirement)
        3. Rename temp to target

        Args:
            path: Target file path
            data: Dictionary to serialize as YAML

        Raises:
            OSError: If file operations fail
        """
        # Write to temp file in same directory (ensures same filesystem)
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

            self.logger.debug(
                "agent.yaml.written", agent_file=str(path), atomic=True
            )

        except Exception:
            # Clean up temp file on error
            if Path(temp_path).exists():
                Path(temp_path).unlink()
            raise

    def _load_custom_agent(self, agent_id: str) -> Optional[CustomAgentDefinition]:
        """
        Load a custom agent from YAML file.

        Args:
            agent_id: Agent identifier

        Returns:
            CustomAgentDefinition if found and valid, None otherwise
        """
        path = self._get_agent_path(agent_id)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            return self._parse_custom_agent_yaml(data, agent_id)

        except Exception as e:
            self.logger.warning(
                "agent.yaml.corrupt",
                agent_id=agent_id,
                path=str(path),
                error=str(e),
            )
            return None

    def _parse_custom_agent_yaml(
        self, data: dict[str, Any], agent_id: str
    ) -> CustomAgentDefinition:
        """
        Parse a custom agent YAML payload into a domain object.

        Args:
            data: YAML payload dictionary
            agent_id: Agent identifier fallback

        Returns:
            Parsed CustomAgentDefinition
        """
        tool_names: list[str] = []
        if "tools" in data:
            for tool_def in data["tools"]:
                # Handle both string tool names and dict tool definitions
                if isinstance(tool_def, str):
                    # Direct tool name string
                    tool_names.append(tool_def)
                elif isinstance(tool_def, dict) and self._tool_mapper:
                    # Dict with type field
                    tool_type = tool_def.get("type")
                    if tool_type is not None:
                        tool_name = self._tool_mapper.get_tool_name(tool_type)
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

    def _load_profile_agent(self, profile_path: Path) -> Optional[ProfileAgentDefinition]:
        """
        Load a profile agent from YAML config file.

        Args:
            profile_path: Path to profile YAML file

        Returns:
            ProfileAgentDefinition if valid, None if corrupt
        """
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # Extract profile name from filename (without .yaml)
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
            self.logger.warning(
                "profile.yaml.corrupt",
                profile=profile_path.name,
                path=str(profile_path),
                error=str(e),
            )
            return None

    def create_agent(self, agent_input: CustomAgentInput) -> CustomAgentDefinition:
        """
        Create a new custom agent.

        Args:
            agent_input: Agent definition input to create

        Returns:
            CustomAgentDefinition with timestamps

        Raises:
            FileExistsError: If agent_id already exists
        """
        path = self._get_agent_path(agent_input.agent_id)

        if path.exists():
            raise FileExistsError(f"Agent '{agent_input.agent_id}' already exists")

        # Add timestamps
        now = datetime.now(timezone.utc).isoformat()
        data = self._build_agent_yaml(
            agent_id=agent_input.agent_id,
            name=agent_input.name,
            description=agent_input.description,
            system_prompt=agent_input.system_prompt,
            tool_allowlist=agent_input.tool_allowlist,
            mcp_servers=agent_input.mcp_servers,
            created_at=now,
            updated_at=now,
        )

        self._atomic_write_yaml(path, data)

        self.logger.info(
            "agent.created", agent_id=agent_input.agent_id, path=str(path)
        )

        # Return domain model
        return CustomAgentDefinition(
            agent_id=agent_input.agent_id,
            name=agent_input.name,
            description=agent_input.description,
            system_prompt=agent_input.system_prompt,
            tool_allowlist=agent_input.tool_allowlist,
            mcp_servers=agent_input.mcp_servers,
            mcp_tool_allowlist=agent_input.mcp_tool_allowlist,
            created_at=now,
            updated_at=now,
        )

    def get_agent(
        self, agent_id: str
    ) -> Optional[CustomAgentDefinition | ProfileAgentDefinition]:
        """
        Get an agent by ID.

        Searches custom agents first, then profile agents.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent definition if found, None otherwise
        """
        # Try custom agents first
        custom = self._load_custom_agent(agent_id)
        if custom:
            return custom

        # Try profile agents (agent_id matches profile name)
        profile_path = self.configs_dir / f"{agent_id}.yaml"
        if profile_path.exists() and agent_id != "llm_config":
            return self._load_profile_agent(profile_path)

        return None

    def list_agents(
        self,
    ) -> list[CustomAgentDefinition | ProfileAgentDefinition]:
        """
        List all agents (custom + profile).

        Scans:
        - configs/custom/*.yaml (custom agents)
        - configs/*.yaml (profile agents, excluding llm_config.yaml)

        Corrupt YAML files are skipped with warning logged.

        Returns:
            List of all valid agent definitions
        """
        agents: list[CustomAgentDefinition | ProfileAgentDefinition] = []

        # Load custom agents
        if self.custom_dir.exists():
            for yaml_file in self.custom_dir.glob("*.yaml"):
                agent_id = yaml_file.stem
                agent = self._load_custom_agent(agent_id)
                if agent:
                    agents.append(agent)

        # Load profile agents
        if self.configs_dir.exists():
            for yaml_file in self.configs_dir.glob("*.yaml"):
                # Skip llm_config.yaml and custom directory
                if yaml_file.name == "llm_config.yaml":
                    continue
                if yaml_file.parent.name == "custom":
                    continue

                profile = self._load_profile_agent(yaml_file)
                if profile:
                    agents.append(profile)

        self.logger.debug("agents.listed", count=len(agents))
        return agents

    def update_agent(
        self, agent_id: str, update_input: CustomAgentUpdateInput
    ) -> CustomAgentDefinition:
        """
        Update an existing custom agent.

        Args:
            agent_id: Agent identifier to update
            update_input: New agent definition values

        Returns:
            Updated CustomAgentDefinition

        Raises:
            FileNotFoundError: If agent doesn't exist
        """
        path = self._get_agent_path(agent_id)

        if not path.exists():
            raise FileNotFoundError(f"Agent '{agent_id}' not found")

        # Load existing to preserve created_at
        existing = self._load_custom_agent(agent_id)
        if not existing:
            raise FileNotFoundError(f"Agent '{agent_id}' is corrupt")

        # Update with new data
        now = datetime.now(timezone.utc).isoformat()
        data = self._build_agent_yaml(
            agent_id=agent_id,
            name=update_input.name,
            description=update_input.description,
            system_prompt=update_input.system_prompt,
            tool_allowlist=update_input.tool_allowlist,
            mcp_servers=update_input.mcp_servers,
            created_at=existing.created_at,
            updated_at=now,
        )

        self._atomic_write_yaml(path, data)

        self.logger.info(
            "agent.updated", agent_id=agent_id, path=str(path)
        )

        # Return domain model
        return CustomAgentDefinition(
            agent_id=agent_id,
            name=update_input.name,
            description=update_input.description,
            system_prompt=update_input.system_prompt,
            tool_allowlist=update_input.tool_allowlist,
            mcp_servers=update_input.mcp_servers,
            mcp_tool_allowlist=update_input.mcp_tool_allowlist,
            created_at=existing.created_at,
            updated_at=now,
        )

    def delete_agent(self, agent_id: str) -> None:
        """
        Delete a custom agent.

        Args:
            agent_id: Agent identifier to delete

        Raises:
            FileNotFoundError: If agent doesn't exist
        """
        path = self._get_agent_path(agent_id)

        if not path.exists():
            raise FileNotFoundError(f"Agent '{agent_id}' not found")

        path.unlink()

        self.logger.info(
            "agent.deleted", agent_id=agent_id, path=str(path)
        )

    def _build_agent_yaml(
        self,
        *,
        agent_id: str,
        name: str,
        description: str,
        system_prompt: str,
        tool_allowlist: list[str],
        mcp_servers: list[dict[str, Any]],
        created_at: str,
        updated_at: str,
    ) -> dict[str, Any]:
        """Build YAML payload for a custom agent definition."""
        tools: list[dict[str, Any]] = []
        if self._tool_mapper:
            tools = self._tool_mapper.map_tools(tool_allowlist)

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
                "router": {"use_llm_classification": True, "max_follow_up_length": 100},
            },
            "persistence": {"type": "file", "work_dir": f".taskforce_{agent_id}"},
            "llm": {"config_path": "configs/llm_config.yaml", "default_model": "main"},
            "logging": {"level": "DEBUG", "format": "console"},
            "tools": tools,
            "mcp_servers": mcp_servers,
            "system_prompt": system_prompt,
        }
