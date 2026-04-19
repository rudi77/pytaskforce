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


@dataclass
class ExecutionInit:
    """Result of the shared initialize-or-resume phase of a planning strategy.

    ``resume`` is ``None`` for a fresh execution; otherwise it carries the
    step/plan/iteration/phase values restored from a paused session. ``plan``
    holds the plan to execute (``DEFAULT_PLAN`` when no plan was generated,
    the resumed plan when resuming, or the freshly generated plan).
    """

    state: dict[str, Any]
    resume: ResumeContext | None
    plan: list[str]


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
