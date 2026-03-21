"""Simple REPL-style streaming chat runner for Taskforce."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from taskforce.api.cli.output_formatter import TASKFORCE_THEME
from taskforce.api.cli.tool_display_formatter import (
    format_tool_call,
    format_tool_change_preview,
    format_tool_result,
)
import structlog

from taskforce.application.agent_registry import AgentRegistry
from taskforce.application.context_display_service import ContextDisplayService
from taskforce.application.executor import AgentExecutor, ProgressUpdate
from taskforce.application.factory import AgentFactory
from taskforce.application.skill_service import SkillService, get_skill_service
from taskforce.core.domain.agent_definition import AgentSource
from taskforce.core.domain.enums import EventType, MessageRole, SkillType, TaskStatus


logger = structlog.get_logger(__name__)


def _build_key_bindings() -> KeyBindings:
    """Build key bindings: Enter submits, Alt+Enter inserts newline."""
    kb = KeyBindings()

    @kb.add(Keys.Enter)
    def _submit(event: Any) -> None:
        event.current_buffer.validate_and_handle()

    @kb.add(Keys.Escape, Keys.Enter)
    def _newline(event: Any) -> None:
        event.current_buffer.insert_text("\n")

    return kb


@dataclass
class PlanState:
    steps: list[dict[str, Any]]
    text: str | None


class SimpleChatRunner:
    """Plain console chat runner with streaming output."""

    def __init__(
        self,
        session_id: str,
        profile: str,
        agent: Any,
        stream: bool,
        user_context: dict[str, Any] | None,
        telegram_polling: bool = False,
        conversation_manager: Any | None = None,
    ):
        self.session_id = session_id
        self.profile = profile
        self.agent = agent
        self.stream = stream
        self.user_context = user_context
        self.telegram_polling = telegram_polling
        self.console = Console(theme=TASKFORCE_THEME)
        self.executor = AgentExecutor()
        self.agent_registry = AgentRegistry()
        self.total_tokens = 0
        self.plan_state = PlanState(steps=[], text=None)
        self._last_event_signature: tuple[str, str] | None = None
        self._skill_service: SkillService | None = None
        self._context_service = ContextDisplayService()
        self._prompt_session: PromptSession[str] | None = None
        self._telegram_poller: Any | None = None
        self._gateway: Any | None = None
        self._scheduler: Any | None = None
        self._conversation_manager = conversation_manager
        self._conversation_id: str | None = None

        # Wire up scheduler for ScheduleTool / ReminderTool
        self._setup_scheduler()

        # Wire up Communication Gateway for channel-targeted ask_user
        self._setup_gateway()

    def _setup_scheduler(self) -> None:
        """Build a SchedulerService so ScheduleTool/ReminderTool can create jobs.

        When a scheduled job fires, the notification callback sends the
        message via the CommunicationGateway (wired later in _setup_gateway).
        """
        import os

        try:
            from taskforce.infrastructure.scheduler.scheduler_service import (
                SchedulerService,
            )

            work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")

            # Load notification defaults from butler profile for fallback.
            notif_defaults: dict[str, str] = {}
            try:
                from taskforce.application.profile_loader import ProfileLoader

                butler_cfg = ProfileLoader(self.executor.factory.config_dir).load("butler")
                notif_defaults = butler_cfg.get("notifications", {})
            except Exception:
                pass

            async def _on_scheduler_event(event: Any) -> None:
                """Handle scheduler events by sending notifications via gateway."""
                payload = event.payload or {}
                action = payload.get("action", {})
                action_type = action.get("action_type", "")
                if action_type != "send_notification":
                    return
                if not self._gateway:
                    logger.warning("scheduler.notification_skipped", reason="no gateway")
                    return

                from taskforce.core.domain.gateway import NotificationRequest

                params = action.get("params", {})
                channel = params.get("channel") or notif_defaults.get(
                    "default_channel", "telegram"
                )
                recipient_id = params.get("recipient_id") or notif_defaults.get(
                    "default_recipient_id", ""
                )
                request = NotificationRequest(
                    channel=channel,
                    recipient_id=recipient_id,
                    message=params.get("message", ""),
                    metadata={},
                )
                result = await self._gateway.send_notification(request)
                if not result.success:
                    logger.error(
                        "scheduler.notification_failed",
                        channel=channel,
                        recipient_id=recipient_id,
                        error=result.error,
                    )

            self._scheduler = SchedulerService(
                work_dir=work_dir,
                event_callback=_on_scheduler_event,
            )
            self.executor.factory.set_scheduler(self._scheduler)
        except Exception as exc:
            logger.warning("simple_chat.scheduler_setup_failed", error=str(exc))

    def _setup_gateway(self) -> None:
        """Build Communication Gateway when channel credentials are available.

        When ``TELEGRAM_BOT_TOKEN`` is set the CLI can send outbound
        Telegram messages and receive replies via long-polling — no
        webhook server required.
        """
        import os

        if not self.telegram_polling:
            return

        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not telegram_token:
            self.console.print(
                "[warning]⚠️ --telegram-polling enabled, but TELEGRAM_BOT_TOKEN is not set[/warning]"
            )
            return

        try:
            from taskforce.application.gateway import CommunicationGateway
            from taskforce.infrastructure.communication.gateway_registry import (
                build_gateway_components,
            )
            from taskforce.infrastructure.communication.telegram_poller import (
                TelegramPoller,
            )
            from taskforce.infrastructure.persistence.pending_channel_store import (
                FilePendingChannelQuestionStore,
            )

            work_dir = os.getenv("TASKFORCE_WORK_DIR", ".taskforce")
            components = build_gateway_components(work_dir=work_dir)
            pending_store = FilePendingChannelQuestionStore(work_dir=work_dir)

            gateway = CommunicationGateway(
                executor=self.executor,
                conversation_store=components.conversation_store,
                recipient_registry=components.recipient_registry,
                outbound_senders=components.outbound_senders,
                pending_channel_store=pending_store,
                max_conversation_history=30,
            )
            self.executor._gateway = gateway
            self.executor.factory.set_gateway(gateway)
            self._gateway = gateway

            # Patch gateway into already-instantiated agent tools.
            # Agent.tools is a dict[str, ToolProtocol].
            if self.agent and hasattr(self.agent, "tools"):
                notif_tool = self.agent.tools.get("send_notification")
                if notif_tool is not None:
                    notif_tool._gateway = gateway

            # Prepare Telegram poller (started in run())
            sender = components.outbound_senders.get("telegram")
            self._telegram_poller = TelegramPoller(
                bot_token=telegram_token,
                pending_store=pending_store,
                outbound_sender=sender,
                recipient_registry=components.recipient_registry,
                inbound_message_handler=self._handle_telegram_inbound_message,
            )

            self.console.print("[info]📡 Telegram channel configured (long-polling mode)[/info]")
        except Exception as exc:
            self.console.print(f"[warning]⚠️ Telegram setup failed: {exc}[/warning]")

    @property
    def prompt_session(self) -> PromptSession[str]:
        """Lazy-initialise the prompt session (requires a real terminal)."""
        if self._prompt_session is None:
            self._prompt_session = PromptSession(
                multiline=True,
                key_bindings=_build_key_bindings(),
            )
        return self._prompt_session

    @property
    def skill_service(self) -> SkillService:
        """Lazy-initialise the skill service."""
        if self._skill_service is None:
            self._skill_service = get_skill_service()
        return self._skill_service

    async def run(self) -> None:
        """Run the REPL loop."""
        self._print_banner()
        self._print_session_info()

        # Start a fresh conversation on each CLI launch.
        # The previous conversation is auto-archived by create_new().
        if self._conversation_manager:
            self._conversation_id = await self._conversation_manager.create_new("cli")

        # Start scheduler for reminder/schedule tools
        if self._scheduler:
            await self._scheduler.start()

        # Start Telegram long-polling if configured
        if self._telegram_poller:
            await self._telegram_poller.start()

        try:
            while True:
                message = await self._read_input()
                if not message:
                    continue

                if message.startswith("/"):
                    should_exit = await self._handle_command(message)
                    if should_exit:
                        return
                    continue

                await self._handle_chat_message(message)
        finally:
            if self._telegram_poller:
                await self._telegram_poller.stop()
            if self._scheduler:
                await self._scheduler.stop()

    async def _handle_telegram_inbound_message(
        self,
        conversation_id: str,
        sender_id: str,
        message: str,
        attachments: list[dict] | None = None,
    ) -> None:
        """Route unsolicited Telegram messages through CommunicationGateway."""
        if not self._gateway:
            return

        from taskforce.core.domain.gateway import GatewayOptions, InboundMessage

        metadata: dict = {}
        if attachments:
            metadata["attachments"] = attachments

        inbound = InboundMessage(
            channel="telegram",
            conversation_id=conversation_id,
            message=message,
            sender_id=sender_id,
            metadata=metadata,
        )
        options = GatewayOptions(profile=self.profile, user_context=self.user_context)
        await self._gateway.handle_message(inbound, options)

    async def _read_input(self) -> str:
        """Read input from the user with multi-line paste support."""
        try:
            value = await self.prompt_session.prompt_async("👤 You > ")
        except (EOFError, KeyboardInterrupt):
            return "/quit"
        return value.strip()

    async def _handle_command(self, command: str) -> bool:
        """Handle slash commands. Returns True if we should exit."""
        parts = command.lstrip("/").split(maxsplit=1)
        cmd_name = parts[0].lower()
        command_args = parts[1] if len(parts) > 1 else ""

        if cmd_name in ["help", "h"]:
            self._show_help()
        elif cmd_name in ["clear", "c"]:
            await self._reset_context()
            self.console.clear()
            self._print_banner()
            self._print_session_info()
        elif cmd_name in ["export", "e"]:
            self._print_system("Export functionality coming soon...", style="warning")
        elif cmd_name in ["exit", "quit", "q"]:
            return True
        elif cmd_name == "new":
            await self._start_new_conversation()
        elif cmd_name == "debug":
            self._print_system("Debug mode toggling is not used in simple mode.", style="warning")
        elif cmd_name == "tokens":
            self._print_system(f"Total tokens used: {self.total_tokens:,}", style="info")
        elif cmd_name == "context":
            await self._show_context(command_args)
        elif cmd_name == "plugins":
            self._list_plugins()
        elif cmd_name == "skills":
            self._list_skills()
        else:
            skill, args = self.skill_service.resolve_slash_command(command)
            if skill is not None:
                if skill.skill_type == SkillType.PROMPT:
                    await self._execute_prompt_skill(skill, args)
                elif skill.skill_type == SkillType.AGENT:
                    await self._execute_agent_skill(skill, args)
                else:
                    # CONTEXT skill: activate it in both the service and the agent
                    self.skill_service.activate_skill(skill.name)
                    self._ensure_agent_skill_manager()
                    self.agent.skill_manager.activate_skill(skill.name)
                    self._print_system(f"Activated context skill: {skill.name}", style="info")
            elif await self._try_switch_plugin(cmd_name):
                return False
            else:
                self._print_system(f"Unknown command: {command}", style="warning")
                self._print_system("Type /help for available commands.", style="info")

        return False

    def _show_help(self) -> None:
        """Show help text."""
        help_text = (
            "**Commands:**\n"
            "- /help or /h\n"
            "- /new — start a new conversation\n"
            "- /clear or /c\n"
            "- /export or /e\n"
            "- /tokens\n"
            "- /context [full]\n"
            "- /plugins\n"
            "- /skills\n"
            "- /debug\n"
            "- /quit or /exit\n"
            "\n**Input:**\n"
            "- **Enter** — send message\n"
            "- **Alt+Enter** — insert newline\n"
            "- Multi-line paste is supported automatically\n"
            "\n**Skills (invokable via /skill-name [args]):**\n"
            "- Run /skills to see all available skills\n"
        )
        self.console.print(Markdown(help_text))

    def _list_plugins(self) -> None:
        """List available plugin agents."""
        plugins = list(self.agent_registry.list_all(sources=[AgentSource.PLUGIN]))
        if not plugins:
            self._print_system("No plugin agents found.", style="info")
            self._print_system(
                "Add plugin folders under examples/ or src/taskforce/plugins/.",
                style="info",
            )
            return

        lines = ["**Plugin Agents:**"]
        for plugin in sorted(plugins, key=lambda item: item.agent_id):
            description = plugin.description or "Plugin agent"
            path = f"[{plugin.plugin_path}]" if plugin.plugin_path else ""
            lines.append(f"- /{plugin.agent_id} — {description} {path}")
        self.console.print(Markdown("\n".join(lines)))

    def _list_skills(self) -> None:
        """List available skills grouped by type."""
        all_meta = self.skill_service.get_all_metadata()
        if not all_meta:
            self._print_system("No skills found.", style="info")
            self._print_system(
                "Add skills under .taskforce/skills/ or ~/.taskforce/skills/.",
                style="info",
            )
            return

        active_names = {s.name for s in self.skill_service.get_active_skills()}

        context_skills = [m for m in all_meta if m.skill_type == SkillType.CONTEXT]
        prompt_skills = [m for m in all_meta if m.skill_type == SkillType.PROMPT]
        agent_skills = [m for m in all_meta if m.skill_type == SkillType.AGENT]

        lines = ["**Skills:**"]

        if prompt_skills:
            lines.append("\n*Prompt skills (invokable via /name [args]):*")
            for meta in sorted(prompt_skills, key=lambda m: m.name):
                slash = f"/{meta.effective_slash_name}"
                lines.append(f"- {slash} — {meta.description}")

        if agent_skills:
            lines.append("\n*Agent skills (invokable via /name [args]):*")
            for meta in sorted(agent_skills, key=lambda m: m.name):
                slash = f"/{meta.effective_slash_name}"
                lines.append(f"- {slash} — {meta.description}")

        if context_skills:
            lines.append("\n*Context skills (activated via /name):*")
            for meta in sorted(context_skills, key=lambda m: m.name):
                active_marker = " ✅" if meta.name in active_names else ""
                lines.append(f"- /{meta.effective_slash_name} — {meta.description}{active_marker}")

        self.console.print(Markdown("\n".join(lines)))

    def _ensure_agent_skill_manager(self) -> None:
        """Ensure the agent has a SkillManager for context skill injection."""
        if self.agent.skill_manager is None:
            from taskforce.application.skill_manager import SkillManager

            self.agent.skill_manager = SkillManager(include_global_skills=True)

    async def _execute_prompt_skill(self, skill: Any, arguments: str) -> None:
        """Execute a PROMPT-type skill by substituting args and sending as chat."""
        prompt = self.skill_service.prepare_skill_prompt(skill, arguments)
        self._print_system(f"Executing /{skill.effective_slash_name}...", style="info")
        await self._handle_chat_message(prompt)

    async def _execute_agent_skill(self, skill: Any, arguments: str) -> None:
        """Execute an AGENT-type skill by temporarily overriding agent config."""
        self._print_system(
            f"Switching to agent skill: {skill.name} (/{skill.effective_slash_name})",
            style="info",
        )
        agent_config = skill.agent_config or {}
        factory = AgentFactory()

        if self.agent:
            await self.agent.close()

        skill_profile = agent_config.get("profile") or self.profile
        self.agent = await factory.create_agent(
            config=skill_profile,
            user_context=self.user_context,
        )
        self.profile = f"skill:{skill.name}"
        self._print_session_info()

        if arguments:
            prompt = skill.substitute_arguments(arguments)
            await self._handle_chat_message(prompt)

    async def _try_switch_plugin(self, command_name: str) -> bool:
        """Switch to a plugin agent if the command matches one."""
        plugin_def = self.agent_registry.get(command_name)
        if not plugin_def or plugin_def.source != AgentSource.PLUGIN:
            return False

        plugin_path = plugin_def.plugin_path
        if not plugin_path:
            self._print_system(
                f"Plugin definition for /{command_name} is missing a path.",
                style="warning",
            )
            return True

        self._print_system(f"Switching to plugin: {command_name}", style="info")
        factory = AgentFactory()

        if self.agent:
            await self.agent.close()

        self.agent = await factory.create_agent_with_plugin(
            plugin_path=plugin_path,
            profile=plugin_def.base_profile or self.profile,
            user_context=self.user_context,
        )
        self.profile = f"plugin:{command_name}"
        self._print_session_info()
        return True

    async def _handle_chat_message(self, content: str) -> None:
        """Handle a regular chat message.

        When a ``ConversationManager`` is wired (ADR-016 persistent mode),
        it is the **primary** store for conversation history. The legacy
        session-based state is still written for backward compatibility.
        """
        user_msg = {"role": MessageRole.USER.value, "content": content}

        # Primary: persist to ConversationManager when available.
        if self._conversation_manager and self._conversation_id:
            await self._conversation_manager.append_message(
                self._conversation_id, user_msg,
            )
            # Load history from conversation manager (source of truth).
            history = await self._conversation_manager.get_messages(
                self._conversation_id,
            )
        else:
            # Fallback: legacy session-based history.
            state = await self.agent.state_manager.load_state(self.session_id) or {}
            history = state.get("conversation_history", [])
            history.append(user_msg)
            state["conversation_history"] = history
            await self.agent.state_manager.save_state(self.session_id, state)

        await self._stream_response(content, history)

    async def _stream_response(self, content: str, history: list[dict[str, Any]]) -> None:
        """Stream the agent response and show events inline."""
        final_tokens: list[str] = []
        paused_question: dict[str, Any] | None = None
        started_output = False
        current_step: str | None = None
        thinking_emitted_for_steps: set[str] = set()

        async for update in self.executor.execute_mission_streaming(
            mission=content,
            profile=self.profile,
            session_id=self.session_id,
            conversation_history=history,
            user_context=self.user_context,
            agent=self.agent,
        ):
            event_type = update.event_type

            if event_type == EventType.LLM_TOKEN.value:
                token = update.details.get("content", "")
                if token:
                    if not started_output:
                        self.console.print("[agent]🤖 Agent:[/agent] ", end="")
                        started_output = True
                    self.console.print(token, end="", style="agent", soft_wrap=True)
                    self.console.file.flush()
                    final_tokens.append(token)

            elif event_type == EventType.FINAL_ANSWER.value:
                if not final_tokens:
                    content = update.details.get("content", "")
                    if content:
                        self.console.print(f"[agent]🤖 Agent:[/agent] {content}")
                        final_tokens.append(content)

            elif event_type == EventType.THOUGHT.value:
                thought_text = (
                    update.details.get("rationale")
                    or update.details.get("thought")
                    or update.message
                )
                step_key = update.details.get("step") or current_step
                if step_key is not None:
                    thinking_emitted_for_steps.add(str(step_key))
                if thought_text:
                    self.console.print(f"[thought]💭 Thinking:[/thought] {thought_text}")

            elif event_type == EventType.OBSERVATION.value:
                observation = update.details.get("observation") or update.message
                if observation:
                    self.console.print(f"[observation]🔎 Observation:[/observation] {observation}")

            elif event_type == EventType.PLAN_UPDATED.value:
                self._handle_plan_update(update)

            elif event_type == EventType.TOKEN_USAGE.value:
                usage = update.details
                self.total_tokens += usage.get("total_tokens", 0)

            elif event_type == EventType.TOOL_CALL.value:
                tool = update.details.get("tool", "unknown")
                params = update.details.get("args", update.details.get("params", {}))
                normalized_params = params if isinstance(params, dict) else {}
                signature = (event_type, f"{tool}:{params}")
                if signature != self._last_event_signature:
                    display = format_tool_call(tool, normalized_params)
                    self.console.print(f"[action]🔧 {display}[/action]")
                    change_preview = format_tool_change_preview(tool, normalized_params)
                    if change_preview:
                        self.console.print(f"[action]{change_preview}[/action]")
                self._last_event_signature = signature

            elif event_type == EventType.TOOL_RESULT.value:
                tool = update.details.get("tool", "unknown")
                success = update.details.get("success", True)
                output = str(update.details.get("output", ""))
                status = "✅" if success else "❌"
                signature = (event_type, f"{tool}:{success}:{output[:200]}")
                if signature != self._last_event_signature:
                    display = format_tool_result(tool, success, output)
                    self.console.print(f"[observation]{status} {tool}:[/observation] {display}")
                self._last_event_signature = signature

            elif event_type == EventType.STEP_START.value:
                step = update.details.get("step", "?")
                current_step = str(step)
                self.console.print(f"[info]🧠 Step {step} starting...[/info]")
                if current_step not in thinking_emitted_for_steps:
                    self.console.print("[thought]💭 Thinking...[/thought]")
                    thinking_emitted_for_steps.add(current_step)

            elif event_type == EventType.STARTED.value:
                self.console.print("[info]🚀 Started[/info]")

            elif event_type == EventType.ASK_USER.value:
                details = update.details
                channel_routed = details.get("channel_routed", False)
                channel_received = details.get("channel_response_received", False)

                if channel_routed:
                    # Channel-targeted question handled by executor/gateway
                    channel = details.get("channel", "")
                    recipient = details.get("recipient_id", "")
                    question = details.get("question", "")
                    self.console.print(
                        f"[warning]📨 Sending question to "
                        f"{channel}:{recipient}:[/warning] {question}"
                    )
                    self.console.print(
                        f"[info]⏳ Waiting for response from " f"{channel}:{recipient}...[/info]"
                    )
                elif channel_received:
                    # Response received from channel (executor handled it)
                    channel = details.get("channel", "")
                    recipient = details.get("recipient_id", "")
                    response = details.get("response", "")
                    self.console.print(
                        f"[info]✅ Response from {channel}:{recipient}:[/info] " f"{response}"
                    )
                else:
                    # Standard ask_user — pauses for CLI user input
                    paused_question = details
                    question = details.get("question", "")
                    missing = details.get("missing", [])
                    if missing:
                        self.console.print(
                            f"[warning]❓ Agent needs input:[/warning] {question} "
                            f"(Missing: {', '.join(map(str, missing))})"
                        )
                    else:
                        self.console.print(f"[warning]❓ Agent needs input:[/warning] {question}")

            elif event_type == EventType.ERROR.value:
                self.console.print(f"[error]❌ Error:[/error] {update.message}")

            elif event_type == EventType.COMPLETE.value:
                # COMPLETE is a status event, not agent content — don't
                # capture its message (e.g. "Execution completed. Status: completed")
                # into final_tokens, which feeds conversation history.
                pass

        if started_output:
            self.console.print()

        if paused_question is not None:
            question_text = str(paused_question.get("question", "")).strip()
            if question_text:
                await self._persist_assistant_message(question_text)
            return

        final_message = "".join(final_tokens) if final_tokens else "No response"
        await self._persist_assistant_message(final_message)

        # Display detailed token analytics if available
        self._print_token_analytics()

    def _handle_plan_update(self, update: ProgressUpdate) -> None:
        """Handle plan update events."""
        action = update.details.get("action", "updated")
        if update.details.get("steps"):
            self.plan_state.steps = [
                {"description": step, "status": "PENDING"}
                for step in update.details.get("steps", [])
            ]
            self.plan_state.text = None
        if update.details.get("plan"):
            self.plan_state.text = update.details.get("plan")
            self.plan_state.steps = []
        if update.details.get("step") and update.details.get("status"):
            step_index = update.details.get("step") - 1
            if 0 <= step_index < len(self.plan_state.steps):
                self.plan_state.steps[step_index]["status"] = update.details.get(
                    "status",
                    "PENDING",
                )

        self.console.print(f"[info]🧭 Plan {action}[/info]")
        if self.plan_state.steps:
            for idx, step in enumerate(self.plan_state.steps, start=1):
                status = step.get("status", "PENDING")
                marker = (
                    "✓"
                    if status in {TaskStatus.DONE.value, "COMPLETED"}
                    else (
                        "⏳"
                        if status
                        in {
                            "IN_PROGRESS",
                            "ACTIVE",
                        }
                        else " "
                    )
                )
                desc = step.get("description", "").strip()
                self.console.print(f"  [{marker}] {idx}. {desc}")
        elif self.plan_state.text:
            for line in self.plan_state.text.strip().splitlines():
                line = line.strip()
                if line:
                    self.console.print(f"  {line}")

    async def _start_new_conversation(self) -> None:
        """Start a new conversation, archiving the current one.

        If a ``ConversationManager`` is wired in, this creates a new
        conversation and resets the local context. Otherwise falls back
        to a simple context reset.
        """
        if self._conversation_manager:
            self._conversation_id = await self._conversation_manager.create_new("cli")
            self._print_system(
                f"New conversation started: {self._conversation_id[:8]}",
                style="info",
            )
        await self._reset_context()

    async def _persist_assistant_message(self, content: str) -> None:
        """Persist an assistant message using the primary store.

        In persistent mode (ADR-016), the ConversationManager is the
        primary store. Otherwise falls back to the legacy session state.
        """
        assistant_msg = {
            "role": MessageRole.ASSISTANT.value,
            "content": content,
            "verified": True,
        }
        if self._conversation_manager and self._conversation_id:
            await self._conversation_manager.append_message(
                self._conversation_id, assistant_msg,
            )
        else:
            state = await self.agent.state_manager.load_state(self.session_id) or {}
            history = state.get("conversation_history", [])
            history.append(assistant_msg)
            state["conversation_history"] = history
            await self.agent.state_manager.save_state(self.session_id, state)

    async def _mirror_assistant_message(self, content: str) -> None:
        """Mirror an assistant message to the conversation manager.

        .. deprecated::
            Kept for backward compatibility. New code should use
            ``_persist_assistant_message`` instead.
        """
        if self._conversation_manager and self._conversation_id:
            await self._conversation_manager.append_message(
                self._conversation_id,
                {"role": MessageRole.ASSISTANT.value, "content": content},
            )

    async def _reset_context(self) -> None:
        """Reset conversation context to default state.

        Clears conversation history and resets in-memory counters
        (tokens, plan state, dedup signature). In persistent mode
        the conversation is archived and a new one started; otherwise
        the legacy session state is cleared.
        """
        self.total_tokens = 0
        self.plan_state = PlanState(steps=[], text=None)
        self._last_event_signature = None

        if not (self._conversation_manager and self._conversation_id):
            # Legacy fallback: clear session state.
            state = await self.agent.state_manager.load_state(self.session_id) or {}
            state["conversation_history"] = []
            await self.agent.state_manager.save_state(self.session_id, state)

    def _print_banner(self) -> None:
        self.console.print("[info]💬 Taskforce Chat (Simple)[/info]")
        self.console.print("[info]Enter to send, Alt+Enter for newline, /help for commands[/info]")

    def _print_session_info(self) -> None:
        if self._conversation_id:
            self.console.print(
                f"[info]Conversation:[/info] {self._conversation_id[:8]}  "
                f"[info]Profile:[/info] {self.profile}"
            )
        else:
            self.console.print(
                f"[info]Session:[/info] {self.session_id[:8]}  "
                f"[info]Profile:[/info] {self.profile}"
            )
        if self.telegram_polling:
            self.console.print("[info]Telegram polling:[/info] enabled")
        if self.user_context:
            for key, value in self.user_context.items():
                self.console.print(f"[info]{key}:[/info] {value}")

    def _print_system(self, message: str, style: str = "system") -> None:
        self.console.print(f"[{style}]ℹ️ {message}[/{style}]")

    def _print_token_analytics(self) -> None:
        """Show detailed token analytics after each agent response."""
        from taskforce.application.token_analytics_facade import get_execution_token_summary
        from taskforce.api.cli.output_formatter import TaskforceConsole

        summary = get_execution_token_summary()
        if summary is not None:
            tf_console = TaskforceConsole()
            tf_console.print_token_analytics(summary)

    async def _show_context(self, command_args: str) -> None:
        """Render a context snapshot showing what is sent to the LLM."""
        include_content = command_args.strip().lower() == "full"
        state = await self.agent.state_manager.load_state(self.session_id) or {}
        snapshot = self._context_service.build_snapshot(
            agent=self.agent,
            state=state,
            include_content=include_content,
        )

        summary = (
            f"Total Tokens: {snapshot.total_tokens:,} / {snapshot.max_tokens:,} "
            f"({snapshot.utilization_percent:.1f}%)"
        )
        self.console.print(Panel(summary, title="Context Snapshot", border_style="cyan"))
        self._render_context_group("System Prompt", snapshot.system_prompt, include_content)
        self._render_context_group("Conversation History", snapshot.messages, include_content)
        self._render_context_group("Skills", snapshot.skills, include_content)
        self._render_context_group("Tool Definitions", snapshot.tools, include_content)

    def _render_context_group(self, title: str, items: list[Any], include_content: bool) -> None:
        """Render one context group as a token table."""
        if not items:
            self.console.print(f"[dim]{title}: empty[/dim]")
            return

        table = Table(title=title)
        table.add_column("Section", style="cyan")
        table.add_column("Tokens", style="magenta", justify="right")
        if include_content:
            table.add_column("Content", style="white")

        for item in items:
            row = [item.title, f"~{item.tokens}"]
            if include_content:
                content = (item.content or "").strip() or "-"
                row.append(content)
            table.add_row(*row)

        self.console.print(table)


async def run_simple_chat(
    session_id: str,
    profile: str,
    agent: Any,
    stream: bool,
    user_context: dict[str, Any] | None,
    telegram_polling: bool = False,
    conversation_manager: Any | None = None,
) -> None:
    """Entry point to run the simple chat loop."""
    runner = SimpleChatRunner(
        session_id=session_id,
        profile=profile,
        agent=agent,
        stream=stream,
        user_context=user_context,
        telegram_polling=telegram_polling,
        conversation_manager=conversation_manager,
    )
    await runner.run()
