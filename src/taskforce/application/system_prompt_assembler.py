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
    CODING_SPECIALIST_PROMPT,
    LEAN_KERNEL_PROMPT,
    RAG_SPECIALIST_PROMPT,
    WIKI_SYSTEM_PROMPT,
)

if TYPE_CHECKING:
    from taskforce.core.interfaces.tools import ToolProtocol


logger = structlog.get_logger(__name__)


# Maps specialist keys to their supplemental prompt text.
_SPECIALIST_PROMPTS: dict[str, str] = {
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

        tools_description = format_tools_description(tools) if tools else ""
        system_prompt = build_system_prompt(
            base_prompt=base_prompt,
            tools_description=tools_description,
        )

        self._logger.debug(
            "system_prompt_assembled",
            specialist=specialist,
            has_custom_prompt=custom_prompt is not None,
            tools_count=len(tools),
            prompt_length=len(system_prompt),
        )

        return system_prompt
