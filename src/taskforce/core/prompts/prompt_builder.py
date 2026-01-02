"""
Dynamic System Prompt Builder

This module provides functions to dynamically assemble system prompts
with tool descriptions injected at runtime. This ensures the LLM always
sees the actual available tools and their parameters, making tool calls
more reliable.

The design follows the pattern from Agent V2 where tool descriptions
are dynamically added to the system prompt rather than being hardcoded
in specialist profiles.
"""

from typing import Optional


def build_system_prompt(
    base_prompt: str,
    mission: Optional[str] = None,
    tools_description: Optional[str] = None,
) -> str:
    """
    Build the system prompt from base, mission, and tools description.

    This function dynamically assembles a system prompt with XML-tagged sections.
    The tools description is injected at runtime, ensuring the LLM always has
    accurate information about available tools and their parameters.

    Args:
        base_prompt: The static base instructions (timeless context, specialist profile).
        mission: Optional mission or current objective. Can be None for 
            mission-agnostic prompts (recommended for multi-turn conversations).
        tools_description: Formatted description of available tools with names,
            descriptions, and parameter schemas.

    Returns:
        Assembled system prompt with XML-tagged sections:
        - <Base>: Core instructions and specialist profile
        - <Mission>: Current objective (if provided)
        - <ToolsDescription>: Available tools and parameters (if provided)

    Example:
        >>> from taskforce.core.prompts import GENERAL_AUTONOMOUS_KERNEL_PROMPT
        >>> from taskforce.core.prompts import CODING_SPECIALIST_PROMPT
        >>> 
        >>> base = GENERAL_AUTONOMOUS_KERNEL_PROMPT + "\\n\\n" + CODING_SPECIALIST_PROMPT
        >>> tools_desc = "Tool: file_read\\nDescription: Read file contents..."
        >>> 
        >>> prompt = build_system_prompt(base, tools_description=tools_desc)
    """
    # Start with base prompt
    prompt_parts = [f"<Base>\n{base_prompt.strip()}\n</Base>"]

    # Only add mission section if mission is provided (backward compatibility)
    if mission:
        prompt_parts.append(f"<Mission>\n{mission.strip()}\n</Mission>")

    # Add tools description - critical for reliable tool calls
    if tools_description:
        prompt_parts.append(f"<ToolsDescription>\n{tools_description.strip()}\n</ToolsDescription>")

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

