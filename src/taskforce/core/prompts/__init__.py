"""System prompts and templates.

This module provides system prompts for different agent types:
- Autonomous prompts (Kernel + Specialist profiles)
- Legacy prompts (generic, rag, text2sql, wiki)
- Dynamic prompt building with tool and skill injection
"""

from taskforce.core.prompts.autonomous_prompts import (
    CODING_SPECIALIST_PROMPT,
    GENERAL_AUTONOMOUS_KERNEL_PROMPT,
    RAG_SPECIALIST_PROMPT,
)
from taskforce.core.prompts.prompt_builder import (
    build_system_prompt,
    format_active_skills_instructions,
    format_skills_metadata,
    format_tools_description,
)

__all__ = [
    "GENERAL_AUTONOMOUS_KERNEL_PROMPT",
    "CODING_SPECIALIST_PROMPT",
    "RAG_SPECIALIST_PROMPT",
    "build_system_prompt",
    "format_tools_description",
    "format_skills_metadata",
    "format_active_skills_instructions",
]

