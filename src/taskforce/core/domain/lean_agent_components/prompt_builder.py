"""Prompt builder for Agent."""

from __future__ import annotations

from typing import Any

from taskforce.core.domain.context_builder import ContextBuilder
from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.tools.planner_tool import PlannerTool


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
