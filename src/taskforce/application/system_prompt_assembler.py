"""
System Prompt Assembler
=======================

Builds system prompts for agents by composing a kernel prompt with optional
specialist instructions and tool descriptions.

Extracted from AgentFactory to enforce single-responsibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from taskforce.core.prompts import build_system_prompt, format_tools_description
from taskforce.core.prompts.autonomous_prompts import (
    BUTLER_SPECIALIST_PROMPT,
    CODING_SPECIALIST_PROMPT,
    LEAN_KERNEL_PROMPT,
    RAG_SPECIALIST_PROMPT,
    WIKI_SYSTEM_PROMPT,
)
from taskforce.core.utils.time import local_now

if TYPE_CHECKING:
    from taskforce.core.interfaces.tools import ToolProtocol


logger = structlog.get_logger(__name__)


# Maps specialist keys to their supplemental prompt text.
_SPECIALIST_PROMPTS: dict[str, str] = {
    "butler": BUTLER_SPECIALIST_PROMPT,
    "coding": CODING_SPECIALIST_PROMPT,
    "rag": RAG_SPECIALIST_PROMPT,
    "wiki": WIKI_SYSTEM_PROMPT,
}


class SystemPromptAssembler:
    """Compose system prompts from kernel, specialist, and tool descriptions.

    The assembler always starts from ``LEAN_KERNEL_PROMPT`` and layers on
    specialist instructions and a formatted tool description section.

    Usage::

        assembler = SystemPromptAssembler()
        prompt = assembler.assemble(specialist="coding", tools=my_tools)
    """

    def __init__(self) -> None:
        self._logger = logger.bind(component="prompt_assembler")

    def assemble(
        self,
        tools: list[ToolProtocol],
        *,
        specialist: str | None = None,
        custom_prompt: str | None = None,
        sub_agents: list[dict[str, str]] | None = None,
    ) -> str:
        """Build a complete system prompt.

        Exactly one of *specialist* or *custom_prompt* is expected.  If
        *custom_prompt* is provided, it is appended to the kernel prompt
        (LEAN_KERNEL_PROMPT).  Otherwise, the *specialist* key selects an
        additional instruction block.

        Args:
            tools: Available tools (used for the tool description section).
            specialist: Specialist key (``"coding"``, ``"rag"``, ``"wiki"``).
            custom_prompt: Free-form prompt to append to the kernel.
            sub_agents: Optional list of sub-agent dicts with ``specialist``
                and ``description`` keys.  When provided, the placeholder
                ``{{SUB_AGENTS_SECTION}}`` in the specialist prompt is
                replaced with a formatted list.

        Returns:
            Fully assembled system prompt string.
        """
        if custom_prompt:
            base_prompt = LEAN_KERNEL_PROMPT + "\n\n" + custom_prompt
        else:
            base_prompt = LEAN_KERNEL_PROMPT
            specialist_prompt = _SPECIALIST_PROMPTS.get(specialist or "")
            if specialist_prompt:
                base_prompt += "\n\n" + specialist_prompt

        # Inject dynamic sub-agent list if the prompt has the placeholder.
        # This works for both specialist prompts and custom prompts (e.g.
        # from butler role definitions that include {{SUB_AGENTS_SECTION}}).
        if sub_agents and "{{SUB_AGENTS_SECTION}}" in base_prompt:
            base_prompt = base_prompt.replace(
                "{{SUB_AGENTS_SECTION}}",
                _format_sub_agents_section(sub_agents),
            )
        elif "{{SUB_AGENTS_SECTION}}" in base_prompt:
            base_prompt = base_prompt.replace("{{SUB_AGENTS_SECTION}}", "")

        # Inject current local time so the agent can handle relative time
        # references (e.g. "in one hour") without asking the user.
        now = local_now()
        time_section = (
            f"\n\n## Current Time\n\n"
            f"Current local time: {now.strftime('%Y-%m-%dT%H:%M:%S%z')} "
            f"({now.strftime('%A, %d %B %Y, %H:%M %Z')})"
        )
        base_prompt += time_section

        # NOTE: Tool descriptions are NOT injected into the system prompt text.
        # Tools are already passed via the `tools` API parameter on each LLM call
        # (as OpenAI-format JSON schemas). Including them here as text would
        # double the token cost (~3,800 tokens) with no benefit.
        system_prompt = build_system_prompt(
            base_prompt=base_prompt,
            tools_description=None,
        )

        self._logger.debug(
            "system_prompt_assembled",
            specialist=specialist,
            has_custom_prompt=custom_prompt is not None,
            tools_count=len(tools),
            prompt_length=len(system_prompt),
            sub_agent_count=len(sub_agents) if sub_agents else 0,
        )

        return system_prompt


def _format_sub_agents_section(sub_agents: list[dict[str, str]]) -> str:
    """Format sub-agent definitions into a prompt section."""
    lines = ["Available sub-agents:"]
    for agent in sub_agents:
        specialist = agent.get("specialist", "unknown")
        description = agent.get("description", "")
        lines.append(f"- **{specialist}** (specialist: `{specialist}`): {description}")
    return "\n".join(lines)
