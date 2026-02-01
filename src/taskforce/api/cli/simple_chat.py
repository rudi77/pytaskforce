"""Simple REPL-style streaming chat runner for Taskforce."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.markdown import Markdown

from taskforce.api.cli.output_formatter import TASKFORCE_THEME
from taskforce.application.agent_registry import AgentRegistry
from taskforce.application.executor import AgentExecutor, ProgressUpdate
from taskforce.application.factory import AgentFactory
from taskforce.application.slash_command_registry import SlashCommandRegistry
from taskforce.application.skill_service import get_skill_service
from taskforce.core.domain.agent_definition import AgentSource
from taskforce.core.domain.enums import EventType, MessageRole, TaskStatus
from taskforce.core.interfaces.slash_commands import (
    CommandType,
    SlashCommandDefinition,
)


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
        self.command_registry = SlashCommandRegistry()
        self.agent_registry = AgentRegistry()
        self.total_tokens = 0
        self.plan_state = PlanState(steps=[], text=None)
        self._last_event_signature: tuple[str, str] | None = None

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
        """Read input from the user without blocking the event loop."""
        prompt = "[user]👤 You >[/user] "
        try:
            value = await asyncio.to_thread(self.console.input, prompt)
        except (EOFError, KeyboardInterrupt):
            return "/quit"
        return value.strip()

    async def _handle_command(self, command: str) -> bool:
        """Handle slash commands. Returns True if we should exit."""
        parts = command.lstrip("/").split(maxsplit=1)
        cmd_name = parts[0].lower()
        arguments = parts[1] if len(parts) > 1 else ""

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
        elif cmd_name == "commands":
            self._list_custom_commands()
        elif cmd_name == "plugins":
            self._list_plugins()
        elif cmd_name == "skills":
            self._list_skills()
        else:
            command_def, args = self.command_registry.resolve_command(command)
            if command_def:
                await self._execute_custom_command(command_def, args)
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
            "- /commands\n"
            "- /plugins\n"
            "- /skills\n"
            "- /debug\n"
            "- /quit or /exit\n"
        )
        self.console.print(Markdown(help_text))

    def _list_custom_commands(self) -> None:
        """List custom commands."""
        commands = self.command_registry.list_commands(include_builtin=False)
        if not commands:
            self._print_system("No custom commands found.", style="info")
            self._print_system(
                "Add .md files to .taskforce/commands/ or ~/.taskforce/commands/",
                style="info",
            )
            return

        lines = ["**Custom Commands:**"]
        for cmd in commands:
            source_tag = f"[{cmd['source']}]" if cmd["source"] != "builtin" else ""
            lines.append(f"- /{cmd['name']} — {cmd['description']} {source_tag}")
        self.console.print(Markdown("\n".join(lines)))

    def _list_plugins(self) -> None:
        """List available plugin agents."""
        plugins = [
            agent
            for agent in self.agent_registry.list_all(sources=[AgentSource.PLUGIN])
        ]
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
        """List available skills."""
        skill_manager = getattr(self.agent, "skill_manager", None)
        if skill_manager and skill_manager.has_skills:
            active = (
                f" (active: {skill_manager.active_skill_name})"
                if skill_manager.active_skill_name
                else ""
            )
            lines = [f"**Skills (plugin + global){active}:**"]
            for skill_name in skill_manager.list_skills():
                lines.append(f"- {skill_name}")
            self.console.print(Markdown("\n".join(lines)))
            return

        skill_service = get_skill_service()
        skills = skill_service.list_skills()
        if not skills:
            self._print_system("No skills found.", style="info")
            self._print_system(
                "Add skills under .taskforce/skills/ or ~/.taskforce/skills/.",
                style="info",
            )
            return

        lines = ["**Skills:**"]
        for skill_name in skills:
            lines.append(f"- {skill_name}")
        self.console.print(Markdown("\n".join(lines)))

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

    async def _execute_custom_command(
        self,
        command_def: SlashCommandDefinition,
        arguments: str,
    ) -> None:
        """Execute a custom slash command."""
        if command_def.command_type == CommandType.PROMPT:
            prompt = self.command_registry.prepare_prompt(command_def, arguments)
            self._print_system(f"Executing /{command_def.name}...", style="info")
            await self._handle_chat_message(prompt)
            return

        if command_def.command_type == CommandType.AGENT:
            self._print_system(
                f"Switching to agent: {command_def.name} (/{command_def.name})",
                style="info",
            )
            agent = await self.command_registry.create_agent_for_command(
                command_def,
                self.profile,
            )
            self.agent = agent
            prompt = self.command_registry.prepare_prompt(command_def, arguments)
            await self._handle_chat_message(prompt)

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
                params = update.details.get("params", {})
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
                paused_question = update.details
                question = update.details.get("question", "")
                missing = update.details.get("missing", [])
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
