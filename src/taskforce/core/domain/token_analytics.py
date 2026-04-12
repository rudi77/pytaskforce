"""Token Analytics - Per-call and per-step token tracking and execution summary.

Domain models for fine-grained LLM token usage analysis.  The actual
collection happens in the infrastructure layer via a LiteLLM callback
(see ``infrastructure/llm/token_analytics_callback.py``).

Key features:
- Per-call token breakdown (prompt / completion / total / model / latency)
- Per-step aggregation (tokens per agent reasoning step)
- Per-model aggregation (token totals, call counts, average latency)
- Efficiency metrics (prompt/completion ratio, tokens per call)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class LLMCallRecord:
    """Token usage for a single LLM call.

    Attributes:
        model: Resolved model name used for this call.
        prompt_tokens: Input tokens reported by the provider.
        completion_tokens: Output tokens reported by the provider.
        total_tokens: Total tokens (prompt + completion).
        latency_ms: Request duration in milliseconds.
        tool_call_names: Names of tools the LLM chose to call (if any).
        timestamp: When this call was made.
        step_number: Agent reasoning step (None for planning/summarizing).
        phase: Execution phase (planning, reasoning, acting, reflecting, etc.).
    """

    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    tool_call_names: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    step_number: int | None = None
    phase: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "tool_call_names": self.tool_call_names,
            "timestamp": self.timestamp.isoformat(),
            "step_number": self.step_number,
            "phase": self.phase,
        }


@dataclass
class ModelTokenSummary:
    """Aggregated token usage per model.

    Attributes:
        model: Model name.
        total_prompt_tokens: Sum of prompt tokens.
        total_completion_tokens: Sum of completion tokens.
        total_tokens: Sum of total tokens.
        call_count: Number of LLM calls.
        total_latency_ms: Sum of latency across all calls.
    """

    model: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0
    total_latency_ms: int = 0

    @property
    def avg_tokens_per_call(self) -> float:
        """Average total tokens per call."""
        return self.total_tokens / self.call_count if self.call_count else 0.0

    @property
    def avg_latency_ms(self) -> float:
        """Average latency per call."""
        return self.total_latency_ms / self.call_count if self.call_count else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "model": self.model,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count,
            "total_latency_ms": self.total_latency_ms,
            "avg_tokens_per_call": round(self.avg_tokens_per_call, 1),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


@dataclass
class StepTokenSummary:
    """Aggregated token usage for a single agent step.

    Groups all LLM calls within one reasoning step (or a named phase
    like ``planning`` / ``summarizing`` for non-step calls).

    Attributes:
        step_number: Agent step (None for planning/summarizing/compression).
        phase: Execution phase name.
        prompt_tokens: Sum of prompt tokens in this step.
        completion_tokens: Sum of completion tokens in this step.
        total_tokens: Sum of total tokens in this step.
        latency_ms: Sum of LLM latency in this step.
        tool_call_names: Tool names invoked during this step.
        llm_calls: Number of LLM calls in this step.
    """

    step_number: int | None
    phase: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    tool_call_names: list[str] = field(default_factory=list)
    llm_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "step_number": self.step_number,
            "phase": self.phase,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "tool_call_names": self.tool_call_names,
            "llm_calls": self.llm_calls,
        }


@dataclass
class ExecutionTokenSummary:
    """Complete token analytics for one execution session.

    Attributes:
        calls: All LLM call records.
        model_breakdown: Aggregated usage per model.
        total_prompt_tokens: Sum of all prompt tokens.
        total_completion_tokens: Sum of all completion tokens.
        total_tokens: Sum of all tokens.
        total_llm_calls: Number of LLM calls.
        total_latency_ms: Sum of all latency.
        prompt_to_completion_ratio: Ratio of prompt to completion tokens.
    """

    calls: list[LLMCallRecord] = field(default_factory=list)
    model_breakdown: dict[str, ModelTokenSummary] = field(default_factory=dict)
    step_breakdown: list[StepTokenSummary] = field(default_factory=list)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_llm_calls: int = 0
    total_latency_ms: int = 0
    prompt_to_completion_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "calls": [c.to_dict() for c in self.calls],
            "model_breakdown": {k: v.to_dict() for k, v in self.model_breakdown.items()},
            "step_breakdown": [s.to_dict() for s in self.step_breakdown],
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_llm_calls": self.total_llm_calls,
            "total_latency_ms": self.total_latency_ms,
            "prompt_to_completion_ratio": round(self.prompt_to_completion_ratio, 2),
        }


def build_summary(calls: list[LLMCallRecord]) -> ExecutionTokenSummary:
    """Build an ExecutionTokenSummary from a list of call records.

    Pure function — no side effects.

    Args:
        calls: List of LLM call records.

    Returns:
        Aggregated summary with per-model breakdown and efficiency metrics.
    """
    summary = ExecutionTokenSummary(calls=list(calls))

    model_map: dict[str, ModelTokenSummary] = {}
    for record in calls:
        summary.total_prompt_tokens += record.prompt_tokens
        summary.total_completion_tokens += record.completion_tokens
        summary.total_tokens += record.total_tokens
        summary.total_latency_ms += record.latency_ms

        ms = model_map.get(record.model)
        if ms is None:
            ms = ModelTokenSummary(model=record.model)
            model_map[record.model] = ms
        ms.total_prompt_tokens += record.prompt_tokens
        ms.total_completion_tokens += record.completion_tokens
        ms.total_tokens += record.total_tokens
        ms.call_count += 1
        ms.total_latency_ms += record.latency_ms

    summary.model_breakdown = model_map
    summary.total_llm_calls = len(calls)

    if summary.total_completion_tokens > 0:
        summary.prompt_to_completion_ratio = (
            summary.total_prompt_tokens / summary.total_completion_tokens
        )

    # Per-step aggregation
    step_map: dict[tuple[int | None, str], StepTokenSummary] = {}
    for record in calls:
        key = (record.step_number, record.phase or "unknown")
        ss = step_map.get(key)
        if ss is None:
            ss = StepTokenSummary(step_number=record.step_number, phase=key[1])
            step_map[key] = ss
        ss.prompt_tokens += record.prompt_tokens
        ss.completion_tokens += record.completion_tokens
        ss.total_tokens += record.total_tokens
        ss.latency_ms += record.latency_ms
        ss.tool_call_names.extend(record.tool_call_names)
        ss.llm_calls += 1

    # Sort: None step_numbers first (planning, compression, summarizing),
    # then by step_number ascending.  Within same step_number, preserve
    # insertion order (dict is ordered in Python 3.7+).
    def _step_sort_key(s: StepTokenSummary) -> tuple[int, int]:
        if s.step_number is None:
            # Order named phases: planning < compression < summarizing < other
            phase_order = {"planning": 0, "compression": 1, "summarizing": 2}
            return (0, phase_order.get(s.phase, 99))
        return (1, s.step_number)

    summary.step_breakdown = sorted(step_map.values(), key=_step_sort_key)

    return summary
