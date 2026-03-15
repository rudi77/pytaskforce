"""Tests for the configurable metric computation."""

from autooptim.metric import ConfigurableMetric
from autooptim.models import CompositeGroup, MetricConfig, ScoreDefinition, Scores


def _make_metric() -> ConfigurableMetric:
    """Create a metric matching the original autoresearch composite."""
    config = MetricConfig(
        scores=[
            ScoreDefinition(name="task_completion"),
            ScoreDefinition(name="output_accuracy"),
            ScoreDefinition(name="model_graded_qa"),
            ScoreDefinition(name="efficiency_steps", type="lower_is_better"),
            ScoreDefinition(name="efficiency_tokens", type="lower_is_better"),
        ],
        quality=CompositeGroup(
            weight=0.9,
            components={
                "task_completion": 0.50,
                "output_accuracy": 0.25,
                "model_graded_qa": 0.25,
            },
        ),
        efficiency=CompositeGroup(
            weight=0.1,
            components=["efficiency_steps", "efficiency_tokens"],
            type="ratio_to_baseline",
        ),
    )
    return ConfigurableMetric(config)


def test_compute_no_baseline():
    metric = _make_metric()
    scores = Scores(values={
        "task_completion": 1.0,
        "output_accuracy": 1.0,
        "model_graded_qa": 1.0,
        "efficiency_steps": 10.0,
        "efficiency_tokens": 1000.0,
    })
    result = metric.compute(scores, baseline_scores=None)
    # Quality: 0.9 * (0.5*1 + 0.25*1 + 0.25*1) = 0.9
    # Efficiency: 0.1 (neutral, no baseline)
    assert abs(result - 1.0) < 0.01


def test_compute_with_baseline():
    metric = _make_metric()
    baseline = Scores(values={
        "task_completion": 0.8,
        "output_accuracy": 0.6,
        "model_graded_qa": 0.5,
        "efficiency_steps": 20.0,
        "efficiency_tokens": 2000.0,
    })
    # Same as baseline
    result = metric.compute(baseline, baseline_scores=baseline)
    # Quality: 0.9 * (0.5*0.8 + 0.25*0.6 + 0.25*0.5) = 0.9 * (0.4+0.15+0.125) = 0.9 * 0.675
    quality = 0.9 * 0.675
    # Efficiency: ratio=1.0 for both, so 0.05*1 + 0.05*1 = 0.1
    assert abs(result - (quality + 0.1)) < 0.01


def test_compute_improved_efficiency():
    metric = _make_metric()
    baseline = Scores(values={
        "task_completion": 1.0,
        "output_accuracy": 1.0,
        "model_graded_qa": 1.0,
        "efficiency_steps": 20.0,
        "efficiency_tokens": 2000.0,
    })
    # Better efficiency (fewer steps/tokens)
    improved = Scores(values={
        "task_completion": 1.0,
        "output_accuracy": 1.0,
        "model_graded_qa": 1.0,
        "efficiency_steps": 10.0,  # 2x improvement
        "efficiency_tokens": 1000.0,  # 2x improvement
    })
    result = metric.compute(improved, baseline_scores=baseline)
    # Quality: 0.9
    # Efficiency: ratio=2.0 for both (capped at 2.0), so 0.05*2 + 0.05*2 = 0.2
    assert abs(result - 1.1) < 0.01


def test_compute_zero_scores():
    metric = _make_metric()
    scores = Scores()
    result = metric.compute(scores, baseline_scores=None)
    # Quality: 0.9 * 0 = 0, Efficiency: 0.1 (neutral)
    assert abs(result - 0.1) < 0.01
