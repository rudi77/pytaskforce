"""Main Textual application for Taskforce chat UI."""

import asyncio
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Footer

from taskforce.api.cli.chat_ui.widgets import (
    ChatLog,
    Header,
    InputBar,
    PlanPanel,
)
from typing import Any

from taskforce.application.executor import AgentExecutor, ProgressUpdate


class TaskforceChatApp(App):
    """Taskforce chat application with Textual UI."""

    TITLE = "Taskforce - ReAct Agent Framework"
    CSS_PATH = "styles.css"

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear Chat"),
        ("f1", "help", "Help"),
    ]

    def __init__(
        self,
        session_id: str,
        profile: str,
        agent: Any,
        debug: bool = False,
        stream: bool = False,
        user_context: Optional[dict] = None,
        **kwargs,
    ):
        """Initialize the chat application.

        Args:
            session_id: Session ID
            profile: Configuration profile
            agent: Agent instance
            debug: Enable debug mode
            stream: Enable streaming mode
            user_context: Optional RAG user context
        """
        super().__init__(**kwargs)
        self.session_id = session_id
        self.profile = profile
        self.agent = agent
        self.debug_mode = debug
        self.stream_mode = stream
        self.user_context = user_context
        self.executor = AgentExecutor()
        self._processing = False
        self._current_agent_message = []

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header(
            session_id=self.session_id,
            profile=self.profile,
            user_context=self.user_context,
        )
        with Container(id="main-container"):
            yield PlanPanel(id="plan-panel")
            yield ChatLog(id="chat-log")
        yield InputBar(id="input-bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Handle app mount event."""
        # Show welcome message
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.add_system_message(
            f"Welcome to Taskforce! {'Debug mode enabled.' if self.debug_mode else ''}"
        )
        chat_log.add_system_message(
            "Type your message or use /help for available commands."
        )

        # Focus input
        input_bar = self.query_one("#input-bar", InputBar)
        input_bar.focus_input()

    async def on_input_bar_message_submitted(
        self, message: InputBar.MessageSubmitted
    ) -> None:
        """Handle message submission from input bar.

        Args:
            message: Message submitted event
        """
        content = message.content

        # Handle commands
        if content.startswith("/"):
            await self._handle_command(content)
            return

        # Handle chat message
        await self._handle_chat_message(content)

    async def _handle_command(self, command: str) -> None:
        """Handle slash commands.

        Args:
            command: Command string
        """
        chat_log = self.query_one("#chat-log", ChatLog)
        cmd_lower = command.lower()

        if cmd_lower in ["/help", "/h"]:
            await self._show_help()
        elif cmd_lower in ["/clear", "/c"]:
            await self._clear_chat()
        elif cmd_lower in ["/export", "/e"]:
            await self._export_chat()
        elif cmd_lower in ["/exit", "/quit", "/q"]:
            self.exit()
        elif cmd_lower == "/debug":
            self._toggle_debug()
        elif cmd_lower == "/tokens":
            await self._show_tokens()
        else:
            chat_log.add_error(f"Unknown command: {command}")
            chat_log.add_system_message("Type /help for available commands")

    async def _show_help(self) -> None:
        """Show help message."""
        chat_log = self.query_one("#chat-log", ChatLog)
        help_text = """**Available Commands:**

• **/help** or **/h** - Show this help message
• **/clear** or **/c** - Clear chat history
• **/export** or **/e** - Export chat to file
• **/debug** - Toggle debug mode
• **/tokens** - Show token usage statistics
• **/exit** or **/quit** - Exit the application

**Keyboard Shortcuts:**
• **Enter** - Send message
• **Ctrl+C** - Quit application
• **Ctrl+L** - Clear chat
• **F1** - Show help"""
        chat_log.add_system_message(help_text)

    async def _clear_chat(self) -> None:
        """Clear chat history."""
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.clear_messages()
        chat_log.add_system_message("Chat cleared.")

    async def _export_chat(self) -> None:
        """Export chat to file."""
        chat_log = self.query_one("#chat-log", ChatLog)
        # TODO: Implement chat export
        chat_log.add_system_message("Export functionality coming soon...")

    def _toggle_debug(self) -> None:
        """Toggle debug mode."""
        self.debug_mode = not self.debug_mode
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.add_system_message(
            f"Debug mode {'enabled' if self.debug_mode else 'disabled'}"
        )

    async def _show_tokens(self) -> None:
        """Show token usage statistics."""
        header = self.query_one(Header)
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.add_system_message(
            f"Total tokens used: {header.token_count:,}"
        )

    async def _handle_chat_message(self, content: str) -> None:
        """Handle regular chat message.

        Args:
            content: Message content
        """
        if self._processing:
            chat_log = self.query_one("#chat-log", ChatLog)
            chat_log.add_system_message("Please wait for the current response to complete.")
            return

        # Add user message to chat
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.add_user_message(content)

        # Disable input while processing
        input_bar = self.query_one("#input-bar", InputBar)
        input_bar.set_enabled(False)

        # Update header status
        header = self.query_one(Header)
        header.update_status("Initializing")

        self._processing = True
        self._current_agent_message = []

        try:
            # Load conversation history
            state = await self.agent.state_manager.load_state(self.session_id) or {}
            history = state.get("conversation_history", [])

            # Add user message to history
            history.append({"role": "user", "content": content})
            state["conversation_history"] = history
            await self.agent.state_manager.save_state(self.session_id, state)

            if self.stream_mode:
                # Streaming execution
                await self._execute_streaming(content, history)
            else:
                # Standard execution
                await self._execute_standard(content)

        except Exception as e:
            chat_log.add_error(f"Error: {str(e)}")
            header.update_status("Error")
        finally:
            self._processing = False
            input_bar.set_enabled(True)
            header.update_status("Idle")

    async def _execute_standard(self, message: str) -> None:
        """Execute message in standard (non-streaming) mode.

        Args:
            message: User message
        """
        chat_log = self.query_one("#chat-log", ChatLog)
        header = self.query_one(Header)

        header.update_status("Working")

        # Execute with agent
        result = await self.agent.execute(mission=message, session_id=self.session_id)

        # Add response to chat
        thought = None
        if self.debug_mode and hasattr(result, 'thoughts') and result.thoughts:
            thought = result.thoughts[-1] if result.thoughts else None

        chat_log.add_agent_message(result.final_message, thought=thought)

        # Update token usage
        if result.token_usage:
            total_tokens = result.token_usage.get("total_tokens", 0)
            header.add_tokens(total_tokens)

        # Save to history
        state = await self.agent.state_manager.load_state(self.session_id) or {}
        history = state.get("conversation_history", [])
        history.append({"role": "assistant", "content": result.final_message})
        state["conversation_history"] = history
        await self.agent.state_manager.save_state(self.session_id, state)

        header.update_status("Complete")

    async def _execute_streaming(self, message: str, history: list) -> None:
        """Execute message in streaming mode.

        Args:
            message: User message
            history: Conversation history
        """
        chat_log = self.query_one("#chat-log", ChatLog)
        header = self.query_one(Header)
        plan_panel = self.query_one("#plan-panel", PlanPanel)

        current_step = 0
        current_thought = None
        final_answer_tokens = []

        async for update in self.executor.execute_mission_streaming(
            mission=message,
            profile=self.profile,
            session_id=self.session_id,
            conversation_history=history,
            user_context=self.user_context,
        ):
            await self._handle_stream_update(
                update,
                chat_log,
                header,
                plan_panel,
                final_answer_tokens,
            )

        # Save final response to history
        final_message = "".join(final_answer_tokens) if final_answer_tokens else "No response"
        state = await self.agent.state_manager.load_state(self.session_id) or {}
        history = state.get("conversation_history", [])
        history.append({"role": "assistant", "content": final_message})
        state["conversation_history"] = history
        await self.agent.state_manager.save_state(self.session_id, state)

    async def _handle_stream_update(
        self,
        update: ProgressUpdate,
        chat_log: ChatLog,
        header: Header,
        plan_panel: PlanPanel,
        final_answer_tokens: list,
    ) -> None:
        """Handle streaming update event.

        Args:
            update: Execution update event
            chat_log: Chat log widget
            header: Header widget
            plan_panel: Plan panel widget
            final_answer_tokens: List to accumulate final answer tokens
        """
        event_type = update.event_type

        if event_type == "started":
            header.update_status("Initializing")

        elif event_type == "step_start":
            header.update_status("Thinking")

        elif event_type == "tool_call":
            tool_name = update.details.get("tool", "unknown")
            tool_params = update.details.get("params", {})
            header.update_status(f"Calling Tool")
            if self.debug_mode:
                chat_log.add_tool_call(tool_name, tool_params)

        elif event_type == "tool_result":
            tool_name = update.details.get("tool", "unknown")
            success = update.details.get("success", True)
            output = str(update.details.get("output", ""))[:200]
            header.update_status("Processing")
            if self.debug_mode:
                chat_log.add_tool_result(tool_name, output, success)

        elif event_type == "llm_token":
            token = update.details.get("content", "")
            if token:
                final_answer_tokens.append(token)
                header.update_status("Responding")

        elif event_type == "plan_updated":
            if update.details.get("steps"):
                steps = update.details.get("steps", [])
                plan_panel.update_plan_steps(steps)
            elif update.details.get("plan"):
                plan_text = update.details.get("plan")
                plan_panel.update_plan_text(plan_text)
            if update.details.get("step") and update.details.get("status"):
                step_index = update.details.get("step")
                status = update.details.get("status")
                plan_panel.update_step_status(step_index, status)

        elif event_type == "token_usage":
            usage = update.details
            tokens = usage.get("total_tokens", 0)
            header.add_tokens(tokens)

        elif event_type == "final_answer":
            if not final_answer_tokens:
                content = update.details.get("content", "")
                if content:
                    final_answer_tokens.append(content)
            # Add agent message to chat
            final_message = "".join(final_answer_tokens)
            if final_message:
                chat_log.add_agent_message(final_message)
            header.update_status("Complete")

        elif event_type == "complete":
            if not final_answer_tokens and update.message:
                final_answer_tokens.append(update.message)
                chat_log.add_agent_message(update.message)
            header.update_status("Complete")

        elif event_type == "error":
            chat_log.add_error(f"Error: {update.message}")
            header.update_status("Error")

    def action_clear(self) -> None:
        """Action to clear chat (Ctrl+L)."""
        asyncio.create_task(self._clear_chat())

    def action_help(self) -> None:
        """Action to show help (F1)."""
        asyncio.create_task(self._show_help())
