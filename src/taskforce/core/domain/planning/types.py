"""Dataclasses and constants for planning strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCallRequest:
    """Parsed tool call request."""

    tool_call_id: str
    tool_name: str
    tool_args: dict[str, Any]


@dataclass
class ResumeContext:
    """State restored when resuming from an ``ask_user`` pause."""

    messages: list[dict[str, Any]]
    step: int
    plan: list[str]
    plan_step_idx: int
    plan_iteration: int
    phase: str


class ToolCallStatus:
    """Status constants for tool call events."""

    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


DEFAULT_PLAN = [
    "Analyze the mission and identify required actions.",
    "Execute the required actions using available tools.",
    "Summarize the results and provide the final response.",
]
