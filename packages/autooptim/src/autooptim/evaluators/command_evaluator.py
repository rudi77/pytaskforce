"""Command-based evaluator.

Runs a shell command and parses the output to extract scores.
Supports multiple runs with averaging and pluggable score parsers.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from autooptim.errors import EvaluatorError
from autooptim.metric import ConfigurableMetric
from autooptim.models import EvaluatorConfig, Scores

logger = logging.getLogger(__name__)


class JsonScoreParser:
    """Default score parser that expects JSON output on stdout.

    The command should print a JSON object with score names as keys
    and float values. Example: {"accuracy": 0.85, "latency": 1.2}
    """

    def parse(self, raw_output: str | dict) -> Scores:
        """Parse JSON output into Scores."""
        if isinstance(raw_output, dict):
            return Scores(values={k: float(v) for k, v in raw_output.items()})

        # Try to extract JSON from stdout
        text = raw_output.strip()
        # Find the last JSON object in output (skip log lines)
        last_brace = text.rfind("}")
        if last_brace < 0:
            raise EvaluatorError(f"No JSON found in eval output:\n{text[:500]}")

        first_brace = text.rfind("{", 0, last_brace + 1)
        if first_brace < 0:
            raise EvaluatorError(f"No JSON found in eval output:\n{text[:500]}")

        try:
            data = json.loads(text[first_brace : last_brace + 1])
        except json.JSONDecodeError as e:
            raise EvaluatorError(f"Invalid JSON in eval output: {e}\n{text[:500]}")

        return Scores(values={k: float(v) for k, v in data.items()})


class CommandEvaluator:
    """Evaluator that runs a shell command and parses output.

    The command template can use {task_name} placeholder.
    The command should output scores as JSON to stdout.
    """

    def __init__(
        self,
        config: EvaluatorConfig,
        project_root: Path,
        metric: ConfigurableMetric,
        score_parser: JsonScoreParser | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.metric = metric
        self.parser = score_parser or JsonScoreParser()

    def evaluate(
        self,
        task_name: str,
        num_runs: int = 1,
        baseline_scores: Scores | None = None,
    ) -> tuple[Scores, float, float]:
        """Run evaluation command and return results.

        Args:
            task_name: Name of the eval task (substituted into command).
            num_runs: Number of runs to average.
            baseline_scores: Baseline for composite computation.

        Returns:
            Tuple of (averaged_scores, composite_score, estimated_cost).
        """
        all_scores: list[Scores] = []
        total_cost = 0.0

        for run_idx in range(num_runs):
            logger.info("Eval run %d/%d for task %s", run_idx + 1, num_runs, task_name)
            scores, cost = self._run_single(task_name)
            all_scores.append(scores)
            total_cost += cost

        if not all_scores:
            return Scores(), 0.0, 0.0

        # Average scores across runs
        avg = self._average_scores(all_scores)
        composite = self.metric.compute(avg, baseline_scores)

        return avg, composite, total_cost

    def _run_single(self, task_name: str) -> tuple[Scores, float]:
        """Run a single evaluation."""
        cmd = self.config.command.replace("{task_name}", task_name)

        logger.info("Running eval: %s", cmd)
        env = os.environ.copy()

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(self.project_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
            )
        except subprocess.TimeoutExpired:
            logger.error("Eval command timed out after %ds", self.config.timeout)
            return Scores(), 0.0

        if result.returncode != 0:
            logger.error(
                "Eval failed (exit %d): %s", result.returncode, result.stderr[-1000:]
            )
            return Scores(), 0.0

        try:
            scores = self.parser.parse(result.stdout)
        except EvaluatorError as e:
            logger.error("Score parsing failed: %s", e)
            return Scores(), 0.0

        # Estimate cost from tokens if available, otherwise 0
        cost = scores.get("cost_usd", 0.0)
        if cost == 0.0 and scores.get("efficiency_tokens", 0.0) > 0:
            cost = scores.get("efficiency_tokens") * 0.00001

        return scores, cost

    def _average_scores(self, all_scores: list[Scores]) -> Scores:
        """Compute the average of multiple Scores objects."""
        if not all_scores:
            return Scores()

        n = len(all_scores)
        # Collect all unique score names
        all_keys: set[str] = set()
        for s in all_scores:
            all_keys.update(s.values.keys())

        avg_values: dict[str, float] = {}
        for key in all_keys:
            avg_values[key] = sum(s.get(key) for s in all_scores) / n

        return Scores(values=avg_values)
