"""Chat message widget for displaying user, agent, and system messages."""

from datetime import datetime
from enum import Enum
from typing import Optional

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static


class MessageType(Enum):
    """Types of chat messages."""

    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PLAN = "plan"
    ERROR = "error"
    DEBUG = "debug"


class ChatMessage(Static):
    """A single chat message with styling based on type."""

    DEFAULT_CSS = """
    ChatMessage {
        width: 100%;
        height: auto;
        margin: 0 1;
        padding: 0;
    }

    ChatMessage.user {
        align: right top;
    }

    ChatMessage.agent {
        align: left top;
    }

    ChatMessage.system {
        align: center top;
    }

    ChatMessage.tool_call {
        align: left top;
    }

    ChatMessage.tool_result {
        align: left top;
    }

    ChatMessage.error {
        align: left top;
    }
    """

    def __init__(
        self,
        message_type: MessageType,
        content: str,
        timestamp: Optional[datetime] = None,
        thought: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_params: Optional[dict] = None,
        success: Optional[bool] = None,
        **kwargs,
    ):
        """Initialize chat message.

        Args:
            message_type: Type of message (user, agent, system, etc.)
            content: Message content
            timestamp: Message timestamp
            thought: Optional agent thought (debug mode)
            tool_name: Optional tool name for tool_call/tool_result
            tool_params: Optional tool parameters
            success: Optional success status for tool_result
        """
        super().__init__(**kwargs)
        self.message_type = message_type
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.thought = thought
        self.tool_name = tool_name
        self.tool_params = tool_params
        self.success = success

        # Add CSS class for styling
        self.add_class(message_type.value)

    def render(self) -> RenderableType:
        """Render the message based on its type."""
        # Format timestamp
        time_str = self.timestamp.strftime("%H:%M:%S")

        if self.message_type == MessageType.USER:
            return self._render_user_message(time_str)
        elif self.message_type == MessageType.AGENT:
            return self._render_agent_message(time_str)
        elif self.message_type == MessageType.SYSTEM:
            return self._render_system_message(time_str)
        elif self.message_type == MessageType.TOOL_CALL:
            return self._render_tool_call(time_str)
        elif self.message_type == MessageType.TOOL_RESULT:
            return self._render_tool_result(time_str)
        elif self.message_type == MessageType.ERROR:
            return self._render_error(time_str)
        elif self.message_type == MessageType.PLAN:
            return self._render_plan(time_str)
        elif self.message_type == MessageType.DEBUG:
            return self._render_debug(time_str)
        else:
            return Panel(self.content, border_style="white")

    def _render_user_message(self, time_str: str) -> Panel:
        """Render user message."""
        title = f"🧑 You                                        {time_str}"
        return Panel(
            self.content,
            title=title,
            title_align="left",
            border_style="green",
            padding=(0, 1),
        )

    def _render_agent_message(self, time_str: str) -> Panel:
        """Render agent message with optional thought."""
        title = f"🤖 Agent                                      {time_str}"

        # Build content with optional thought
        content_parts = []

        if self.thought:
            thought_text = Text()
            thought_text.append("💭 Thought:\n", style="bold magenta")
            thought_text.append(self.thought, style="italic magenta")
            content_parts.append(thought_text)
            content_parts.append("\n\n")

        # Main content (render as markdown for rich formatting)
        if self.content:
            content_parts.append(Markdown(self.content))

        # Combine all parts
        if len(content_parts) == 0:
            final_content = ""
        elif len(content_parts) == 1:
            final_content = content_parts[0]
        else:
            from rich.console import Group
            final_content = Group(*content_parts)

        return Panel(
            final_content,
            title=title,
            title_align="left",
            border_style="cyan",
            padding=(0, 1),
        )

    def _render_system_message(self, time_str: str) -> Panel:
        """Render system message."""
        title = f"ℹ️  System                                     {time_str}"
        return Panel(
            Text(self.content, style="blue"),
            title=title,
            title_align="left",
            border_style="blue",
            padding=(0, 1),
        )

    def _render_tool_call(self, time_str: str) -> Panel:
        """Render tool call message."""
        title = f"🔧 Tool Call                                  {time_str}"

        content = Text()
        content.append(f"Tool: ", style="bold yellow")
        content.append(f"{self.tool_name}\n", style="yellow")

        if self.tool_params:
            content.append("Parameters: ", style="bold yellow")
            content.append(f"{self.tool_params}", style="dim yellow")

        return Panel(
            content,
            title=title,
            title_align="left",
            border_style="yellow",
            padding=(0, 1),
        )

    def _render_tool_result(self, time_str: str) -> Panel:
        """Render tool result message."""
        status_icon = "✅" if self.success else "❌"
        status_color = "green" if self.success else "red"
        title = f"{status_icon} Tool Result                              {time_str}"

        content = Text()
        if self.tool_name:
            content.append(f"Tool: ", style="bold")
            content.append(f"{self.tool_name}\n", style=status_color)

        content.append(self.content, style=status_color)

        return Panel(
            content,
            title=title,
            title_align="left",
            border_style=status_color,
            padding=(0, 1),
        )

    def _render_error(self, time_str: str) -> Panel:
        """Render error message."""
        title = f"❌ Error                                      {time_str}"
        return Panel(
            Text(self.content, style="bold red"),
            title=title,
            title_align="left",
            border_style="red",
            padding=(0, 1),
        )

    def _render_plan(self, time_str: str) -> Panel:
        """Render plan message."""
        title = f"🧭 Plan Update                                {time_str}"
        return Panel(
            Text(self.content, style="magenta"),
            title=title,
            title_align="left",
            border_style="magenta",
            padding=(0, 1),
        )

    def _render_debug(self, time_str: str) -> Panel:
        """Render debug message."""
        title = f"🔍 Debug                                      {time_str}"
        return Panel(
            Text(self.content, style="dim white"),
            title=title,
            title_align="left",
            border_style="dim white",
            padding=(0, 1),
        )
