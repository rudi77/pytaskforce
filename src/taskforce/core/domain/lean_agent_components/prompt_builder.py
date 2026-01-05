"""Prompt builder for Agent."""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.domain.context_builder import ContextBuilder
from taskforce.core.domain.context_policy import ContextPolicy
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
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        self._base_system_prompt = base_system_prompt
        self._planner = planner
        self._context_builder = context_builder
        self._context_policy = context_policy
        self._logger = logger

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
        """Build the plan status section for the system prompt."""
        if not self._planner:
            return ""

        plan_output = self._planner.get_plan_summary()
        if not plan_output or plan_output == "No active plan.":
            return ""

        plan_section = (
            "\n\n## CURRENT PLAN STATUS\n"
            "The following plan is currently active. "
            "Use it to guide your next steps.\n\n"
            f"{plan_output}"
        )
        self._logger.debug("plan_injected", plan_steps=plan_output.count("\n") + 1)
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

        Args:
            mission: Optional mission description for context pack
            state: Optional session state for context pack
            messages: Optional message history for context pack

        Returns:
            Context pack section string or empty string if no context pack.
        """
        context_pack = self._context_builder.build_context_pack(
            mission=mission, state=state, messages=messages
        )
        if not context_pack:
            return ""

        self._logger.debug(
            "context_pack_injected",
            pack_length=len(context_pack),
            policy_max=self._context_policy.max_total_chars,
        )
        return f"\n\n{context_pack}"
