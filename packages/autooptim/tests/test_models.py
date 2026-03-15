"""Tests for AutoOptim data models."""

from autooptim.models import (
    ExperimentPlan,
    ExperimentStatus,
    FileChange,
    Scores,
)


def test_scores_get_default():
    scores = Scores(values={"accuracy": 0.95})
    assert scores.get("accuracy") == 0.95
    assert scores.get("missing") == 0.0
    assert scores.get("missing", 1.0) == 1.0


def test_scores_repr():
    scores = Scores(values={"a": 0.5, "b": 1.0})
    r = repr(scores)
    assert "a=0.5000" in r
    assert "b=1.0000" in r


def test_experiment_plan_creation():
    plan = ExperimentPlan(
        category="config",
        hypothesis="Testing",
        description="Test change",
        files=[FileChange(path="config.yaml", action="modify", content="key: value")],
    )
    assert plan.category == "config"
    assert len(plan.files) == 1
    assert plan.risk == "low"


def test_experiment_status_values():
    assert ExperimentStatus.KEPT.value == "kept"
    assert ExperimentStatus.DISCARDED.value == "discarded"
    assert ExperimentStatus.ERROR.value == "error"
    assert ExperimentStatus.BASELINE.value == "baseline"
