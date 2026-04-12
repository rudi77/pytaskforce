"""Tests for token analytics domain models and summary builder."""

from taskforce.core.domain.token_analytics import (
    ExecutionTokenSummary,
    LLMCallRecord,
    ModelTokenSummary,
    StepTokenSummary,
    build_summary,
)


class TestLLMCallRecord:
    def test_defaults(self):
        r = LLMCallRecord(model="gpt-4o")
        assert r.prompt_tokens == 0
        assert r.total_tokens == 0
        assert r.tool_call_names == []

    def test_to_dict(self):
        r = LLMCallRecord(
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=200,
            total_tokens=1200,
            latency_ms=500,
            tool_call_names=["file_read"],
        )
        d = r.to_dict()
        assert d["model"] == "gpt-4o"
        assert d["total_tokens"] == 1200
        assert d["tool_call_names"] == ["file_read"]
        assert "timestamp" in d


class TestModelTokenSummary:
    def test_avg_zero_calls(self):
        s = ModelTokenSummary(model="m")
        assert s.avg_tokens_per_call == 0.0
        assert s.avg_latency_ms == 0.0

    def test_avg_computed(self):
        s = ModelTokenSummary(
            model="m", total_tokens=3000, call_count=3, total_latency_ms=900
        )
        assert s.avg_tokens_per_call == 1000.0
        assert s.avg_latency_ms == 300.0

    def test_to_dict(self):
        s = ModelTokenSummary(model="gpt-4o", total_tokens=1000, call_count=2)
        d = s.to_dict()
        assert d["avg_tokens_per_call"] == 500.0


