"""
Slash Command Protocol

Defines the contract for custom slash command implementations.
Commands are Markdown files with optional YAML frontmatter.
Compatible with Claude Code command format.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class CommandType(str, Enum):
    """Type of slash command."""

    PROMPT = "prompt"  # Simple prompt template
    AGENT = "agent"  # Agent with specific profile/tools
    WORKFLOW = "workflow"  # Task workflow (future)


@dataclass
class SlashCommandDefinition:
    """
    Parsed slash command definition.

    Attributes:
        name: Command name (filename without .md)
        source: "project" or "user" (for precedence)
        source_path: Absolute path to the .md file
        command_type: Type of command (prompt, agent, workflow)
        description: Short description from frontmatter
        prompt_template: The prompt text with $ARGUMENTS placeholder
        agent_config: Optional agent configuration (profile, tools, mcp_servers)
        metadata: Additional frontmatter fields
    """

    name: str
    source: str  # "project" | "user"
    source_path: str
    command_type: CommandType
    description: str
    prompt_template: str
    agent_config: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class SlashCommandLoaderProtocol(Protocol):
    """Protocol for loading slash commands from storage."""

    def list_commands(self) -> list[SlashCommandDefinition]:
        """
        List all available commands.

        Returns:
            List of command definitions from all sources.
            Project commands override user commands with same name.
        """
        ...

    def load_command(self, name: str) -> SlashCommandDefinition | None:
        """
        Load a specific command by name.

        Args:
            name: Command name (without leading /)

        Returns:
            Command definition if found, None otherwise.
            Returns project command if both project and user exist.
        """
        ...

    def get_search_paths(self) -> list[str]:
        """
        Return the directories being searched for commands.

        Returns:
            List of directory paths in search order.
        """
        ...
