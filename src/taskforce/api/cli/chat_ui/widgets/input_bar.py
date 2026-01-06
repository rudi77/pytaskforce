"""Input bar widget for user message input."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Input, Static


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

    InputBar Horizontal {
        width: 100%;
        height: auto;
    }

    InputBar Input {
        width: 1fr;
        margin-right: 1;
    }

    InputBar Button {
        width: auto;
        min-width: 10;
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
        with Horizontal():
            yield Input(
                placeholder=self.placeholder,
                id="message-input",
            )
            yield Button("Send", variant="primary", id="send-button")
        yield Static(
            "Commands: /help /clear /export /exit  |  Ctrl+C to quit",
            classes="hint-text",
        )

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission via Enter key.

        Args:
            event: Input submitted event
        """
        self._submit_message()

    @on(Button.Pressed, "#send-button")
    def on_send_button_pressed(self, event: Button.Pressed) -> None:
        """Handle send button press.

        Args:
            event: Button pressed event
        """
        self._submit_message()

    def _submit_message(self) -> None:
        """Submit the current message."""
        input_widget = self.query_one("#message-input", Input)
        message = input_widget.value.strip()

        if message:
            # Post message to parent
            self.post_message(self.MessageSubmitted(message))
            # Clear input
            input_widget.value = ""
            input_widget.focus()

    def focus_input(self) -> None:
        """Focus the input field."""
        input_widget = self.query_one("#message-input", Input)
        input_widget.focus()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable input.

        Args:
            enabled: Whether input should be enabled
        """
        input_widget = self.query_one("#message-input", Input)
        send_button = self.query_one("#send-button", Button)

        input_widget.disabled = not enabled
        send_button.disabled = not enabled

        if enabled:
            input_widget.focus()

    def insert_text(self, text: str) -> None:
        """Insert text at cursor position in the input field.

        Args:
            text: Text to insert
        """
        input_widget = self.query_one("#message-input", Input)
        input_widget.insert_text_at_cursor(text)
        input_widget.focus()