class TestBuildSummary:
    def test_empty(self):
        s = build_summary([])
        assert s.total_tokens == 0
        assert s.total_llm_calls == 0
        assert s.model_breakdown == {}

    def test_single_call(self):
        calls = [
            LLMCallRecord(
                model="gpt-4o",
                prompt_tokens=500,
                completion_tokens=100,
                total_tokens=600,
                latency_ms=200,
            )
        ]
        s = build_summary(calls)
        assert s.total_tokens == 600
        assert s.total_prompt_tokens == 500
        assert s.total_completion_tokens == 100
        assert s.total_llm_calls == 1
        assert s.total_latency_ms == 200
        assert s.prompt_to_completion_ratio == 5.0
        assert "gpt-4o" in s.model_breakdown
        assert s.model_breakdown["gpt-4o"].call_count == 1

    def test_multiple_models(self):
        calls = [
            LLMCallRecord(model="gpt-4o", prompt_tokens=1000, completion_tokens=200, total_tokens=1200),
            LLMCallRecord(model="gpt-4o", prompt_tokens=1500, completion_tokens=300, total_tokens=1800),
            LLMCallRecord(model="gpt-4o-mini", prompt_tokens=300, completion_tokens=400, total_tokens=700),
        ]
        s = build_summary(calls)
        assert s.total_tokens == 3700
        assert s.total_llm_calls == 3
        assert s.model_breakdown["gpt-4o"].call_count == 2
        assert s.model_breakdown["gpt-4o"].total_tokens == 3000
        assert s.model_breakdown["gpt-4o-mini"].call_count == 1
        assert s.model_breakdown["gpt-4o-mini"].total_tokens == 700

    def test_ratio_zero_completion(self):
        calls = [LLMCallRecord(model="m", prompt_tokens=1000, completion_tokens=0, total_tokens=1000)]
        s = build_summary(calls)
        assert s.prompt_to_completion_ratio == 0.0

    def test_to_dict(self):
        calls = [
            LLMCallRecord(model="gpt-4o", prompt_tokens=500, completion_tokens=100, total_tokens=600),
        ]
        s = build_summary(calls)
        d = s.to_dict()
        assert d["total_tokens"] == 600
        assert d["total_llm_calls"] == 1
        assert "gpt-4o" in d["model_breakdown"]
        assert len(d["calls"]) == 1
        assert "step_breakdown" in d

    def test_step_breakdown_single_step(self):
        calls = [
            LLMCallRecord(
                model="gpt-4o",
                prompt_tokens=500,
                completion_tokens=100,
                total_tokens=600,
                latency_ms=200,
                tool_call_names=["file_read"],
                step_number=1,
                phase="reasoning",
            )
        ]
        s = build_summary(calls)
        assert len(s.step_breakdown) == 1
        ss = s.step_breakdown[0]
        assert ss.step_number == 1
        assert ss.phase == "reasoning"
        assert ss.total_tokens == 600
        assert ss.tool_call_names == ["file_read"]
        assert ss.llm_calls == 1

    def test_step_breakdown_groups_same_step(self):
        """Multiple LLM calls within one step should merge."""
        calls = [
            LLMCallRecord(
                model="gpt-4o", prompt_tokens=500, completion_tokens=100,
                total_tokens=600, latency_ms=200, step_number=1, phase="reasoning",
            ),
            LLMCallRecord(
                model="gpt-4o", prompt_tokens=600, completion_tokens=150,
                total_tokens=750, latency_ms=300,
                tool_call_names=["python"], step_number=1, phase="reasoning",
            ),
        ]
        s = build_summary(calls)
        assert len(s.step_breakdown) == 1
        ss = s.step_breakdown[0]
        assert ss.total_tokens == 1350
        assert ss.llm_calls == 2
        assert ss.tool_call_names == ["python"]

    def test_step_breakdown_multi_step_with_phases(self):
        """Full execution with planning, steps, and summarizing."""
        calls = [
            LLMCallRecord(
                model="gpt-4o", prompt_tokens=1000, completion_tokens=300,
                total_tokens=1300, step_number=None, phase="planning",
            ),
            LLMCallRecord(
                model="gpt-4o", prompt_tokens=2000, completion_tokens=100,
                total_tokens=2100, tool_call_names=["file_read"],
                step_number=1, phase="reasoning",
            ),
            LLMCallRecord(
                model="gpt-4o", prompt_tokens=2500, completion_tokens=200,
                total_tokens=2700, tool_call_names=["python"],
                step_number=2, phase="reasoning",
            ),
            LLMCallRecord(
                model="gpt-4o", prompt_tokens=3000, completion_tokens=400,
                total_tokens=3400, step_number=None, phase="summarizing",
            ),
        ]
        s = build_summary(calls)
        assert len(s.step_breakdown) == 4

        # Sorted: planning, summarizing (None steps first), then step 1, step 2
        assert s.step_breakdown[0].phase == "planning"
        assert s.step_breakdown[0].step_number is None
        assert s.step_breakdown[1].phase == "summarizing"
        assert s.step_breakdown[1].step_number is None
        assert s.step_breakdown[2].step_number == 1
        assert s.step_breakdown[3].step_number == 2

    def test_step_breakdown_sort_order(self):
        """Named phases sort: planning < compression < summarizing, then numbered steps."""
        calls = [
            LLMCallRecord(model="m", total_tokens=100, step_number=None, phase="summarizing"),
            LLMCallRecord(model="m", total_tokens=100, step_number=2, phase="acting"),
            LLMCallRecord(model="m", total_tokens=100, step_number=None, phase="planning"),
            LLMCallRecord(model="m", total_tokens=100, step_number=None, phase="compression"),
            LLMCallRecord(model="m", total_tokens=100, step_number=1, phase="reasoning"),
        ]
        s = build_summary(calls)
        phases = [(ss.step_number, ss.phase) for ss in s.step_breakdown]
        assert phases == [
            (None, "planning"),
            (None, "compression"),
            (None, "summarizing"),
            (1, "reasoning"),
            (2, "acting"),
        ]

    def test_step_breakdown_no_step_phase(self):
        """Records without step/phase default to unknown."""
        calls = [LLMCallRecord(model="m", total_tokens=100)]
        s = build_summary(calls)
        assert len(s.step_breakdown) == 1
        assert s.step_breakdown[0].phase == "unknown"
        assert s.step_breakdown[0].step_number is None


class TestLLMCallRecordStepFields:
    def test_step_fields_default_none(self):
        r = LLMCallRecord(model="m")
        assert r.step_number is None
        assert r.phase is None

    def test_step_fields_set(self):
        r = LLMCallRecord(model="m", step_number=3, phase="acting")
        assert r.step_number == 3
        assert r.phase == "acting"

    def test_to_dict_includes_step_fields(self):
        r = LLMCallRecord(model="m", step_number=1, phase="reasoning")
        d = r.to_dict()
        assert d["step_number"] == 1
        assert d["phase"] == "reasoning"


class TestStepTokenSummary:
    def test_to_dict(self):
        s = StepTokenSummary(
            step_number=1,
            phase="reasoning",
            prompt_tokens=500,
            completion_tokens=100,
            total_tokens=600,
            latency_ms=200,
            tool_call_names=["file_read"],
            llm_calls=1,
        )
        d = s.to_dict()
        assert d["step_number"] == 1
        assert d["phase"] == "reasoning"
        assert d["total_tokens"] == 600
        assert d["tool_call_names"] == ["file_read"]
