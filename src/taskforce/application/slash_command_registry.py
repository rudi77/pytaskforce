"""
Slash Command Registry

Central registry for resolving and executing slash commands.
Integrates with AgentFactory for agent-type commands.
"""


import structlog

from taskforce.application.factory import AgentFactory
from taskforce.core.domain.agent import Agent
from taskforce.core.interfaces.slash_commands import (
    CommandType,
    SlashCommandDefinition,
    SlashCommandLoaderProtocol,
)
from taskforce.infrastructure.slash_commands.command_loader import FileSlashCommandLoader
from taskforce.infrastructure.slash_commands.command_parser import substitute_arguments


class SlashCommandRegistry:
    """
    Registry for custom slash commands.

    Responsibilities:
    - Load commands from filesystem
    - Resolve command by name with precedence
    - Prepare prompt or agent for execution
    """

    # Built-in commands that cannot be overridden
    BUILTIN_COMMANDS = frozenset({
        "help",
        "h",
        "clear",
        "c",
        "export",
        "e",
        "exit",
        "quit",
        "q",
        "debug",
        "tokens",
    })

    def __init__(
        self,
        loader: SlashCommandLoaderProtocol | None = None,
        factory: AgentFactory | None = None,
    ):
        """
        Initialize command registry.

        Args:
            loader: Command loader (defaults to FileSlashCommandLoader)
            factory: Agent factory for agent-type commands
        """
        self.loader = loader or FileSlashCommandLoader()
        self.factory = factory or AgentFactory()
        self.logger = structlog.get_logger().bind(component="slash_command_registry")

    def is_builtin(self, command_name: str) -> bool:
        """Check if command is a built-in that cannot be overridden."""
        return command_name.lower() in self.BUILTIN_COMMANDS

    def is_custom_command(self, command_name: str) -> bool:
        """Check if a custom command exists with this name."""
        if self.is_builtin(command_name):
            return False
        return self.loader.load_command(command_name) is not None

    def list_commands(self, include_builtin: bool = True) -> list[dict[str, str]]:
        """
        List all available commands.

        Returns:
            List of dicts with name, description, source, type
        """
        commands = []

        # Add built-in commands
        if include_builtin:
            commands.extend(
                [
                    {
                        "name": "help",
                        "description": "Show help message",
                        "source": "builtin",
                        "type": "builtin",
                    },
                    {
                        "name": "clear",
                        "description": "Clear chat history",
                        "source": "builtin",
                        "type": "builtin",
                    },
                    {
                        "name": "debug",
                        "description": "Toggle debug mode",
                        "source": "builtin",
                        "type": "builtin",
                    },
                    {
                        "name": "tokens",
                        "description": "Show token usage",
                        "source": "builtin",
                        "type": "builtin",
                    },
                    {
                        "name": "exit",
                        "description": "Exit application",
                        "source": "builtin",
                        "type": "builtin",
                    },
                ]
            )

        # Add custom commands
        for cmd in self.loader.list_commands():
            commands.append(
                {
                    "name": cmd.name,
                    "description": cmd.description,
                    "source": cmd.source,
                    "type": cmd.command_type.value,
                }
            )

        return commands

    def resolve_command(
        self, command_input: str
    ) -> tuple[SlashCommandDefinition | None, str]:
        """
        Resolve a command string to definition and arguments.

        Args:
            command_input: Full command string (e.g., "/review path/to/file.py")

        Returns:
            Tuple of (command_definition, arguments_string)
            Returns (None, "") if command not found or is builtin
        """
        # Parse command and arguments
        parts = command_input.lstrip("/").split(maxsplit=1)
        command_name = parts[0].lower()
        arguments = parts[1] if len(parts) > 1 else ""

        # Check for builtin (not handled here)
        if self.is_builtin(command_name):
            return None, ""

        # Load custom command
        command_def = self.loader.load_command(command_name)
        if not command_def:
            return None, ""

        return command_def, arguments

    def prepare_prompt(
        self, command_def: SlashCommandDefinition, arguments: str
    ) -> str:
        """
        Prepare final prompt from command definition.

        Substitutes $ARGUMENTS in template.

        Args:
            command_def: Parsed command definition
            arguments: Arguments to substitute

        Returns:
            Final prompt string
        """
        return substitute_arguments(command_def.prompt_template, arguments)

    async def create_agent_for_command(
        self, command_def: SlashCommandDefinition, base_profile: str = "dev"
    ) -> Agent:
        """
        Create an Agent configured for an agent-type command.

        Args:
            command_def: Agent command definition
            base_profile: Base profile for infrastructure settings

        Returns:
            Configured Agent instance

        Raises:
            ValueError: If command is not agent type
        """
        if command_def.command_type != CommandType.AGENT:
            raise ValueError(f"Command '{command_def.name}' is not an agent type")

        agent_config = command_def.agent_config or {}
        metadata = command_def.metadata or {}

        # Check if plugin path is specified in metadata
        plugin_path = metadata.get("plugin")

        # Use command's profile if specified, otherwise base_profile
        profile = agent_config.get("profile", base_profile)

        # If plugin is specified, use create_agent_with_plugin
        if plugin_path:
            tool_allowlist = agent_config.get("tools", [])
            self.logger.info(
                "creating_agent_with_plugin_from_command",
                command=command_def.name,
                plugin_path=plugin_path,
                profile=profile,
                tools=tool_allowlist,
            )

            # Create agent with plugin - plugin config will be merged with base profile
            agent = await self.factory.create_agent_with_plugin(
                plugin_path=plugin_path,
                profile=profile,
            )

            # Filter tools by allowlist if specified in command
            if tool_allowlist:
                original_tool_count = len(agent.tools)
                filtered_tools = {
                    name: tool
                    for name, tool in agent.tools.items()
                    if name in tool_allowlist
                }
                # Rebuild tools dict and OpenAI format
                agent.tools = filtered_tools
                from taskforce.core.tools.tool_converter import tools_to_openai_format

                agent._openai_tools = tools_to_openai_format(agent.tools)
                self.logger.debug(
                    "tools_filtered_for_command",
                    command=command_def.name,
                    original_count=original_tool_count,
                    filtered_count=len(filtered_tools),
                    allowed_tools=tool_allowlist,
                )

            # Override system prompt from command (command prompt takes precedence over plugin config)
            if command_def.prompt_template:
                agent._base_system_prompt = command_def.prompt_template
                # Also update the prompt builder to use the new prompt
                agent.prompt_builder._base_system_prompt = command_def.prompt_template

            return agent

        # Standard agent creation without plugin
        agent_definition = {
            "system_prompt": command_def.prompt_template,
            "tool_allowlist": agent_config.get("tools", []),
            "mcp_servers": agent_config.get("mcp_servers", []),
            "mcp_tool_allowlist": [],
        }

        self.logger.info(
            "creating_agent_from_command",
            command=command_def.name,
            profile=profile,
            tools=agent_config.get("tools", []),
        )

        return await self.factory.create_agent_from_definition(
            agent_definition=agent_definition,
            profile=profile,
        )
