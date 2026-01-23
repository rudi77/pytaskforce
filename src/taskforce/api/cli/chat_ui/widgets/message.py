"""Chat message widget for displaying user, agent, and system messages."""

from datetime import datetime
from enum import Enum
from typing import Optional

from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.text import Text
from textual.reactive import reactive
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

    copy_mode = reactive(False)

    DEFAULT_CSS = """
    ChatMessage {
        width: 100%;
        height: auto;
        margin: 1 0;
        padding: 0;
    }

    ChatMessage.user {
        align: left top;
    }

    ChatMessage.agent {
        align: left top;
    }

    ChatMessage.system {
        align: left top;
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
        # Check if copy mode is active
        if self.copy_mode:
            return self._render_plain_text()

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
            return self._render_simple_message("Message", time_str, Text(self.content))

    def _render_simple_message(
        self,
        label: str,
        time_str: str,
        content: RenderableType,
        label_style: str = "bold bright_white",
    ) -> RenderableType:
        """Render a formatted message block without panels."""
        header = Text()
        header.append(label, style=label_style)
        header.append(f"  {time_str}", style="dim")
        return Group(header, content)

    def _render_user_message(self, time_str: str) -> RenderableType:
        """Render user message."""
        content = Markdown(self.content) if self.content else Text("")
        return self._render_simple_message("🧑 You", time_str, content, "bold cyan")

    def _render_agent_message(self, time_str: str) -> RenderableType:
        """Render agent message with optional thought."""
        content_parts: list[RenderableType] = []

        if self.thought:
            thought_text = Text()
            thought_text.append("💭 Thought:\n", style="bold magenta")
            thought_text.append(self.thought, style="italic magenta")
            content_parts.append(thought_text)
            content_parts.append("\n\n")

        # Main content (render as markdown for rich formatting)
        if self.content:
            content_parts.append(Markdown(self.content))

        if not content_parts:
            final_content: RenderableType = Text("")
        elif len(content_parts) == 1:
            final_content = content_parts[0]
        else:
            final_content = Group(*content_parts)

        return self._render_simple_message("🤖 Agent", time_str, final_content, "bold bright_green")

    def _render_system_message(self, time_str: str) -> RenderableType:
        """Render system message."""
        content = Text(self.content, style="yellow")
        return self._render_simple_message("ℹ️ System", time_str, content, "bold yellow")

    def _render_tool_call(self, time_str: str) -> RenderableType:
        """Render tool call message."""
        content = Text()
        content.append(f"Tool: ", style="bold yellow")
        content.append(f"{self.tool_name}\n", style="yellow")

        if self.tool_params:
            content.append("Parameters: ", style="bold yellow")
            content.append(f"{self.tool_params}", style="dim yellow")

        return self._render_simple_message("🔧 Tool Call", time_str, content, "bold yellow")

    def _render_tool_result(self, time_str: str) -> RenderableType:
        """Render tool result message."""
        status_icon = "✅" if self.success else "❌"
        status_color = "green" if self.success else "red"

        content = Text()
        if self.tool_name:
            content.append(f"Tool: ", style="bold")
            content.append(f"{self.tool_name}\n", style=status_color)

        content.append(self.content, style=status_color)

        return self._render_simple_message(
            f"{status_icon} Tool Result",
            time_str,
            content,
            f"bold {status_color}",
        )

    def _render_error(self, time_str: str) -> RenderableType:
        """Render error message."""
        content = Text(self.content, style="bold red")
        return self._render_simple_message("❌ Error", time_str, content, "bold red")

    def _render_plan(self, time_str: str) -> RenderableType:
        """Render plan message."""
        content = Text(self.content, style="magenta")
        return self._render_simple_message("🧭 Plan Update", time_str, content, "bold magenta")

    def _render_debug(self, time_str: str) -> RenderableType:
        """Render debug message."""
        content = Text(self.content, style="dim white")
        return self._render_simple_message("🔍 Debug", time_str, content, "bold dim white")

    def to_plain_text(self) -> str:
        """Generate plain text representation of this message.

        Returns:
            Plain text string without Rich formatting.
        """
        time_str = self.timestamp.strftime("%H:%M:%S")

        if self.message_type == MessageType.USER:
            return f"[{time_str}] You: {self.content}"
        elif self.message_type == MessageType.AGENT:
            if self.thought:
                return f"[{time_str}] Agent (thought: {self.thought}): {self.content}"
            return f"[{time_str}] Agent: {self.content}"
        elif self.message_type == MessageType.SYSTEM:
            return f"[{time_str}] System: {self.content}"
        elif self.message_type == MessageType.TOOL_CALL:
            params_str = str(self.tool_params) if self.tool_params else ""
            return f"[{time_str}] Tool Call: {self.tool_name} {params_str}"
        elif self.message_type == MessageType.TOOL_RESULT:
            status = "SUCCESS" if self.success else "FAILED"
            return f"[{time_str}] Tool Result ({status}): {self.tool_name} - {self.content}"
        elif self.message_type == MessageType.ERROR:
            return f"[{time_str}] ERROR: {self.content}"
        elif self.message_type == MessageType.PLAN:
            return f"[{time_str}] Plan: {self.content}"
        elif self.message_type == MessageType.DEBUG:
            return f"[{time_str}] Debug: {self.content}"
        else:
            return f"[{time_str}] {self.content}"

    def _render_plain_text(self) -> RenderableType:
        """Render message as plain text without Rich formatting.

        Returns:
            Text object with minimal styling for copy mode.
        """
        return Text(self.to_plain_text())

    def watch_copy_mode(self, new_mode: bool) -> None:
        """React to copy mode changes.

        Args:
            new_mode: New copy mode state.
        """
        self.refresh()
