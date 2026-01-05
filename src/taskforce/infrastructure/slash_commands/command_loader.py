"""
File-Based Slash Command Loader

Loads custom slash commands from:
- Project: .taskforce/commands/*.md
- User:    ~/.taskforce/commands/*.md
"""

from pathlib import Path

import structlog

from taskforce.core.interfaces.slash_commands import (
    SlashCommandDefinition,
    SlashCommandLoaderProtocol,
)
from taskforce.infrastructure.slash_commands.command_parser import parse_command_markdown


class FileSlashCommandLoader:
    """
    Loads slash commands from filesystem.

    Searches in order (later overrides earlier):
    1. User global: ~/.taskforce/commands/
    2. Project: .taskforce/commands/

    Commands are Markdown files with optional YAML frontmatter.
    """

    def __init__(
        self,
        project_dir: str | Path | None = None,
        user_dir: str | Path | None = None,
    ):
        """
        Initialize the command loader.

        Args:
            project_dir: Project root directory (defaults to cwd)
            user_dir: User home directory (defaults to ~)
        """
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.user_dir = Path(user_dir) if user_dir else Path.home()
        self.logger = structlog.get_logger().bind(component="slash_command_loader")

        self._project_commands_dir = self.project_dir / ".taskforce" / "commands"
        self._user_commands_dir = self.user_dir / ".taskforce" / "commands"

    def get_search_paths(self) -> list[str]:
        """Return directories being searched for commands."""
        return [
            str(self._user_commands_dir),
            str(self._project_commands_dir),
        ]

    def list_commands(self) -> list[SlashCommandDefinition]:
        """
        List all available commands.

        Project commands override user commands with same name.
        """
        commands: dict[str, SlashCommandDefinition] = {}

        # Load user commands first (lower priority)
        if self._user_commands_dir.exists():
            for cmd in self._scan_directory(self._user_commands_dir, "user"):
                commands[cmd.name] = cmd

        # Load project commands (higher priority, overrides user)
        if self._project_commands_dir.exists():
            for cmd in self._scan_directory(self._project_commands_dir, "project"):
                if cmd.name in commands:
                    self.logger.debug(
                        "command.override",
                        command=cmd.name,
                        source="project",
                        overridden="user",
                    )
                commands[cmd.name] = cmd

        return list(commands.values())

    def load_command(self, name: str) -> SlashCommandDefinition | None:
        """Load a specific command by name."""
        # Check project first (higher priority)
        project_path = self._project_commands_dir / f"{name}.md"
        if project_path.exists():
            return self._load_from_file(project_path, "project")

        # Fall back to user
        user_path = self._user_commands_dir / f"{name}.md"
        if user_path.exists():
            return self._load_from_file(user_path, "user")

        return None

    def _scan_directory(
        self, directory: Path, source: str
    ) -> list[SlashCommandDefinition]:
        """Scan directory for command files."""
        commands = []
        for md_file in directory.glob("*.md"):
            cmd = self._load_from_file(md_file, source)
            if cmd:
                commands.append(cmd)
        return commands

    def _load_from_file(
        self, path: Path, source: str
    ) -> SlashCommandDefinition | None:
        """Load and parse a command file."""
        try:
            content = path.read_text(encoding="utf-8")
            return parse_command_markdown(
                content=content,
                name=path.stem,
                source=source,
                source_path=str(path),
            )
        except Exception as e:
            self.logger.warning(
                "command.load_failed",
                path=str(path),
                error=str(e),
            )
            return None
