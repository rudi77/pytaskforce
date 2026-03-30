"""Domain models for sub-agent orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4


def build_sub_agent_session_id(
    parent_session_id: str,
    label: str,
    suffix: str | None = None,
    *,
    deterministic: bool = True,
) -> str:
    """Build a hierarchical session ID for sub-agents.

    Args:
        parent_session_id: Parent agent's session ID.
        label: Specialist name or agent label.
        suffix: Explicit suffix override.
        deterministic: If True (default), use a stable suffix derived from
            the label so the same specialist reuses its session within
            the same parent conversation.  Set to False to get a unique
            session per spawn (legacy behavior).
    """
    safe_label = label.replace(" ", "_") if label else "generic"
    if suffix:
        suffix_value = suffix
    elif deterministic:
        suffix_value = "ctx"
    else:
        suffix_value = uuid4().hex[:8]
    return f"{parent_session_id}--sub_{safe_label}_{suffix_value}"


@dataclass(frozen=True)
class SubAgentSpec:
    """Specification for spawning a sub-agent."""

    mission: str
    parent_session_id: str
    specialist: str | None = None
    planning_strategy: str | None = None
    profile: str | None = None
    work_dir: str | None = None
    max_steps: int | None = None
    agent_definition: dict[str, Any] | None = None


@dataclass(frozen=True)
class SubAgentResult:
    """Result payload returned from a sub-agent execution."""

    session_id: str
    status: str
    success: bool
    final_message: str
    error: str | None = None
