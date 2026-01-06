"""
Application Layer - Command Loader Service

Provides application-level access to slash command loading.
API layer should import from here instead of directly from infrastructure.
"""

from pathlib import Path
from typing import Optional

from taskforce.core.interfaces.slash_commands import SlashCommandDefinition
from taskforce.infrastructure.slash_commands.command_loader import FileSlashCommandLoader


class CommandLoaderService:
    """Application service for loading slash commands."""

    def __init__(
        self,
        project_dir: Optional[str | Path] = None,
        user_dir: Optional[str | Path] = None,
    ):
        """
        Initialize the command loader service.

        Args:
            project_dir: Project root directory (defaults to cwd)
            user_dir: User home directory (defaults to ~)
        """
        self._loader = FileSlashCommandLoader(
            project_dir=project_dir,
            user_dir=user_dir,
        )

    def get_search_paths(self) -> list[str]:
        """Return directories being searched for commands."""
        return self._loader.get_search_paths()

    def list_commands(self) -> list[SlashCommandDefinition]:
        """List all available commands."""
        return self._loader.list_commands()

    def load_command(self, name: str) -> Optional[SlashCommandDefinition]:
        """Load a specific command by name."""
        return self._loader.load_command(name)


def get_command_loader_service(
    project_dir: Optional[str | Path] = None,
    user_dir: Optional[str | Path] = None,
) -> CommandLoaderService:
    """Get a command loader service instance."""
    return CommandLoaderService(project_dir=project_dir, user_dir=user_dir)
