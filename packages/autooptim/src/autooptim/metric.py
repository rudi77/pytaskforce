"""Configurable composite metric computation.

Combines quality and efficiency scores into a single scalar for
keep/discard decisions. Weights and score names come from config.
"""

from __future__ import annotations

import logging

from autooptim.models import CompositeGroup, MetricConfig, Scores

logger = logging.getLogger(__name__)


class ConfigurableMetric:
    """Computes composite score from config-defined weights.

    Supports two group types:
    - weighted_sum: weighted average of score values
    - ratio_to_baseline: bonus based on improvement ratio vs baseline
    """

    def __init__(self, config: MetricConfig) -> None:
        self.config = config

    def compute(
        self,
        scores: Scores,
        baseline_scores: Scores | None = None,
    ) -> float:
        """Compute weighted composite metric. Higher is better.

        Args:
            scores: Current experiment scores.
            baseline_scores: Baseline scores for ratio-based groups.

        Returns:
            Composite score.
        """
        quality_value = self._compute_group(
            self.config.quality, scores, baseline_scores
        )
        efficiency_value = self._compute_group(
            self.config.efficiency, scores, baseline_scores
        )

        return quality_value + efficiency_value

    def _compute_group(
        self,
        group: CompositeGroup,
        scores: Scores,
        baseline_scores: Scores | None,
    ) -> float:
        """Compute a single group's contribution to the composite."""
        if group.type == "weighted_sum":
            return self._compute_weighted_sum(group, scores)
        elif group.type == "ratio_to_baseline":
            return self._compute_ratio_bonus(group, scores, baseline_scores)
        else:
            logger.warning("Unknown group type: %s, treating as weighted_sum", group.type)
            return self._compute_weighted_sum(group, scores)

    def _compute_weighted_sum(self, group: CompositeGroup, scores: Scores) -> float:
        """Compute weighted sum of score components."""
        if not isinstance(group.components, dict):
            return 0.0

        total = 0.0
        for score_name, weight in group.components.items():
            value = scores.get(score_name)
            # For lower_is_better scores, check the config
            score_def = next(
                (s for s in self.config.scores if s.name == score_name), None
            )
            if score_def and score_def.type == "lower_is_better":
                # Normalize: lower raw value = higher quality
                # Use 1/(1+value) as a simple normalization
                value = 1.0 / (1.0 + value) if value > 0 else 1.0
            total += weight * value

        return group.weight * total

    def _compute_ratio_bonus(
        self,
        group: CompositeGroup,
        scores: Scores,
        baseline_scores: Scores | None,
    ) -> float:
        """Compute efficiency bonus as ratio to baseline."""
        if baseline_scores is None:
            return group.weight  # neutral when no baseline

        component_names = (
            group.components if isinstance(group.components, list) else []
        )
        if not component_names:
            return group.weight

        per_component_weight = group.weight / len(component_names)
        total_bonus = 0.0

        for name in component_names:
            baseline_val = baseline_scores.get(name)
            current_val = scores.get(name)

            if baseline_val > 0 and current_val > 0:
                # For lower_is_better: ratio = baseline/current (lower current = higher ratio)
                ratio = baseline_val / current_val
                # Cap ratio to avoid outsized bonus
                total_bonus += per_component_weight * min(ratio, 2.0)
            else:
                total_bonus += per_component_weight

        return total_bonus


def create_default_metric() -> ConfigurableMetric:
    """Create a metric with sensible defaults matching the original autoresearch."""
    config = MetricConfig(
        scores=[],
        quality=CompositeGroup(weight=0.9, components={}),
        efficiency=CompositeGroup(weight=0.1, components=[], type="ratio_to_baseline"),
    )
    return ConfigurableMetric(config)
