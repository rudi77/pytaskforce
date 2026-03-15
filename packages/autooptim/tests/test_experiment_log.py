"""Tests for the experiment log."""

from datetime import datetime, timezone
from pathlib import Path

from autooptim.experiment_log import ExperimentLog
from autooptim.models import ExperimentResult, ExperimentStatus, Scores


def _make_result(
    experiment_id: int = 1,
    status: ExperimentStatus = ExperimentStatus.KEPT,
    composite: float = 0.85,
) -> ExperimentResult:
    return ExperimentResult(
        experiment_id=experiment_id,
        timestamp=datetime.now(timezone.utc),
        category="config",
        description="Test experiment",
        hypothesis="Testing hypothesis",
        git_sha="abc1234",
        status=status,
        scores=Scores(values={"accuracy": 0.9, "latency": 1.5}),
        composite_score=composite,
        baseline_composite=0.80,
        eval_runs=2,
        eval_cost_usd=0.05,
        files_modified=["config.yaml"],
        duration_seconds=10.5,
    )


def test_append_and_read(tmp_path: Path):
    log = ExperimentLog(tmp_path / "test.tsv")
    result = _make_result()
    log.append(result)

    results = log.read_all()
    assert len(results) == 1
    assert results[0].experiment_id == 1
    assert results[0].status == ExperimentStatus.KEPT
    assert results[0].scores.get("accuracy") == 0.9
    assert results[0].scores.get("latency") == 1.5
    assert results[0].files_modified == ["config.yaml"]


def test_next_experiment_id(tmp_path: Path):
    log = ExperimentLog(tmp_path / "test.tsv")
    assert log.next_experiment_id() == 0

    log.append(_make_result(experiment_id=0))
    assert log.next_experiment_id() == 1

    log.append(_make_result(experiment_id=1))
    assert log.next_experiment_id() == 2


def test_total_cost(tmp_path: Path):
    log = ExperimentLog(tmp_path / "test.tsv")
    log.append(_make_result(experiment_id=0))
    log.append(_make_result(experiment_id=1))
    assert abs(log.total_cost() - 0.10) < 0.001


def test_summary_text(tmp_path: Path):
    log = ExperimentLog(tmp_path / "test.tsv")
    assert "No experiments" in log.summary_text()

    log.append(_make_result(experiment_id=0, status=ExperimentStatus.BASELINE))
    log.append(_make_result(experiment_id=1, status=ExperimentStatus.KEPT, composite=0.87))

    summary = log.summary_text(score_names=["accuracy", "latency"])
    assert "Exp #0" in summary
    assert "Exp #1" in summary
    assert "baseline" in summary
    assert "kept" in summary
    assert "accuracy=" in summary


def test_empty_log_read(tmp_path: Path):
    log = ExperimentLog(tmp_path / "nonexistent.tsv")
    assert log.read_all() == []
