"""Chat log widget for displaying message history."""

from datetime import datetime
from typing import Optional

from textual.containers import VerticalScroll
from textual.widgets import Static

from taskforce.api.cli.chat_ui.widgets.message import ChatMessage, MessageType


class ChatLog(VerticalScroll):
    """Scrollable container for chat messages."""

    DEFAULT_CSS = """
    ChatLog {
        width: 100%;
        height: 1fr;
        padding: 1;
        background: $surface;
        border: solid $primary;
    }

    ChatLog > Static {
        width: 100%;
        height: auto;
    }
    """

    def __init__(self, **kwargs):
        """Initialize chat log."""
        super().__init__(**kwargs)
        self.auto_scroll = True
        self.message_count = 0

    def add_user_message(self, content: str, timestamp: Optional[datetime] = None):
        """Add a user message to the chat log.

        Args:
            content: Message content
            timestamp: Message timestamp
        """
        message = ChatMessage(
            message_type=MessageType.USER,
            content=content,
            timestamp=timestamp,
        )
        self.mount(message)
        self.message_count += 1
        if self.auto_scroll:
            self.scroll_end(animate=False)

    def add_agent_message(
        self,
        content: str,
        timestamp: Optional[datetime] = None,
        thought: Optional[str] = None,
    ):
        """Add an agent message to the chat log.

        Args:
            content: Message content
            timestamp: Message timestamp
            thought: Optional agent thought for debug mode
        """
        message = ChatMessage(
            message_type=MessageType.AGENT,
            content=content,
            timestamp=timestamp,
            thought=thought,
        )
        self.mount(message)
        self.message_count += 1
        if self.auto_scroll:
            self.scroll_end(animate=False)

    def add_system_message(self, content: str, timestamp: Optional[datetime] = None):
        """Add a system message to the chat log.

        Args:
            content: Message content
            timestamp: Message timestamp
        """
        message = ChatMessage(
            message_type=MessageType.SYSTEM,
            content=content,
            timestamp=timestamp,
        )
        self.mount(message)
        self.message_count += 1
        if self.auto_scroll:
            self.scroll_end(animate=False)

    def add_tool_call(
        self,
        tool_name: str,
        tool_params: Optional[dict] = None,
        timestamp: Optional[datetime] = None,
    ):
        """Add a tool call message to the chat log.

        Args:
            tool_name: Name of the tool being called
            tool_params: Tool parameters
            timestamp: Message timestamp
        """
        message = ChatMessage(
            message_type=MessageType.TOOL_CALL,
            content="",
            tool_name=tool_name,
            tool_params=tool_params,
            timestamp=timestamp,
        )
        self.mount(message)
        self.message_count += 1
        if self.auto_scroll:
            self.scroll_end(animate=False)

    def add_tool_result(
        self,
        tool_name: str,
        result: str,
        success: bool = True,
        timestamp: Optional[datetime] = None,
    ):
        """Add a tool result message to the chat log.

        Args:
            tool_name: Name of the tool
            result: Result content
            success: Whether the tool call was successful
            timestamp: Message timestamp
        """
        message = ChatMessage(
            message_type=MessageType.TOOL_RESULT,
            content=result,
            tool_name=tool_name,
            success=success,
            timestamp=timestamp,
        )
        self.mount(message)
        self.message_count += 1
        if self.auto_scroll:
            self.scroll_end(animate=False)

    def add_error(self, content: str, timestamp: Optional[datetime] = None):
        """Add an error message to the chat log.

        Args:
            content: Error message
            timestamp: Message timestamp
        """
        message = ChatMessage(
            message_type=MessageType.ERROR,
            content=content,
            timestamp=timestamp,
        )
        self.mount(message)
        self.message_count += 1
        if self.auto_scroll:
            self.scroll_end(animate=False)

    def add_plan_update(self, content: str, timestamp: Optional[datetime] = None):
        """Add a plan update message to the chat log.

        Args:
            content: Plan update content
            timestamp: Message timestamp
        """
        message = ChatMessage(
            message_type=MessageType.PLAN,
            content=content,
            timestamp=timestamp,
        )
        self.mount(message)
        self.message_count += 1
        if self.auto_scroll:
            self.scroll_end(animate=False)

    def add_debug_message(self, content: str, timestamp: Optional[datetime] = None):
        """Add a debug message to the chat log.

        Args:
            content: Debug message
            timestamp: Message timestamp
        """
        message = ChatMessage(
            message_type=MessageType.DEBUG,
            content=content,
            timestamp=timestamp,
        )
        self.mount(message)
        self.message_count += 1
        if self.auto_scroll:
            self.scroll_end(animate=False)

    def clear_messages(self):
        """Clear all messages from the chat log."""
        # Remove all child widgets
        for child in list(self.children):
            child.remove()
        self.message_count = 0

    def toggle_auto_scroll(self) -> bool:
        """Toggle auto-scroll on/off.

        Returns:
            New auto-scroll state
        """
        self.auto_scroll = not self.auto_scroll
        return self.auto_scroll
