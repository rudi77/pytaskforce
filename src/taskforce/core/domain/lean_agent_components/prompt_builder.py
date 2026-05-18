"""Prompt builder for Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from taskforce.core.domain.context_builder import ContextBuilder
from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.domain.planning.deliverable_check import (
    build_checklist_section,
    extract_checklist_bullets,
)
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.tools.planner_tool import PlannerTool

# Don't blow the budget on a massive CLAUDE.md. Mirrors Claude Code's own
# behaviour (truncate-with-marker after ~20k chars).
_CLAUDE_MD_MAX_CHARS = 20_000


class LeanPromptBuilder:
    """
    Build Agent system prompts with plan and context sections.

    Keeps prompt composition logic isolated from the execution loop.
    """

    def __init__(
        self,
        *,
        base_system_prompt: str,
        planner: PlannerTool | None,
        context_builder: ContextBuilder,
        context_policy: ContextPolicy,
        logger: LoggerProtocol,
    ) -> None:
        self._base_system_prompt = base_system_prompt
        self._planner = planner
        self._context_builder = context_builder
        self._context_policy = context_policy
        self._logger = logger

        # Section-level caches for prompt building
        self._cached_plan_section: str | None = None
        self._cached_plan_hash: int | None = None
        self._cached_context_section: str | None = None
        self._cached_context_key: tuple[int, int] | None = None
        # Workspace section cache. Key is (root, claude_md_mtime_ns)
        # so the section invalidates when the user switches workspace
        # OR edits CLAUDE.md without restarting the agent.
        self._cached_workspace_section: str | None = None
        self._cached_workspace_key: tuple[str | None, int | None] | None = None

    def build_system_prompt(
        self,
        *,
        mission: str | None = None,
        state: dict[str, Any] | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Build system prompt with dynamic plan and context pack injection.

        Args:
            mission: Optional mission description for context pack
            state: Optional session state for context pack
            messages: Optional message history for context pack

        Returns:
            Complete system prompt with plan context and context pack.
        """
        prompt = self._base_system_prompt
        workspace_section = self._build_workspace_section()
        if workspace_section:
            prompt += workspace_section

        # Mandatory-deliverables checklist (#406). When the mission
        # contains an enumerated list of bolded bullets (PinchBench
        # rubrics use 4–7), reify it as a checkbox section the agent
        # can tick off — prevents partial completions that skip 1–2
        # named items.
        checklist_section = self._build_checklist_section(mission)
        if checklist_section:
            prompt += checklist_section

        plan_section = self._build_plan_section()
        if plan_section:
            prompt += plan_section

        context_section = self._build_context_pack_section(
            mission=mission,
            state=state,
            messages=messages,
        )
        if context_section:
            prompt += context_section

        return prompt

    def _build_checklist_section(self, mission: str | None) -> str:
        """Extract enumerated bullets from the mission into a checklist.

        Returns the empty string when the mission has fewer than 2
        bolded bullet titles (i.e. is not structured as a rubric).
        Cheap regex; safe to call on every prompt rebuild.
        """
        bullets = extract_checklist_bullets(mission)
        if not bullets:
            return ""
        self._logger.debug("checklist_section_injected", item_count=len(bullets))
        return build_checklist_section(bullets)

    def _build_workspace_section(self) -> str:
        """Build the workspace + project-guidance section.

        Consulted on every prompt rebuild because the workspace context
        is set per-mission via ``workspace_scope`` in the executor; the
        same agent instance can serve missions across different projects
        if the conversation is reassigned. Cached by ``(root, mtime)``
        so steady-state per-mission cost is a tiny `os.stat` call.

        Without a workspace (no project linked, or single-tenant runs
        without ``work_dir``) this returns an empty string and the
        prompt looks bit-for-bit like before #273.
        """
        # Lazy import to avoid pulling the workspace ContextVar into
        # tests that don't use it (and to keep core/domain free of
        # tool-layer imports).
        from taskforce.core.interfaces.workspace import get_workspace_context

        ws = get_workspace_context()
        if ws is None:
            self._cached_workspace_section = ""
            self._cached_workspace_key = None
            return ""

        try:
            root = Path(ws.root())
        except Exception:  # noqa: BLE001 — defensive: never break prompt build
            return ""

        claude_md = root / "CLAUDE.md"
        try:
            md_stat = claude_md.stat()
            mtime_ns: int | None = md_stat.st_mtime_ns
        except OSError:
            mtime_ns = None

        key = (str(root), mtime_ns)
        if self._cached_workspace_key == key and self._cached_workspace_section is not None:
            return self._cached_workspace_section

        parts: list[str] = [
            "\n\n## WORKSPACE\n",
            f"You are working inside the project directory:\n  `{root}`\n",
            "Relative paths passed to file/shell/python/edit tools resolve under "
            "this root, and absolute paths outside it are rejected. Treat this "
            "directory as your default workspace — do NOT claim you have no "
            "filesystem access; use the file/shell/edit tools to explore and "
            "modify it.",
        ]

        if mtime_ns is not None:
            try:
                content = claude_md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = ""
            content = content.strip()
            if content:
                if len(content) > _CLAUDE_MD_MAX_CHARS:
                    truncated = content[:_CLAUDE_MD_MAX_CHARS]
                    content = (
                        f"{truncated}\n\n"
                        f"[…truncated, {len(content) - _CLAUDE_MD_MAX_CHARS} chars omitted. "
                        "Read CLAUDE.md with file_read for the full contents.]"
                    )
                parts.append(
                    "\n\n### Project guidance (CLAUDE.md)\n\n"
                    "The project ships a CLAUDE.md file. Follow these "
                    "instructions for all work in this workspace:\n\n"
                    f"{content}"
                )
                self._logger.debug(
                    "workspace_claude_md_injected",
                    root=str(root),
                    chars=len(content),
                )

        section = "".join(parts)
        self._cached_workspace_section = section
        self._cached_workspace_key = key
        return section

    def _build_plan_section(self) -> str:
        """Build the plan status section for the system prompt.

        Caches the result keyed on the hash of the plan summary string.
        The cache invalidates when the plan content changes (e.g., steps
        are marked done).
        """
        if not self._planner:
            return ""

        plan_output = self._planner.get_plan_summary()
        if not plan_output or plan_output == "No active plan.":
            self._cached_plan_section = ""
            self._cached_plan_hash = None
            return ""

        plan_hash = hash(plan_output)
        if self._cached_plan_hash == plan_hash and self._cached_plan_section is not None:
            return self._cached_plan_section

        plan_section = (
            "\n\n## CURRENT PLAN STATUS\n"
            "The following plan is currently active. "
            "Use it to guide your next steps.\n\n"
            f"{plan_output}"
        )
        self._logger.debug("plan_injected", plan_steps=plan_output.count("\n") + 1)
        self._cached_plan_section = plan_section
        self._cached_plan_hash = plan_hash
        return plan_section

    def _build_context_pack_section(
        self,
        *,
        mission: str | None,
        state: dict[str, Any] | None,
        messages: list[dict[str, Any]] | None,
    ) -> str:
        """
        Build the context pack section for the system prompt.

        Caches the result keyed on message count and the identity of the
        last tool message content. The cache invalidates when new tool
        results are added or messages are compressed.

        Args:
            mission: Optional mission description for context pack
            state: Optional session state for context pack
            messages: Optional message history for context pack

        Returns:
            Context pack section string or empty string if no context pack.
        """
        # Compute a lightweight cache key from message shape
        msg_list = messages or []
        last_tool_content_id = 0
        for msg in reversed(msg_list):
            if msg.get("role") == "tool":
                last_tool_content_id = id(msg.get("content"))
                break
        context_key = (len(msg_list), last_tool_content_id)

        if self._cached_context_key == context_key and self._cached_context_section is not None:
            return self._cached_context_section

        visible_window = self._context_policy.deduplicate_visible_window or None
        context_pack = self._context_builder.build_context_pack(
            mission=mission,
            state=state,
            messages=messages,
            visible_window_size=visible_window,
        )
        if not context_pack:
            self._cached_context_section = ""
            self._cached_context_key = context_key
            return ""

        self._logger.debug(
            "context_pack_injected",
            pack_length=len(context_pack),
            policy_max=self._context_policy.max_total_chars,
        )
        result = f"\n\n{context_pack}"
        self._cached_context_section = result
        self._cached_context_key = context_key
        return result
