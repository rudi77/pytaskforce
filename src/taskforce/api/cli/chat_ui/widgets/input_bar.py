"""Input bar widget for user message input."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.events import Key
from textual.widgets import Static, TextArea


class InputBar(Static):
    """Fixed input bar at the bottom of the screen."""

    DEFAULT_CSS = """
    InputBar {
        height: auto;
        width: 100%;
        background: $surface;
        border-top: solid $primary;
        padding: 1;
    }

    InputBar Vertical {
        width: 100%;
        height: auto;
    }

    InputBar TextArea {
        width: 1fr;
        min-height: 4;
        max-height: 8;
    }

    InputBar .hint-text {
        color: $text-muted;
        text-style: italic;
        margin-top: 1;
    }
    """

    class MessageSubmitted(Message):
        """Message sent when user submits input."""

        def __init__(self, content: str):
            """Initialize message.

            Args:
                content: The submitted message content
            """
            super().__init__()
            self.content = content

    def __init__(self, placeholder: str = "Type your message...", **kwargs):
        """Initialize input bar.

        Args:
            placeholder: Placeholder text for input
        """
        super().__init__(**kwargs)
        self.placeholder = placeholder

    def compose(self) -> ComposeResult:
        """Compose the input bar layout."""
        with Vertical():
            yield TextArea(
                id="message-input",
            )
            yield Static(
                "Ctrl+Enter to send · Enter for newline · /help for commands · Ctrl+C to quit",
                classes="hint-text",
            )

    def _submit_message(self) -> None:
        """Submit the current message."""
        input_widget = self.query_one("#message-input", TextArea)
        message = input_widget.text.strip()

        if message:
            # Post message to parent
            self.post_message(self.MessageSubmitted(message))
            # Clear input
            input_widget.text = ""
            input_widget.focus()

    def on_key(self, event: Key) -> None:
        """Handle key events for submit shortcuts."""
        if event.key == "enter" and event.ctrl:
            event.stop()
            self._submit_message()

    def focus_input(self) -> None:
        """Focus the input field."""
        input_widget = self.query_one("#message-input", TextArea)
        input_widget.focus()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable input.

        Args:
            enabled: Whether input should be enabled
        """
        input_widget = self.query_one("#message-input", TextArea)

        input_widget.disabled = not enabled

        if enabled:
            input_widget.focus()

    def insert_text(self, text: str) -> None:
        """Insert text at cursor position in the input field.

        Args:
            text: Text to insert
        """
        input_widget = self.query_one("#message-input", TextArea)
        if hasattr(input_widget, "insert"):
            input_widget.insert(text)
        else:
            input_widget.text = f"{input_widget.text}{text}"
        input_widget.focus()
