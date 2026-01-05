"""
Markdown Command Parser

Parses Claude Code compatible command files:
- Optional YAML frontmatter (---...---)
- Prompt template with $ARGUMENTS variable
"""

import re
from typing import Any

import yaml

from taskforce.core.interfaces.slash_commands import (
    CommandType,
    SlashCommandDefinition,
)


def parse_command_markdown(
    content: str,
    name: str,
    source: str,
    source_path: str,
) -> SlashCommandDefinition:
    """
    Parse a Markdown command file into SlashCommandDefinition.

    Format:
        ---
        description: Short description
        type: prompt|agent
        profile: dev  # for agent type
        tools: [file_read, python]  # for agent type
        ---

        The prompt template with $ARGUMENTS

    Args:
        content: Markdown file content
        name: Command name (from filename)
        source: "project" or "user"
        source_path: Absolute path to file

    Returns:
        SlashCommandDefinition instance
    """
    frontmatter, body = _extract_frontmatter(content)

    # Determine command type
    command_type_str = frontmatter.get("type", "prompt")
    try:
        command_type = CommandType(command_type_str)
    except ValueError:
        command_type = CommandType.PROMPT

    # Extract description
    description = frontmatter.get("description", "")
    if not description and body:
        # Use first line of body as description if not in frontmatter
        first_line = body.strip().split("\n")[0]
        if first_line.startswith("#"):
            description = first_line.lstrip("#").strip()

    # Build agent config if type is agent
    agent_config = None
    if command_type == CommandType.AGENT:
        agent_config = {
            "profile": frontmatter.get("profile", "dev"),
            "tools": frontmatter.get("tools", []),
            "mcp_servers": frontmatter.get("mcp_servers", []),
            "specialist": frontmatter.get("specialist"),
        }

    # Collect remaining metadata
    known_keys = {"description", "type", "profile", "tools", "mcp_servers", "specialist"}
    metadata = {k: v for k, v in frontmatter.items() if k not in known_keys}

    return SlashCommandDefinition(
        name=name,
        source=source,
        source_path=source_path,
        command_type=command_type,
        description=description,
        prompt_template=body.strip(),
        agent_config=agent_config,
        metadata=metadata if metadata else None,
    )


def _extract_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Extract YAML frontmatter from Markdown content.

    Returns:
        Tuple of (frontmatter_dict, body_content)
    """
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if match:
        frontmatter_yaml = match.group(1)
        body = match.group(2)
        try:
            frontmatter = yaml.safe_load(frontmatter_yaml) or {}
        except yaml.YAMLError:
            frontmatter = {}
        return frontmatter, body

    return {}, content


def substitute_arguments(template: str, arguments: str) -> str:
    """
    Substitute $ARGUMENTS in template with provided arguments.

    Args:
        template: Prompt template with $ARGUMENTS placeholder
        arguments: The arguments string to substitute

    Returns:
        Prompt with $ARGUMENTS replaced
    """
    return template.replace("$ARGUMENTS", arguments)
