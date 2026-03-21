"""Tests for TokenAnalytics domain models and collector."""

from __future__ import annotations

from datetime import UTC, datetime

from taskforce.core.domain.token_analytics import (
    ExecutionTokenSummary,
    PhaseTokenSummary,
    StepTokenRecord,
    TokenAnalyticsCollector,
    ToolTokenImpact,
)


# ---------------------------------------------------------------------------
# StepTokenRecord
# ---------------------------------------------------------------------------


class TestStepTokenRecord:
    def test_creation_defaults(self):
        record = StepTokenRecord(step=1, phase="reasoning", model="gpt-4o")
        assert record.step == 1
        assert record.phase == "reasoning"
        assert record.model == "gpt-4o"
        assert record.prompt_tokens == 0
        assert record.completion_tokens == 0
        assert record.total_tokens == 0
        assert record.tool_calls == []

    def test_to_dict(self):
        record = StepTokenRecord(
            step=3,
            phase="planning",
            model="claude-3",
            prompt_tokens=1000,
            completion_tokens=200,
            total_tokens=1200,
            message_count=15,
            tool_schemas_count=19,
            tool_calls=["file_read", "grep"],
        )
        d = record.to_dict()
        assert d["step"] == 3
        assert d["phase"] == "planning"
        assert d["prompt_tokens"] == 1000
        assert d["tool_calls"] == ["file_read", "grep"]
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# PhaseTokenSummary
# ---------------------------------------------------------------------------


class TestPhaseTokenSummary:
    def test_avg_tokens_per_call_zero_calls(self):
        summary = PhaseTokenSummary(phase="reasoning")
        assert summary.avg_tokens_per_call == 0.0

    def test_avg_tokens_per_call(self):
        summary = PhaseTokenSummary(
            phase="reasoning",
            total_tokens=3000,
            call_count=3,
        )
        assert summary.avg_tokens_per_call == 1000.0

    def test_to_dict(self):
        summary = PhaseTokenSummary(
            phase="planning",
            total_prompt_tokens=800,
            total_completion_tokens=200,
            total_tokens=1000,
            call_count=2,
        )
        d = summary.to_dict()
        assert d["phase"] == "planning"
        assert d["avg_tokens_per_call"] == 500.0


# ---------------------------------------------------------------------------
# ToolTokenImpact
# ---------------------------------------------------------------------------


class TestToolTokenImpact:
    def test_avg_result_chars_zero_calls(self):
        impact = ToolTokenImpact(tool_name="file_read")
        assert impact.avg_result_chars == 0.0

    def test_compression_ratio(self):
        impact = ToolTokenImpact(
            tool_name="file_read",
            call_count=2,
            total_result_chars=10000,
            total_context_chars=3000,
        )
        assert impact.compression_ratio == 0.3

    def test_compression_ratio_zero_result(self):
        impact = ToolTokenImpact(tool_name="file_read")
        assert impact.compression_ratio == 0.0

    def test_to_dict(self):
        impact = ToolTokenImpact(
            tool_name="grep",
            call_count=5,
            total_result_chars=25000,
            total_context_chars=5000,
            estimated_tokens_added=1350,
        )
        d = impact.to_dict()
        assert d["tool_name"] == "grep"
        assert d["avg_result_chars"] == 5000.0
        assert d["compression_ratio"] == 0.2


# ---------------------------------------------------------------------------
# TokenAnalyticsCollector
# ---------------------------------------------------------------------------


