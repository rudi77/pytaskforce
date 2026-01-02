"""System prompts and templates.

This module provides system prompts for different agent types:
- Autonomous prompts (Kernel + Specialist profiles)
- Legacy prompts (generic, rag, text2sql, wiki)
- Dynamic prompt building with tool injection
"""

from taskforce.core.prompts.autonomous_prompts import (
    CODING_SPECIALIST_PROMPT,
    GENERAL_AUTONOMOUS_KERNEL_PROMPT,
    RAG_SPECIALIST_PROMPT,
)
from taskforce.core.prompts.generic_system_prompt import GENERIC_SYSTEM_PROMPT
from taskforce.core.prompts.prompt_builder import (
    build_system_prompt,
    format_tools_description,
)

__all__ = [
    "GENERAL_AUTONOMOUS_KERNEL_PROMPT",
    "CODING_SPECIALIST_PROMPT",
    "RAG_SPECIALIST_PROMPT",
    "GENERIC_SYSTEM_PROMPT",
    "build_system_prompt",
    "format_tools_description",
]

