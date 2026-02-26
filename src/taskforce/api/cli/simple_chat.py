"""Simple REPL-style streaming chat runner for Taskforce."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from rich.console import Console
from rich.markdown import Markdown

from taskforce.api.cli.output_formatter import TASKFORCE_THEME
from taskforce.application.agent_registry import AgentRegistry
from taskforce.application.executor import AgentExecutor, ProgressUpdate
from taskforce.application.factory import AgentFactory
from taskforce.application.skill_service import SkillService, get_skill_service
from taskforce.core.domain.agent_definition import AgentSource
from taskforce.core.domain.enums import EventType, MessageRole, SkillType, TaskStatus


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
    ):
        self.session_id = session_id
        self.profile = profile
        self.agent = agent
        self.stream = stream
        self.user_context = user_context
        self.console = Console(theme=TASKFORCE_THEME)
        self.executor = AgentExecutor()
        self.agent_registry = AgentRegistry()
        self.total_tokens = 0
        self.plan_state = PlanState(steps=[], text=None)
        self._last_event_signature: tuple[str, str] | None = None
        self._skill_service: SkillService | None = None
        self._prompt_session: PromptSession[str] | None = None

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
        parts[1] if len(parts) > 1 else ""

        if cmd_name in ["help", "h"]:
            self._show_help()
        elif cmd_name in ["clear", "c"]:
            self.console.clear()
            self._print_banner()
            self._print_session_info()
        elif cmd_name in ["export", "e"]:
            self._print_system("Export functionality coming soon...", style="warning")
        elif cmd_name in ["exit", "quit", "q"]:
            return True
        elif cmd_name == "debug":
            self._print_system("Debug mode toggling is not used in simple mode.", style="warning")
        elif cmd_name == "tokens":
            self._print_system(f"Total tokens used: {self.total_tokens:,}", style="info")
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
                    # CONTEXT skill: activate it
                    self.skill_service.activate_skill(skill.name)
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
            "- /clear or /c\n"
            "- /export or /e\n"
            "- /tokens\n"
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
                "Add plugin folders under examples/ or src/taskforce_extensions/plugins/.",
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
        """Handle a regular chat message."""
        state = await self.agent.state_manager.load_state(self.session_id) or {}
        history = state.get("conversation_history", [])
        history.append({"role": MessageRole.USER.value, "content": content})
        state["conversation_history"] = history
        await self.agent.state_manager.save_state(self.session_id, state)

        await self._stream_response(content, history)

    async def _stream_response(self, content: str, history: list[dict[str, Any]]) -> None:
        """Stream the agent response and show events inline."""
        final_tokens: list[str] = []
        paused_question: dict[str, Any] | None = None
        started_output = False

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
                if thought_text:
                    self.console.print(f"[thought]💭 Thought:[/thought] {thought_text}")

            elif event_type == EventType.OBSERVATION.value:
                observation = update.details.get("observation") or update.message
                if observation:
                    self.console.print(
                        f"[observation]🔎 Observation:[/observation] {observation}"
                    )

            elif event_type == EventType.PLAN_UPDATED.value:
                self._handle_plan_update(update)

            elif event_type == EventType.TOKEN_USAGE.value:
                usage = update.details
                self.total_tokens += usage.get("total_tokens", 0)

            elif event_type == EventType.TOOL_CALL.value:
                tool = update.details.get("tool", "unknown")
                params = update.details.get("args", update.details.get("params", {}))
                signature = (event_type, f"{tool}:{params}")
                if signature != self._last_event_signature:
                    self.console.print(
                        f"[action]🔧 Tool call:[/action] {tool} {params}"
                    )
                self._last_event_signature = signature

            elif event_type == EventType.TOOL_RESULT.value:
                tool = update.details.get("tool", "unknown")
                success = update.details.get("success", True)
                output = str(update.details.get("output", ""))[:200]
                status = "✅" if success else "❌"
                signature = (event_type, f"{tool}:{success}:{output}")
                if signature != self._last_event_signature:
                    self.console.print(
                        f"[observation]{status} {tool}:[/observation] {output}"
                    )
                self._last_event_signature = signature

            elif event_type == EventType.STEP_START.value:
                step = update.details.get("step", "?")
                self.console.print(f"[info]🧠 Step {step} starting...[/info]")

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
                        f"[info]⏳ Waiting for response from "
                        f"{channel}:{recipient}...[/info]"
                    )
                elif channel_received:
                    # Response received from channel (executor handled it)
                    channel = details.get("channel", "")
                    recipient = details.get("recipient_id", "")
                    response = details.get("response", "")
                    self.console.print(
                        f"[info]✅ Response from {channel}:{recipient}:[/info] "
                        f"{response}"
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
                        self.console.print(
                            f"[warning]❓ Agent needs input:[/warning] {question}"
                        )

            elif event_type == EventType.ERROR.value:
                self.console.print(f"[error]❌ Error:[/error] {update.message}")

            elif event_type == EventType.COMPLETE.value:
                if not final_tokens and update.message:
                    self.console.print(f"[agent]🤖 Agent:[/agent] {update.message}")
                    final_tokens.append(update.message)

        if started_output:
            self.console.print()

        if paused_question is not None:
            question_text = str(paused_question.get("question", "")).strip()
            if question_text:
                state = await self.agent.state_manager.load_state(self.session_id) or {}
                history = state.get("conversation_history", [])
                history.append({"role": MessageRole.ASSISTANT.value, "content": question_text})
                state["conversation_history"] = history
                await self.agent.state_manager.save_state(self.session_id, state)
            return

        final_message = "".join(final_tokens) if final_tokens else "No response"
        state = await self.agent.state_manager.load_state(self.session_id) or {}
        history = state.get("conversation_history", [])
        history.append({"role": MessageRole.ASSISTANT.value, "content": final_message})
        state["conversation_history"] = history
        await self.agent.state_manager.save_state(self.session_id, state)

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
                marker = "✓" if status in {TaskStatus.DONE.value, "COMPLETED"} else "⏳" if status in {
                    "IN_PROGRESS",
                    "ACTIVE",
                } else " "
                desc = step.get("description", "").strip()
                self.console.print(f"  [{marker}] {idx}. {desc}")
        elif self.plan_state.text:
            self.console.print(Markdown(self.plan_state.text))

    def _print_banner(self) -> None:
        self.console.print("[info]💬 Taskforce Chat (Simple)[/info]")
        self.console.print("[info]Enter to send, Alt+Enter for newline, /help for commands[/info]")

    def _print_session_info(self) -> None:
        self.console.print(
            f"[info]Session:[/info] {self.session_id[:8]}  "
            f"[info]Profile:[/info] {self.profile}"
        )
        if self.user_context:
            for key, value in self.user_context.items():
                self.console.print(f"[info]{key}:[/info] {value}")

    def _print_system(self, message: str, style: str = "system") -> None:
        self.console.print(f"[{style}]ℹ️ {message}[/{style}]")


async def run_simple_chat(
    session_id: str,
    profile: str,
    agent: Any,
    stream: bool,
    user_context: dict[str, Any] | None,
) -> None:
    """Entry point to run the simple chat loop."""
    runner = SimpleChatRunner(
        session_id=session_id,
        profile=profile,
        agent=agent,
        stream=stream,
        user_context=user_context,
    )
    await runner.run()
