"""Rich output formatting for Taskforce CLI.

Provides beautiful, eye-catching console output with clear visual separation
between agent and user messages.
"""

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

# Custom theme for Taskforce CLI
TASKFORCE_THEME = Theme(
    {
        "agent": "bold cyan",
        "user": "bold green",
        "system": "bold blue",
        "error": "bold red",
        "warning": "bold yellow",
        "success": "bold green",
        "debug": "dim white",
        "info": "white",
        "thought": "italic magenta",
        "action": "bold yellow",
        "observation": "cyan",
    }
)


class TaskforceConsole:
    """Enhanced console with Taskforce branding and formatting."""

    def __init__(self, debug: bool = False):
        """Initialize console with optional debug mode.

        Args:
            debug: Enable debug logging output
        """
        self.console = Console(theme=TASKFORCE_THEME)
        self.debug_mode = debug

    def print_banner(self):
        """Print Taskforce startup banner."""
        banner = Text()
        banner.append("=" * 60 + "\n", style="bold blue")
        banner.append("                                                            \n", style="bold blue")
        banner.append("        ", style="bold blue")
        banner.append("TASKFORCE", style="bold cyan")
        banner.append(" - ReAct Agent Framework        \n", style="bold blue")
        banner.append("                                                            \n", style="bold blue")
        banner.append("=" * 60, style="bold blue")
        self.console.print(banner)
        self.console.print()

    def print_agent_message(self, message: str, thought: Optional[str] = None):
        """Print agent message with distinctive styling.

        Args:
            message: Agent's response message
            thought: Optional agent's reasoning/thought process
        """
        # Show thought process if in debug mode
        if thought and self.debug_mode:
            thought_panel = Panel(
                thought,
                title="[Agent Thought]",
                title_align="left",
                border_style="magenta",
                padding=(0, 1),
            )
            self.console.print(thought_panel)

        # Main agent message
        agent_panel = Panel(
            message,
            title="[Agent]",
            title_align="left",
            border_style="cyan",
            padding=(0, 1),
        )
        self.console.print(agent_panel)
        self.console.print()

    def print_user_message(self, message: str):
        """Print user message with distinctive styling.

        Args:
            message: User's input message
        """
        user_panel = Panel(
            message,
            title="[You]",
            title_align="left",
            border_style="green",
            padding=(0, 1),
        )
        self.console.print(user_panel)
        self.console.print()

    def print_system_message(self, message: str, style: str = "system"):
        """Print system message.

        Args:
            message: System message
            style: Rich style to apply (from theme)
        """
        self.console.print(f"[{style}][i] {message}[/{style}]")

    def print_error(self, message: str, exception: Optional[Exception] = None):
        """Print error message with optional exception details.

        Args:
            message: Error message
            exception: Optional exception for debug mode
        """
        error_panel = Panel(
            f"[X] {message}",
            title="[Error]",
            title_align="left",
            border_style="red",
            padding=(0, 1),
        )
        self.console.print(error_panel)

        if exception and self.debug_mode:
            import traceback

            self.console.print("[debug]" + traceback.format_exc() + "[/debug]")

    def print_success(self, message: str):
        """Print success message.

        Args:
            message: Success message
        """
        success_panel = Panel(
            f"[OK] {message}",
            title="[Success]",
            title_align="left",
            border_style="green",
            padding=(0, 1),
        )
        self.console.print(success_panel)

    def print_warning(self, message: str):
        """Print warning message.

        Args:
            message: Warning message
        """
        self.console.print(f"[warning][!] {message}[/warning]")

    def print_debug(self, message: str):
        """Print debug message (only if debug mode enabled).

        Args:
            message: Debug message
        """
        if self.debug_mode:
            self.console.print(f"[debug][DEBUG] {message}[/debug]")

    def print_action(self, action_type: str, details: str):
        """Print agent action with details.

        Args:
            action_type: Type of action (tool_call, ask_user, etc.)
            details: Action details
        """
        if self.debug_mode:
            action_text = f"[action][Action][/action] {action_type}\n[info]{details}[/info]"
            action_panel = Panel(
                action_text,
                title="[Agent Action]",
                title_align="left",
                border_style="yellow",
                padding=(0, 1),
            )
            self.console.print(action_panel)

    def print_observation(self, observation: str):
        """Print observation result.

        Args:
            observation: Observation text
        """
        if self.debug_mode:
            obs_panel = Panel(
                observation,
                title="[Observation]",
                title_align="left",
                border_style="cyan",
                padding=(0, 1),
            )
            self.console.print(obs_panel)

    def print_session_info(
        self,
        session_id: str,
        profile: str,
        user_context: Optional[dict] = None,
    ):
        """Print session information.

        Args:
            session_id: Session ID
            profile: Configuration profile
            user_context: Optional RAG user context
        """
        info_lines = [
            f"[info]Session ID:[/info] [debug]{session_id}[/debug]",
            f"[info]Profile:[/info] [debug]{profile}[/debug]",
        ]

        if user_context:
            info_lines.append("[info]RAG Context:[/info]")
            for key, value in user_context.items():
                info_lines.append(f"  [debug]{key}:[/debug] {value}")

        info_text = "\n".join(info_lines)
        info_panel = Panel(
            info_text,
            title="[Session Info]",
            title_align="left",
            border_style="blue",
            padding=(0, 1),
        )
        self.console.print(info_panel)
        self.console.print()

    def print_divider(self, text: Optional[str] = None):
        """Print a visual divider.

        Args:
            text: Optional text to display in divider
        """
        if text:
            self.console.print(f"\n[bold blue]{'=' * 20} {text} {'=' * 20}[/bold blue]\n")
        else:
            self.console.print(f"[dim]{'-' * 60}[/dim]")

    def prompt(self, message: str = "You") -> str:
        """Prompt user for input with styled prompt.

        Args:
            message: Prompt message

        Returns:
            User input string
        """
        from rich.prompt import Prompt

        return Prompt.ask(f"[user]> {message}[/user]")

