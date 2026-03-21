"""Token Analytics - Per-step, per-phase, per-tool token tracking.

Provides fine-grained visibility into token consumption during agent
execution.  The ``TokenAnalyticsCollector`` is designed to be lightweight
and non-blocking; it records metrics synchronously and builds a summary
only when requested at the end of execution.

Key features:
- Per-step token breakdown (prompt / completion / total)
- Per-phase aggregation (planning / reasoning / acting / reflecting / summarizing)
- Per-tool context impact (how much context each tool's results add)
- Efficiency metrics (prompt/completion ratio, tokens per step, schema overhead)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


@dataclass
class StepTokenRecord:
    """Token usage for a single LLM call within one execution step.

    Attributes:
        step: Execution step number.
        phase: Execution phase hint (e.g. ``"reasoning"``, ``"planning"``).
        model: Actual model used (resolved from alias).
        prompt_tokens: Input tokens reported by the LLM provider.
        completion_tokens: Output tokens reported by the LLM provider.
        total_tokens: Total tokens (prompt + completion).
        message_count: Number of messages in history at this step.
        tool_schemas_count: Number of tool schemas sent with this call.
        context_tokens_estimate: Estimated tokens from the context pack.
        tool_calls: Names of tools called in this step.
        timestamp: When this LLM call was made.
    """

    step: int
    phase: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    message_count: int = 0
    tool_schemas_count: int = 0
    context_tokens_estimate: int = 0
    tool_calls: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "step": self.step,
            "phase": self.phase,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "message_count": self.message_count,
            "tool_schemas_count": self.tool_schemas_count,
            "context_tokens_estimate": self.context_tokens_estimate,
            "tool_calls": self.tool_calls,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PhaseTokenSummary:
    """Aggregated token usage per execution phase.

    Attributes:
        phase: Phase name (e.g. ``"reasoning"``).
        total_prompt_tokens: Sum of prompt tokens across all calls in this phase.
        total_completion_tokens: Sum of completion tokens.
        total_tokens: Sum of total tokens.
        call_count: Number of LLM calls in this phase.
    """

    phase: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0

    @property
    def avg_tokens_per_call(self) -> float:
        """Average total tokens per LLM call in this phase."""
        if self.call_count == 0:
            return 0.0
        return self.total_tokens / self.call_count

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "phase": self.phase,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count,
            "avg_tokens_per_call": round(self.avg_tokens_per_call, 1),
        }


@dataclass
class ToolTokenImpact:
    """Token impact of a specific tool's results on context size.

    Attributes:
        tool_name: Name of the tool.
        call_count: Number of times this tool was called.
        total_result_chars: Total raw result characters across all calls.
        total_context_chars: Total characters after truncation/preview.
        estimated_tokens_added: Estimated tokens added to context per call.
    """

    tool_name: str
    call_count: int = 0
    total_result_chars: int = 0
    total_context_chars: int = 0
    estimated_tokens_added: int = 0

    @property
    def avg_result_chars(self) -> float:
        """Average raw result size per call."""
        if self.call_count == 0:
            return 0.0
        return self.total_result_chars / self.call_count

    @property
    def compression_ratio(self) -> float:
        """Ratio of context chars to result chars (lower = more compressed)."""
        if self.total_result_chars == 0:
            return 0.0
        return self.total_context_chars / self.total_result_chars

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "tool_name": self.tool_name,
            "call_count": self.call_count,
            "total_result_chars": self.total_result_chars,
            "total_context_chars": self.total_context_chars,
            "estimated_tokens_added": self.estimated_tokens_added,
            "avg_result_chars": round(self.avg_result_chars, 1),
            "compression_ratio": round(self.compression_ratio, 3),
        }


@dataclass
class ExecutionTokenSummary:
    """Complete token analytics for one agent execution.

    Provides aggregated metrics, per-phase breakdown, per-tool impact,
    and efficiency scores for diagnosing token waste.

    Attributes:
        session_id: Session that was executed.
        steps: Per-step token records.
        phase_breakdown: Aggregated tokens by execution phase.
        tool_impact: Per-tool context impact.
        total_prompt_tokens: Sum of all prompt tokens.
        total_completion_tokens: Sum of all completion tokens.
        total_tokens: Sum of all tokens.
        total_llm_calls: Number of LLM calls made.
        total_steps: Number of execution steps.
        tokens_per_step_avg: Average tokens per step.
        prompt_to_completion_ratio: Ratio of prompt to completion tokens.
        compression_events: Number of times compression was triggered.
        most_expensive_step: Step with highest token usage.
        most_expensive_tool: Tool with highest context impact.
    """

    session_id: str
    steps: list[StepTokenRecord] = field(default_factory=list)
    phase_breakdown: dict[str, PhaseTokenSummary] = field(default_factory=dict)
    tool_impact: dict[str, ToolTokenImpact] = field(default_factory=dict)

    # Aggregates
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_llm_calls: int = 0
    total_steps: int = 0

    # Efficiency metrics
    tokens_per_step_avg: float = 0.0
    prompt_to_completion_ratio: float = 0.0
    compression_events: int = 0

    # Top consumers
    most_expensive_step: int | None = None
    most_expensive_tool: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for persistence and logging."""
        return {
            "session_id": self.session_id,
            "steps": [s.to_dict() for s in self.steps],
            "phase_breakdown": {k: v.to_dict() for k, v in self.phase_breakdown.items()},
            "tool_impact": {k: v.to_dict() for k, v in self.tool_impact.items()},
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_llm_calls": self.total_llm_calls,
            "total_steps": self.total_steps,
            "tokens_per_step_avg": round(self.tokens_per_step_avg, 1),
            "prompt_to_completion_ratio": round(self.prompt_to_completion_ratio, 2),
            "compression_events": self.compression_events,
            "most_expensive_step": self.most_expensive_step,
            "most_expensive_tool": self.most_expensive_tool,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionTokenSummary:
        """Deserialize from dictionary."""
        return cls(
            session_id=data.get("session_id", ""),
            total_prompt_tokens=data.get("total_prompt_tokens", 0),
            total_completion_tokens=data.get("total_completion_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            total_llm_calls=data.get("total_llm_calls", 0),
            total_steps=data.get("total_steps", 0),
            tokens_per_step_avg=data.get("tokens_per_step_avg", 0.0),
            prompt_to_completion_ratio=data.get("prompt_to_completion_ratio", 0.0),
            compression_events=data.get("compression_events", 0),
            most_expensive_step=data.get("most_expensive_step"),
            most_expensive_tool=data.get("most_expensive_tool", ""),
            phase_breakdown={
                k: PhaseTokenSummary(
                    phase=k,
                    **{
                        kk: vv for kk, vv in v.items() if kk not in ("phase", "avg_tokens_per_call")
                    },
                )
                for k, v in data.get("phase_breakdown", {}).items()
                if isinstance(v, dict)
            },
            tool_impact={
                k: ToolTokenImpact(
                    tool_name=k,
                    **{
                        kk: vv
                        for kk, vv in v.items()
                        if kk not in ("tool_name", "avg_result_chars", "compression_ratio")
                    },
                )
                for k, v in data.get("tool_impact", {}).items()
                if isinstance(v, dict)
            },
        )


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

# Heuristic constant matching HeuristicTokenEstimator
_CHARS_PER_TOKEN = 3.7


class TokenAnalyticsCollector:
    """Collects token metrics during agent execution.

    Designed to be lightweight and non-blocking.  Called from the
    ReAct loop after each LLM call and tool execution.

    Usage::

        collector = TokenAnalyticsCollector("session-123")
        # During execution:
        collector.record_llm_call(step=1, phase="reasoning", ...)
        collector.record_tool_result("file_read", result_chars=8000, context_chars=3000)
        # At end:
        summary = collector.build_summary()
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._steps: list[StepTokenRecord] = []
        self._tool_impacts: dict[str, ToolTokenImpact] = {}
        self._compression_events: int = 0
        self._current_step_tool_calls: list[str] = []

    @property
    def session_id(self) -> str:
        """Return the session ID this collector is tracking."""
        return self._session_id

    def record_llm_call(
        self,
        *,
        step: int,
        phase: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        message_count: int = 0,
        tool_schemas_count: int = 0,
        context_tokens_estimate: int = 0,
    ) -> None:
        """Record token usage for one LLM call.

        Args:
            step: Execution step number.
            phase: Phase hint (e.g. ``"reasoning"``).
            model: Resolved model name.
            prompt_tokens: Input tokens from LLM response.
            completion_tokens: Output tokens from LLM response.
            total_tokens: Total tokens from LLM response.
            message_count: Number of messages sent.
            tool_schemas_count: Number of tool schemas sent.
            context_tokens_estimate: Estimated tokens from context pack.
        """
        record = StepTokenRecord(
            step=step,
            phase=phase,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            message_count=message_count,
            tool_schemas_count=tool_schemas_count,
            context_tokens_estimate=context_tokens_estimate,
            tool_calls=list(self._current_step_tool_calls),
        )
        self._steps.append(record)
        self._current_step_tool_calls = []

    def record_tool_call(self, tool_name: str) -> None:
        """Record that a tool was called in the current step.

        Args:
            tool_name: Name of the tool that was called.
        """
        self._current_step_tool_calls.append(tool_name)

    def record_tool_result(
        self,
        tool_name: str,
        result_chars: int,
        context_chars: int,
    ) -> None:
        """Record the token impact of a tool result.

        Args:
            tool_name: Name of the tool.
            result_chars: Raw result size in characters.
            context_chars: Size after truncation/preview (what goes into context).
        """
        impact = self._tool_impacts.get(tool_name)
        if impact is None:
            impact = ToolTokenImpact(tool_name=tool_name)
            self._tool_impacts[tool_name] = impact

        impact.call_count += 1
        impact.total_result_chars += result_chars
        impact.total_context_chars += context_chars
        impact.estimated_tokens_added += int(context_chars / _CHARS_PER_TOKEN)

    def record_compression(self) -> None:
        """Record that message compression was triggered."""
        self._compression_events += 1

    def build_summary(self) -> ExecutionTokenSummary:
        """Build the final analytics summary.

        Should be called once at the end of execution.

        Returns:
            Complete ``ExecutionTokenSummary`` with all aggregations computed.
        """
        summary = ExecutionTokenSummary(session_id=self._session_id)
        summary.steps = list(self._steps)
        summary.tool_impact = dict(self._tool_impacts)
        summary.compression_events = self._compression_events

        # Aggregate totals
        for record in self._steps:
            summary.total_prompt_tokens += record.prompt_tokens
            summary.total_completion_tokens += record.completion_tokens
            summary.total_tokens += record.total_tokens

        summary.total_llm_calls = len(self._steps)

        # Unique steps
        step_numbers = {r.step for r in self._steps}
        summary.total_steps = len(step_numbers)

        # Per-phase breakdown
        phase_map: dict[str, PhaseTokenSummary] = {}
        for record in self._steps:
            phase = record.phase
            if phase not in phase_map:
                phase_map[phase] = PhaseTokenSummary(phase=phase)
            ps = phase_map[phase]
            ps.total_prompt_tokens += record.prompt_tokens
            ps.total_completion_tokens += record.completion_tokens
            ps.total_tokens += record.total_tokens
            ps.call_count += 1
        summary.phase_breakdown = phase_map

        # Efficiency metrics
        if summary.total_steps > 0:
            summary.tokens_per_step_avg = summary.total_tokens / summary.total_steps

        if summary.total_completion_tokens > 0:
            summary.prompt_to_completion_ratio = (
                summary.total_prompt_tokens / summary.total_completion_tokens
            )

        # Most expensive step
        if self._steps:
            most_expensive = max(self._steps, key=lambda r: r.total_tokens)
            summary.most_expensive_step = most_expensive.step

        # Most expensive tool (by estimated tokens added)
        if self._tool_impacts:
            most_expensive_tool = max(
                self._tool_impacts.values(),
                key=lambda t: t.estimated_tokens_added,
            )
            summary.most_expensive_tool = most_expensive_tool.tool_name

        return summary
