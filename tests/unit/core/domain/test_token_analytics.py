"""Tests for token analytics domain models and summary builder."""

from taskforce.core.domain.token_analytics import (
    ExecutionTokenSummary,
    LLMCallRecord,
    ModelTokenSummary,
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
