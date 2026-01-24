"""
Skill Protocol Interfaces

This module defines the protocol interfaces for skill implementations.
Skills are modular capabilities that extend agent functionality with
domain-specific instructions, workflows, and resources.

Skills follow a progressive loading pattern:
- Level 1 (Metadata): Name and description - always loaded
- Level 2 (Instructions): Main SKILL.md content - loaded when triggered
- Level 3 (Resources): Additional files and scripts - loaded as needed

Protocol implementations must provide:
- Skill metadata (name, description)
- Instruction loading
- Resource access
"""

from typing import Any, Protocol


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

    Attributes:
        name: Unique identifier for the skill (lowercase, hyphenated)
        description: What the skill does and when to use it
        instructions: Main content from SKILL.md
        resources: Available resource files
    """

    @property
    def name(self) -> str:
        """
        Unique identifier for the skill.

        Must be:
        - Lowercase with hyphens (kebab-case)
        - Descriptive and concise (e.g., "pdf-processing", "code-review")
        - Maximum 64 characters
        - Cannot contain reserved words: "anthropic", "claude"

        Returns:
            Skill name string

        Example:
            >>> skill.name
            'pdf-processing'
        """
        ...

    @property
    def description(self) -> str:
        """
        Human-readable description of skill's purpose and trigger conditions.

        Should include:
        - What the skill does (1-2 sentences)
        - When Claude should use it (trigger conditions)
        - Key capabilities provided

        This description is used by the agent to determine when to
        activate the skill based on user requests.

        Returns:
            Skill description string (max 1024 characters)

        Example:
            >>> skill.description
            'Extract text and tables from PDF files, fill forms, merge documents.
             Use when working with PDF files or when the user mentions PDFs.'
        """
        ...

    @property
    def instructions(self) -> str:
        """
        Main instructional content from SKILL.md body.

        Contains the procedural knowledge: workflows, best practices,
        code examples, and guidance that the agent follows when using
        this skill.

        Loaded on-demand when the skill is triggered, to minimize
        context usage when skill is not active.

        Returns:
            Markdown-formatted instruction text

        Example:
            >>> skill.instructions[:100]
            '# PDF Processing\\n\\n## Quick start\\n\\nUse pdfplumber to extract...'
        """
        ...

    @property
    def source_path(self) -> str:
        """
        Path to the skill's source directory.

        Points to the directory containing SKILL.md and any bundled
        resources. Used for loading additional files on demand.

        Returns:
            Absolute path to skill directory

        Example:
            >>> skill.source_path
            '/home/user/.taskforce/skills/pdf-processing'
        """
        ...

    def get_resources(self) -> dict[str, str]:
        """
        List available resource files in the skill directory.

        Returns a mapping of relative file paths to their full paths.
        Does not include SKILL.md itself.

        Returns:
            Dictionary mapping relative paths to absolute paths

        Example:
            >>> skill.get_resources()
            {
                'FORMS.md': '/path/to/skill/FORMS.md',
                'scripts/fill_form.py': '/path/to/skill/scripts/fill_form.py'
            }
        """
        ...

    def read_resource(self, relative_path: str) -> str | None:
        """
        Read content of a bundled resource file.

        Args:
            relative_path: Path relative to skill directory

        Returns:
            File content as string, or None if file not found

        Example:
            >>> content = skill.read_resource('FORMS.md')
            >>> content[:50]
            '# Form Filling Guide\\n\\n## PDF Form Fields...'
        """
        ...


class SkillMetadata(Protocol):
    """
    Lightweight metadata for skill discovery.

    Contains only the information needed for skill matching
    without loading the full instructions.
    """

    @property
    def name(self) -> str:
        """Skill identifier."""
        ...

    @property
    def description(self) -> str:
        """Skill description for trigger matching."""
        ...

    @property
    def source_path(self) -> str:
        """Path to skill directory."""
        ...


class SkillRegistryProtocol(Protocol):
    """
    Protocol for skill discovery and management.

    Implementations are responsible for:
    - Discovering skills from configured locations
    - Loading skill metadata at startup
    - Providing full skills on demand
    - Managing skill lifecycle
    """

    def discover_skills(self) -> list[SkillMetadata]:
        """
        Discover all available skills and return their metadata.

        Scans configured skill directories for SKILL.md files and
        extracts metadata (name, description) from YAML frontmatter.

        Returns:
            List of skill metadata objects (lightweight, no instructions)

        Example:
            >>> registry = FileSkillRegistry(['/home/user/.taskforce/skills'])
            >>> skills = registry.discover_skills()
            >>> len(skills)
            3
            >>> skills[0].name
            'pdf-processing'
        """
        ...

    def get_skill(self, name: str) -> SkillProtocol | None:
        """
        Load a complete skill by name.

        Loads the full skill including instructions and resource access.
        This is called when a skill is triggered.

        Args:
            name: Skill identifier

        Returns:
            Full skill object, or None if not found

        Example:
            >>> skill = registry.get_skill('pdf-processing')
            >>> skill.instructions[:50]
            '# PDF Processing\\n\\nUse pdfplumber...'
        """
        ...

    def list_skills(self) -> list[str]:
        """
        List names of all discovered skills.

        Returns:
            List of skill names

        Example:
            >>> registry.list_skills()
            ['code-review', 'pdf-processing', 'data-analysis']
        """
        ...

    def get_skill_metadata(self, name: str) -> SkillMetadata | None:
        """
        Get metadata for a specific skill without loading instructions.

        Args:
            name: Skill identifier

        Returns:
            Skill metadata, or None if not found

        Example:
            >>> meta = registry.get_skill_metadata('pdf-processing')
            >>> meta.description
            'Extract text from PDFs...'
        """
        ...

    def refresh(self) -> None:
        """
        Re-scan skill directories and refresh the registry.

        Call this after adding or removing skills to update
        the registry's internal state.

        Example:
            >>> registry.refresh()  # Pick up new skills
        """
        ...

    def get_all_metadata(self) -> list[SkillMetadata]:
        """
        Get metadata for all discovered skills.

        Returns lightweight metadata objects suitable for
        including in system prompts.

        Returns:
            List of all skill metadata

        Example:
            >>> all_meta = registry.get_all_metadata()
            >>> for meta in all_meta:
            ...     print(f"{meta.name}: {meta.description[:50]}...")
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

        Adds the skill's instructions to the context and makes
        its resources available.

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
