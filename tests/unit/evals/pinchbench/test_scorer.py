"""Unit tests for evals.pinchbench.scorer.

Mocks ``run_automated_check`` and ``run_llm_judge`` so no subprocess is
spawned and no LLM call is made — we're testing the dispatch + hybrid
aggregation logic, not the graders themselves.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from evals.pinchbench import scorer as scorer_module


def _make_state(metadata: dict[str, Any], completion: str = "done") -> SimpleNamespace:
    output = SimpleNamespace(completion=completion)
    return SimpleNamespace(input_text="prompt", output=output, metadata=metadata)


def _base_meta(**overrides: Any) -> dict[str, Any]:
    meta = {
        "pinchbench_task_id": "task_x",
        "pinchbench_grading_type": "automated",
        "pinchbench_grade_function": "def grade(t,w): return {'k': 1.0}",
        "pinchbench_transcript": [],
        "pinchbench_workspace": "/tmp/pinchbench_ws_test",
        "pinchbench_prompt": "do x",
        "pinchbench_rubric": "Score 1.0 if x.",
        "pinchbench_expected_behavior": "x happens",
        "pinchbench_grading_criteria": "- x",
        "pinchbench_timeout_seconds": 60,
        "pinchbench_status": "completed",
    }
    meta.update(overrides)
    return meta


@pytest.mark.asyncio
async def test_agent_error_short_circuits_to_zero() -> None:
    state = _make_state(_base_meta(pinchbench_status="error", pinchbench_error="LLM 500"))
    result = await scorer_module._score_impl(state, state.metadata)
    assert result.value == 0.0
    assert "LLM 500" in result.explanation


@pytest.mark.asyncio
async def test_automated_path_returns_aggregated_score() -> None:
    state = _make_state(_base_meta(pinchbench_grading_type="automated"))
    with patch.object(
        scorer_module,
        "run_automated_check",
        return_value={"ok": True, "scores": {"a": 1.0, "b": 0.5}},
    ):
        result = await scorer_module._score_impl(state, state.metadata)
    assert result.value == 0.75
    assert result.metadata["components"] == {"automated": 0.75}


@pytest.mark.asyncio
async def test_automated_failure_returns_zero_when_pure_automated() -> None:
    state = _make_state(_base_meta(pinchbench_grading_type="automated"))
    with patch.object(
        scorer_module, "run_automated_check", return_value={"ok": False, "error": "boom"}
    ):
        result = await scorer_module._score_impl(state, state.metadata)
    assert result.value == 0.0
    assert "boom" in result.explanation


@pytest.mark.asyncio
async def test_llm_judge_only_path() -> None:
    state = _make_state(_base_meta(pinchbench_grading_type="llm_judge"))
    async def fake_judge(**kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "score": 0.6, "reasoning": "partial"}
    with patch.object(scorer_module, "run_llm_judge", side_effect=fake_judge):
        result = await scorer_module._score_impl(state, state.metadata)
    assert result.value == 0.6
    assert result.metadata["judge_reasoning"] == "partial"


@pytest.mark.asyncio
async def test_hybrid_averages_automated_and_judge() -> None:
    state = _make_state(_base_meta(pinchbench_grading_type="hybrid"))
    async def fake_judge(**kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "score": 0.4, "reasoning": ""}
    with patch.object(
        scorer_module, "run_automated_check", return_value={"ok": True, "scores": {"a": 0.8}}
    ), patch.object(scorer_module, "run_llm_judge", side_effect=fake_judge):
        result = await scorer_module._score_impl(state, state.metadata)
    # (0.8 + 0.4) / 2 = 0.6
    assert result.value == pytest.approx(0.6)
    assert result.metadata["components"] == {"automated": 0.8, "judge": 0.4}


@pytest.mark.asyncio
async def test_hybrid_with_failing_automated_falls_through_to_judge_and_marks_degraded() -> None:
    state = _make_state(_base_meta(pinchbench_grading_type="hybrid"))
    async def fake_judge(**kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "score": 0.5, "reasoning": "mid"}
    with patch.object(
        scorer_module, "run_automated_check", return_value={"ok": False, "error": "ImportError"}
    ), patch.object(scorer_module, "run_llm_judge", side_effect=fake_judge):
        result = await scorer_module._score_impl(state, state.metadata)
    assert result.value == 0.5
    assert result.metadata["grading_type"] == "hybrid_degraded_to_judge_only"
    assert result.metadata["automated_error"] == "ImportError"


@pytest.mark.asyncio
async def test_returns_zero_when_no_graders_usable() -> None:
    state = _make_state(_base_meta(
        pinchbench_grading_type="llm_judge",
        pinchbench_grade_function="",
    ))
    async def fake_judge(**kwargs: Any) -> dict[str, Any]:
        return {"ok": False, "error": "judge offline"}
    with patch.object(scorer_module, "run_llm_judge", side_effect=fake_judge):
        result = await scorer_module._score_impl(state, state.metadata)
    assert result.value == 0.0
    assert "no usable grader" in result.explanation


def test_cleanup_workspace_only_removes_pinchbench_dirs(tmp_path: Path) -> None:
    # A legit pinchbench-ish path should get removed
    legit = tmp_path / "pinchbench_ws_abc"
    legit.mkdir()
    (legit / "file.txt").write_text("x")
    scorer_module._cleanup_workspace(str(legit))
    assert not legit.exists()

    # A non-matching path must be left untouched even if metadata is malformed
    bystander = tmp_path / "important_data"
    bystander.mkdir()
    (bystander / "keep.txt").write_text("y")
    scorer_module._cleanup_workspace(str(bystander))
    assert bystander.exists()
    assert (bystander / "keep.txt").exists()


def test_cleanup_workspace_handles_none_and_missing(tmp_path: Path) -> None:
    scorer_module._cleanup_workspace(None)  # no-op
    scorer_module._cleanup_workspace("")  # no-op
    scorer_module._cleanup_workspace(str(tmp_path / "pinchbench_ws_does_not_exist"))  # no-op
