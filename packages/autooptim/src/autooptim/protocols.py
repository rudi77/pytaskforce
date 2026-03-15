"""Extension point protocols for the AutoOptim framework.

All layer boundaries use Python Protocols (PEP 544) for structural subtyping.
Implement these to plug in domain-specific behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from autooptim.models import ExperimentPlan, Scores


class MutatorProtocol(Protocol):
    """Applies an experiment plan's file changes to the project.

    Each optimization category (config, code, text, etc.) has its own mutator
    that knows how to safely apply changes and validate them.
    """

    def apply(self, plan: ExperimentPlan) -> list[str]:
        """Apply changes from the experiment plan.

        Args:
            plan: Experiment plan containing file changes.

        Returns:
            List of modified file paths (relative to project root).

        Raises:
            MutationError: If the plan is invalid or unsafe.
        """
        ...

    def validate_path(self, path: str) -> bool:
        """Check if a file path is allowed for modification.

        Args:
            path: File path relative to project root.

        Returns:
            True if the path is allowed for modification.
        """
        ...

    def read_file(self, path: str) -> str:
        """Read a file and return its content for proposer context.

        Args:
            path: File path relative to project root.

        Returns:
            File content as string, or error message if not found.
        """
        ...


class EvaluatorProtocol(Protocol):
    """Runs evaluation and returns scores + cost.

    The evaluator is the most domain-specific component. It defines
    how to measure whether a mutation improved or degraded the system.
    """

    def evaluate(
        self,
        task_name: str,
        num_runs: int,
        baseline_scores: Scores | None = None,
    ) -> tuple[Scores, float, float]:
        """Run evaluation and return results.

        Args:
            task_name: Name of the eval task to run.
            num_runs: Number of runs to average over.
            baseline_scores: Baseline scores for composite computation.

        Returns:
            Tuple of (averaged_scores, composite_score, estimated_cost_usd).
        """
        ...


class MetricProtocol(Protocol):
    """Computes a composite scalar from a Scores object.

    The composite score is used for keep/discard decisions.
    Higher is always better.
    """

    def compute(
        self,
        scores: Scores,
        baseline_scores: Scores | None = None,
    ) -> float:
        """Compute a composite score from individual metrics.

        Args:
            scores: Current scores.
            baseline_scores: Baseline scores for relative metrics.

        Returns:
            Single composite score. Higher is better.
        """
        ...


class ProposerProtocol(Protocol):
    """Generates experiment proposals via LLM.

    The proposer analyzes experiment history and current file state
    to propose targeted, single-variable experiments.
    """

    def propose(
        self,
        baseline_scores: Scores,
        category: str | None = None,
    ) -> ExperimentPlan:
        """Generate an experiment proposal.

        Args:
            baseline_scores: Current baseline scores.
            category: Force a specific category (or None for weighted random).

        Returns:
            ExperimentPlan with proposed changes.

        Raises:
            ProposerError: If the LLM fails to generate a valid plan.
        """
        ...


class ScoreParserProtocol(Protocol):
    """Parses raw evaluation output into a Scores object.

    Different eval frameworks produce output in different formats.
    A ScoreParser adapts the raw output into the generic Scores model.
    """

    def parse(self, raw_output: str | dict) -> Scores:
        """Parse raw eval output into structured scores.

        Args:
            raw_output: Raw output from the evaluation command
                       (stdout string or parsed JSON dict).

        Returns:
            Scores object with named metrics.
        """
        ...


class PreflightProtocol(Protocol):
    """Runs pre-flight validation after mutations are applied.

    Pre-flight checks ensure that mutations don't break the project
    before running expensive evaluations.
    """

    def check(self, modified_files: list[str], project_root: Path) -> None:
        """Run validation on modified files.

        Args:
            modified_files: List of modified file paths (relative to project root).
            project_root: Absolute path to the project root.

        Raises:
            PreflightError: If any check fails.
        """
        ...
