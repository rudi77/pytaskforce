"""
Skill Protocol Interfaces

This module defines the protocol interfaces for skill implementations.
Skills are modular capabilities that extend agent functionality with
domain-specific instructions, workflows, and resources.

Skills support three execution types (SkillType):
- CONTEXT: Instructions injected into the system prompt; activated by
  the activate_skill tool or intent routing.
- PROMPT: One-shot prompt template with $ARGUMENTS; invokable directly
  from the chat interface via /skill-name [args].
- AGENT: Temporarily overrides the agent configuration; invokable directly
  from the chat interface via /skill-name [args].

Protocol implementations must provide:
- Skill metadata (name, description, skill_type)
- Instruction loading
- Resource access
- $ARGUMENTS substitution (for PROMPT type)
"""

from typing import Any, Protocol

from taskforce.core.domain.enums import SkillType
from taskforce.core.domain.skill import SkillMetadataModel


class SkillProtocol(Protocol):
    """
    Protocol defining the contract for skill implementations.

    Skills are modular capabilities that provide domain-specific expertise
    to agents. Each skill packages instructions, metadata, and optional
    resources (scripts, templates, documentation).

    Skill Loading Pattern:
        1. Metadata (name, description) is loaded at discovery time
        2. Instructions are loaded when skill is triggered by relevance
        3. Resources are loaded on-demand during execution
    """

    @property
    def name(self) -> str:
        """
        Unique identifier for the skill.

        May be hierarchical using ':' as separator, e.g.
        'pdf-processing' or 'agents:reviewer'.

        Returns:
            Skill name string (max 64 characters)

        Example:
            >>> skill.name
            'pdf-processing'
        """
        ...

    @property
    def description(self) -> str:
        """
        Human-readable description of skill's purpose and trigger conditions.

        Returns:
            Skill description string (max 1024 characters)
        """
        ...

    @property
    def instructions(self) -> str:
        """
        Main instructional content from SKILL.md body.

        For PROMPT-type skills, may contain the $ARGUMENTS placeholder.

        Returns:
            Markdown-formatted instruction text
        """
        ...

    @property
    def source_path(self) -> str:
        """
        Path to the skill's source directory.

        Returns:
            Absolute path to skill directory
        """
        ...

    @property
    def skill_type(self) -> SkillType:
        """
        Execution type determining how the skill is invoked.

        Returns:
            SkillType enum value (CONTEXT, PROMPT, or AGENT)
        """
        ...

    @property
    def slash_name(self) -> str | None:
        """
        Optional override for /name-style invocation.

        If None, the skill's ``name`` is used as the slash name.

        Returns:
            Slash name override, or None
        """
        ...

    @property
    def agent_config(self) -> dict[str, Any] | None:
        """
        Agent configuration override for AGENT-type skills.

        Keys: 'profile', 'tools', 'mcp_servers', 'specialist'

        Returns:
            Agent config dict, or None for non-AGENT skills
        """
        ...

    @property
    def effective_slash_name(self) -> str:
        """
        Effective name used for /name-style invocation.

        Returns slash_name if set, otherwise falls back to name.

        Returns:
            The slash-command name for this skill
        """
        ...

    def substitute_arguments(self, arguments: str) -> str:
        """
        Replace $ARGUMENTS placeholder in the instructions body.

        Args:
            arguments: User-provided arguments string.

        Returns:
            Instructions text with $ARGUMENTS replaced.
        """
        ...

    def get_resources(self) -> dict[str, str]:
        """
        List available resource files in the skill directory.

        Returns:
            Dictionary mapping relative paths to absolute paths
        """
        ...

    def read_resource(self, relative_path: str) -> str | None:
        """
        Read content of a bundled resource file.

        Args:
            relative_path: Path relative to skill directory

        Returns:
            File content as string, or None if file not found
        """
        ...


class SkillRegistryProtocol(Protocol):
    """Protocol for skill discovery and management.

    Implementations are responsible for:
    - Discovering skills from configured locations
    - Loading skill metadata at startup
    - Providing full skills on demand
    - Managing skill lifecycle
    - Resolving skills by slash name

    .. note::
        Methods in this protocol are currently **synchronous** because the
        underlying ``FileSkillRegistry`` reads from the local filesystem
        using synchronous I/O.  If a future implementation needs network
        or database access, these methods should be migrated to ``async``
        (see hexagonal architecture review, finding #10).
    """

    def discover_skills(self) -> list[SkillMetadataModel]:
        """
        Discover all available skills and return their metadata.

        Returns:
            List of skill metadata objects (lightweight, no instructions)
        """
        ...

    def get_skill(self, name: str) -> SkillProtocol | None:
        """
        Load a complete skill by canonical name.

        Args:
            name: Skill identifier

        Returns:
            Full skill object, or None if not found
        """
        ...

    def get_skill_by_slash_name(self, slash_name: str) -> SkillProtocol | None:
        """
        Find a skill by its effective slash name.

        Used for /name-style invocation from the chat interface.

        Args:
            slash_name: The slash-command name (without leading /)

        Returns:
            Full skill object, or None if not found
        """
        ...

    def list_skills(self) -> list[str]:
        """
        List names of all discovered skills.

        Returns:
            List of skill names
        """
        ...

    def list_slash_command_skills(self) -> list[str]:
        """
        List names of skills that are directly invokable via /name.

        Returns only PROMPT and AGENT type skills.

        Returns:
            List of skill names
        """
        ...

    def get_skill_metadata(self, name: str) -> SkillMetadataModel | None:
        """
        Get metadata for a specific skill without loading instructions.

        Args:
            name: Skill identifier

        Returns:
            Skill metadata, or None if not found
        """
        ...

    def refresh(self) -> None:
        """
        Re-scan skill directories and refresh the registry.
        """
        ...

    def get_all_metadata(self) -> list[SkillMetadataModel]:
        """
        Get metadata for all discovered skills.

        Returns:
            List of all skill metadata
        """
        ...


class SkillContextProtocol(Protocol):
    """
    Protocol for managing active skill context during execution.

    Tracks which skills are currently active and provides access
    to skill instructions and resources.
    """

    def activate_skill(self, skill: SkillProtocol) -> None:
        """
        Activate a skill for the current execution context.

        Args:
            skill: The skill to activate
        """
        ...

    def deactivate_skill(self, name: str) -> None:
        """
        Deactivate a skill from the current context.

        Args:
            name: Name of the skill to deactivate
        """
        ...

    def get_active_skills(self) -> list[SkillProtocol]:
        """
        Get list of currently active skills.

        Returns:
            List of active skill objects
        """
        ...

    def get_combined_instructions(self) -> str:
        """
        Get combined instructions from all active skills.

        Returns:
            Concatenated instructions from all active skills
        """
        ...

    def read_skill_resource(self, skill_name: str, resource_path: str) -> str | None:
        """
        Read a resource from an active skill.

        Args:
            skill_name: Name of the skill
            resource_path: Relative path to the resource

        Returns:
            Resource content, or None if not found
        """
        ...
