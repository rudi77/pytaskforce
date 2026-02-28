"""Tests for experience domain models."""

from datetime import UTC, datetime

from taskforce.core.domain.enums import ConsolidationStrategy
from taskforce.core.domain.experience import (
    ConsolidatedMemoryKind,
    ConsolidationResult,
    ExperienceEvent,
    SessionExperience,
    ToolCallExperience,
    truncate_output,
)


class TestTruncateOutput:
    def test_short_text_unchanged(self):
        assert truncate_output("hello") == "hello"

    def test_exact_limit_unchanged(self):
        text = "x" * 500
        assert truncate_output(text) == text

    def test_over_limit_truncated(self):
        text = "x" * 600
        result = truncate_output(text)
        assert len(result) == 503  # 500 + "..."
        assert result.endswith("...")


class TestExperienceEvent:
    def test_round_trip(self):
        now = datetime.now(UTC)
        event = ExperienceEvent(
            timestamp=now,
            event_type="tool_call",
            data={"tool": "python"},
            step=3,
        )
        d = event.to_dict()
        restored = ExperienceEvent.from_dict(d)
        assert restored.event_type == "tool_call"
        assert restored.step == 3
        assert restored.data == {"tool": "python"}


class TestToolCallExperience:
    def test_round_trip(self):
        tc = ToolCallExperience(
            tool_name="file_read",
            arguments={"path": "test.py"},
            success=True,
            output_summary="contents...",
            duration_ms=150,
        )
        d = tc.to_dict()
        restored = ToolCallExperience.from_dict(d)
        assert restored.tool_name == "file_read"
        assert restored.success is True
        assert restored.duration_ms == 150
        assert "error" not in d

    def test_with_error(self):
        tc = ToolCallExperience(
            tool_name="shell",
            arguments={},
            success=False,
            error="Permission denied",
        )
        d = tc.to_dict()
        assert d["error"] == "Permission denied"
        restored = ToolCallExperience.from_dict(d)
        assert restored.error == "Permission denied"
        assert restored.success is False


class TestSessionExperience:
    def test_round_trip(self):
        exp = SessionExperience(
            session_id="sess-1",
            profile="dev",
            mission="Analyze data",
            total_steps=5,
            total_tokens=1000,
            final_answer="Done.",
            errors=["timeout"],
            processed_by=["consol-1"],
        )
        exp.tool_calls.append(ToolCallExperience(tool_name="python", arguments={"code": "1+1"}))
        d = exp.to_dict()
        restored = SessionExperience.from_dict(d)
        assert restored.session_id == "sess-1"
        assert restored.profile == "dev"
        assert restored.total_steps == 5
        assert len(restored.tool_calls) == 1
        assert restored.processed_by == ["consol-1"]
        assert restored.errors == ["timeout"]


class TestConsolidationResult:
    def test_round_trip(self):
        result = ConsolidationResult(
            consolidation_id="abc123",
            strategy="batch",
            sessions_processed=3,
            memories_created=5,
            quality_score=0.85,
            session_ids=["s1", "s2", "s3"],
        )
        d = result.to_dict()
        restored = ConsolidationResult.from_dict(d)
        assert restored.consolidation_id == "abc123"
        assert restored.strategy == "batch"
        assert restored.sessions_processed == 3
        assert restored.memories_created == 5
        assert restored.quality_score == 0.85
        assert len(restored.session_ids) == 3


class TestEnums:
    def test_consolidation_strategy_values(self):
        assert ConsolidationStrategy.IMMEDIATE.value == "immediate"
        assert ConsolidationStrategy.BATCH.value == "batch"
        assert ConsolidationStrategy.SCHEDULED.value == "scheduled"

    def test_consolidated_memory_kind_values(self):
        assert ConsolidatedMemoryKind.PROCEDURAL.value == "procedural"
        assert ConsolidatedMemoryKind.EPISODIC.value == "episodic"
        assert ConsolidatedMemoryKind.SEMANTIC.value == "semantic"
        assert ConsolidatedMemoryKind.META_COGNITIVE.value == "meta_cognitive"