class TestTokenAnalyticsCollector:
    def test_empty_collector(self):
        collector = TokenAnalyticsCollector("sess-1")
        summary = collector.build_summary()
        assert summary.session_id == "sess-1"
        assert summary.total_tokens == 0
        assert summary.total_llm_calls == 0
        assert summary.total_steps == 0
        assert summary.most_expensive_step is None
        assert summary.most_expensive_tool == ""

    def test_record_llm_call(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_llm_call(
            step=1,
            phase="reasoning",
            model="gpt-4o",
            prompt_tokens=500,
            completion_tokens=100,
            total_tokens=600,
            message_count=5,
            tool_schemas_count=19,
        )
        summary = collector.build_summary()
        assert summary.total_tokens == 600
        assert summary.total_prompt_tokens == 500
        assert summary.total_completion_tokens == 100
        assert summary.total_llm_calls == 1
        assert summary.total_steps == 1
        assert len(summary.steps) == 1
        assert summary.steps[0].phase == "reasoning"

    def test_multiple_steps(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_llm_call(
            step=1, phase="reasoning", model="gpt-4o",
            prompt_tokens=500, completion_tokens=100, total_tokens=600,
        )
        collector.record_llm_call(
            step=2, phase="reasoning", model="gpt-4o",
            prompt_tokens=800, completion_tokens=150, total_tokens=950,
        )
        collector.record_llm_call(
            step=3, phase="summarizing", model="gpt-4o-mini",
            prompt_tokens=300, completion_tokens=200, total_tokens=500,
        )
        summary = collector.build_summary()
        assert summary.total_tokens == 2050
        assert summary.total_llm_calls == 3
        assert summary.total_steps == 3

    def test_phase_breakdown(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_llm_call(
            step=1, phase="reasoning", model="m",
            prompt_tokens=1000, completion_tokens=200, total_tokens=1200,
        )
        collector.record_llm_call(
            step=2, phase="reasoning", model="m",
            prompt_tokens=1500, completion_tokens=300, total_tokens=1800,
        )
        collector.record_llm_call(
            step=3, phase="summarizing", model="m",
            prompt_tokens=500, completion_tokens=400, total_tokens=900,
        )
        summary = collector.build_summary()
        assert "reasoning" in summary.phase_breakdown
        assert "summarizing" in summary.phase_breakdown
        reasoning = summary.phase_breakdown["reasoning"]
        assert reasoning.total_tokens == 3000
        assert reasoning.call_count == 2
        summarizing = summary.phase_breakdown["summarizing"]
        assert summarizing.total_tokens == 900
        assert summarizing.call_count == 1

    def test_most_expensive_step(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_llm_call(
            step=1, phase="r", model="m",
            prompt_tokens=100, completion_tokens=50, total_tokens=150,
        )
        collector.record_llm_call(
            step=2, phase="r", model="m",
            prompt_tokens=5000, completion_tokens=500, total_tokens=5500,
        )
        collector.record_llm_call(
            step=3, phase="r", model="m",
            prompt_tokens=200, completion_tokens=80, total_tokens=280,
        )
        summary = collector.build_summary()
        assert summary.most_expensive_step == 2

    def test_prompt_to_completion_ratio(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_llm_call(
            step=1, phase="r", model="m",
            prompt_tokens=4000, completion_tokens=500, total_tokens=4500,
        )
        summary = collector.build_summary()
        assert summary.prompt_to_completion_ratio == 8.0

    def test_prompt_to_completion_ratio_zero_completion(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_llm_call(
            step=1, phase="r", model="m",
            prompt_tokens=1000, completion_tokens=0, total_tokens=1000,
        )
        summary = collector.build_summary()
        assert summary.prompt_to_completion_ratio == 0.0

    def test_tokens_per_step_avg(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_llm_call(
            step=1, phase="r", model="m",
            prompt_tokens=0, completion_tokens=0, total_tokens=1000,
        )
        collector.record_llm_call(
            step=2, phase="r", model="m",
            prompt_tokens=0, completion_tokens=0, total_tokens=3000,
        )
        summary = collector.build_summary()
        assert summary.tokens_per_step_avg == 2000.0

    def test_record_tool_result(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_tool_result("file_read", result_chars=8000, context_chars=3000)
        collector.record_tool_result("file_read", result_chars=6000, context_chars=2000)
        collector.record_tool_result("grep", result_chars=2000, context_chars=2000)

        summary = collector.build_summary()
        assert "file_read" in summary.tool_impact
        assert "grep" in summary.tool_impact

        fr = summary.tool_impact["file_read"]
        assert fr.call_count == 2
        assert fr.total_result_chars == 14000
        assert fr.total_context_chars == 5000
        assert fr.avg_result_chars == 7000.0

    def test_most_expensive_tool(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_tool_result("file_read", result_chars=8000, context_chars=8000)
        collector.record_tool_result("grep", result_chars=200, context_chars=200)
        summary = collector.build_summary()
        assert summary.most_expensive_tool == "file_read"

    def test_record_compression(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_compression()
        collector.record_compression()
        summary = collector.build_summary()
        assert summary.compression_events == 2

    def test_record_tool_call_attached_to_step(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_tool_call("file_read")
        collector.record_tool_call("grep")
        collector.record_llm_call(
            step=1, phase="r", model="m",
            prompt_tokens=100, completion_tokens=50, total_tokens=150,
        )
        summary = collector.build_summary()
        assert summary.steps[0].tool_calls == ["file_read", "grep"]

    def test_tool_calls_reset_after_llm_call(self):
        collector = TokenAnalyticsCollector("sess-1")
        collector.record_tool_call("file_read")
        collector.record_llm_call(
            step=1, phase="r", model="m",
            prompt_tokens=100, completion_tokens=50, total_tokens=150,
        )
        collector.record_tool_call("grep")
        collector.record_llm_call(
            step=2, phase="r", model="m",
            prompt_tokens=100, completion_tokens=50, total_tokens=150,
        )
        summary = collector.build_summary()
        assert summary.steps[0].tool_calls == ["file_read"]
        assert summary.steps[1].tool_calls == ["grep"]

    def test_session_id_property(self):
        collector = TokenAnalyticsCollector("sess-42")
        assert collector.session_id == "sess-42"


# ---------------------------------------------------------------------------
# ExecutionTokenSummary serialization
# ---------------------------------------------------------------------------


class TestExecutionTokenSummary:
    def test_to_dict(self):
        summary = ExecutionTokenSummary(
            session_id="sess-1",
            total_tokens=5000,
            total_prompt_tokens=4000,
            total_completion_tokens=1000,
            total_llm_calls=3,
            total_steps=3,
            tokens_per_step_avg=1666.7,
            prompt_to_completion_ratio=4.0,
            compression_events=1,
            most_expensive_step=2,
            most_expensive_tool="file_read",
        )
        d = summary.to_dict()
        assert d["session_id"] == "sess-1"
        assert d["total_tokens"] == 5000
        assert d["prompt_to_completion_ratio"] == 4.0
        assert d["most_expensive_step"] == 2

    def test_from_dict_roundtrip(self):
        collector = TokenAnalyticsCollector("sess-rt")
        collector.record_llm_call(
            step=1, phase="reasoning", model="gpt-4o",
            prompt_tokens=1000, completion_tokens=200, total_tokens=1200,
        )
        collector.record_tool_result("grep", result_chars=5000, context_chars=2000)
        collector.record_compression()
        original = collector.build_summary()

        d = original.to_dict()
        restored = ExecutionTokenSummary.from_dict(d)
        assert restored.session_id == "sess-rt"
        assert restored.total_tokens == 1200
        assert restored.compression_events == 1
        assert "reasoning" in restored.phase_breakdown
        assert "grep" in restored.tool_impact

    def test_from_dict_empty(self):
        summary = ExecutionTokenSummary.from_dict({})
        assert summary.session_id == ""
        assert summary.total_tokens == 0
