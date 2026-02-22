"""
Dynamic System Prompt Builder

This module provides functions to dynamically assemble system prompts
with tool descriptions and skill metadata injected at runtime. This ensures
the LLM always sees the actual available tools and their parameters, making
tool calls more reliable.

The design follows the pattern from Agent V2 where tool descriptions
are dynamically added to the system prompt rather than being hardcoded
in specialist profiles.

Skills are modular capabilities that provide domain-specific expertise.
Skill metadata is included in the prompt to enable skill discovery and
activation based on user requests.
"""



def build_system_prompt(
    base_prompt: str,
    mission: str | None = None,
    tools_description: str | None = None,
    skills_metadata: str | None = None,
    active_skills: str | None = None,
) -> str:
    """
    Build the system prompt from base, mission, tools, and skills.

    This function dynamically assembles a system prompt with XML-tagged sections.
    The tools description and skills metadata are injected at runtime, ensuring
    the LLM always has accurate information about available capabilities.

    Args:
        base_prompt: The static base instructions (timeless context, specialist profile).
        mission: Optional mission or current objective. Can be None for
            mission-agnostic prompts (recommended for multi-turn conversations).
        tools_description: Formatted description of available tools with names,
            descriptions, and parameter schemas.
        skills_metadata: Optional formatted list of available skills with names
            and descriptions. Used for skill discovery.
        active_skills: Optional combined instructions from currently active skills.
            Loaded when skills are triggered based on user request relevance.

    Returns:
        Assembled system prompt with XML-tagged sections:
        - <Base>: Core instructions and specialist profile
        - <Mission>: Current objective (if provided)
        - <ToolsDescription>: Available tools and parameters (if provided)
        - <AvailableSkills>: Skill metadata for discovery (if provided)
        - <ActiveSkills>: Active skill instructions (if provided)

    Example:
        >>> from taskforce.core.prompts import GENERAL_AUTONOMOUS_KERNEL_PROMPT
        >>> from taskforce.core.prompts import CODING_SPECIALIST_PROMPT
        >>>
        >>> base = GENERAL_AUTONOMOUS_KERNEL_PROMPT + "\\n\\n" + CODING_SPECIALIST_PROMPT
        >>> tools_desc = "Tool: file_read\\nDescription: Read file contents..."
        >>> skills_meta = "- code-review: Analyze code for issues..."
        >>>
        >>> prompt = build_system_prompt(
        ...     base,
        ...     tools_description=tools_desc,
        ...     skills_metadata=skills_meta
        ... )
    """
    # Start with base prompt
    prompt_parts = [f"<Base>\n{base_prompt.strip()}\n</Base>"]

    # Only add mission section if mission is provided (backward compatibility)
    if mission:
        prompt_parts.append(f"<Mission>\n{mission.strip()}\n</Mission>")

    # Add tools description - critical for reliable tool calls
    if tools_description:
        prompt_parts.append(f"<ToolsDescription>\n{tools_description.strip()}\n</ToolsDescription>")

    # Add available skills metadata for discovery
    if skills_metadata:
        prompt_parts.append(f"<AvailableSkills>\n{skills_metadata.strip()}\n</AvailableSkills>")

    # Add active skill instructions
    if active_skills:
        prompt_parts.append(f"<ActiveSkills>\n{active_skills.strip()}\n</ActiveSkills>")

    return "\n\n".join(prompt_parts)


def format_tools_description(tools: list) -> str:
    """
    Format a list of tools into a structured description string.

    Each tool is formatted with its name, description, and parameter schema.
    This format helps the LLM understand available tools and their usage.

    Args:
        tools: List of tool objects with 'name', 'description', and
            'parameters_schema' attributes.

    Returns:
        Formatted string with all tools described in a consistent format.

    Example:
        >>> from taskforce.infrastructure.tools.native.file_tools import FileReadTool
        >>> tools = [FileReadTool()]
        >>> desc = format_tools_description(tools)
        >>> print(desc)
        Tool: file_read
        Description: Read the contents of a file...
        Parameters: {...}
    """
    import json

    descriptions = []
    for tool in tools:
        params = json.dumps(tool.parameters_schema, indent=2)
        descriptions.append(
            f"Tool: {tool.name}\n"
            f"Description: {tool.description}\n"
            f"Parameters: {params}"
        )
    return "\n\n".join(descriptions)


def format_skills_metadata(skills_metadata: list) -> str:
    """
    Format skill metadata for system prompt inclusion.

    Creates a lightweight description of available skills that helps
    the agent understand when to activate each skill based on user requests.

    Args:
        skills_metadata: List of skill metadata objects with 'name' and
            'description' attributes.

    Returns:
        Formatted string listing all skills with their trigger descriptions.

    Example:
        >>> from taskforce.core.domain.skill import SkillMetadataModel
        >>> metadata = [
        ...     SkillMetadataModel(
        ...         name="code-review",
        ...         description="Review code for bugs and improvements",
        ...         source_path="/path/to/skill"
        ...     )
        ... ]
        >>> desc = format_skills_metadata(metadata)
        >>> print(desc)
        Available Skills:
        - code-review: Review code for bugs and improvements
    """
    if not skills_metadata:
        return ""

    lines = ["The following skills are available. Activate relevant skills when the user's request matches their description:"]
    for meta in skills_metadata:
        lines.append(f"- {meta.name}: {meta.description}")

    return "\n".join(lines)


def format_active_skills_instructions(skills: list) -> str:
    """
    Format instructions from active skills.

    Combines instructions from all currently active skills into a
    single formatted string for inclusion in the system prompt.

    Args:
        skills: List of Skill objects with 'name' and 'instructions' attributes.

    Returns:
        Combined instructions from all active skills, separated by headers.

    Example:
        >>> # With active skills
        >>> active_instructions = format_active_skills_instructions(active_skills)
        >>> print(active_instructions)
        ## Skill: code-review
        <instructions>
        ---
        ## Skill: data-analysis
        <instructions>
    """
    if not skills:
        return ""

    parts = []
    for skill in skills:
        parts.append(f"## Skill: {skill.name}\n\n{skill.instructions}")

    return "\n\n---\n\n".join(parts)

