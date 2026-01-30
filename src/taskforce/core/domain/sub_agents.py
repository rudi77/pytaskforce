"""Domain models for sub-agent orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4


def build_sub_agent_session_id(
    parent_session_id: str,
    label: str,
    suffix: str | None = None,
) -> str:
    """Build a hierarchical session ID for sub-agents."""
    safe_label = label.replace(" ", "_") if label else "generic"
    suffix_value = suffix or uuid4().hex[:8]
    return f"{parent_session_id}:sub_{safe_label}_{suffix_value}"


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
