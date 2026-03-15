"""Main autoresearch experiment loop runner.

Orchestrates the full cycle: propose → mutate → eval → keep/discard.

Usage:
    python -m evals.autoresearch.runner
    python -m evals.autoresearch.runner --max-iterations 20 --eval-mode quick
    python -m evals.autoresearch.runner --categories config,prompt --tolerance 0.03
    python -m evals.autoresearch.runner --resume  # resume from existing log
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from evals.autoresearch.code_mutator import CodeMutator, CodeMutationError, PreflightError
from evals.autoresearch.config_mutator import ConfigMutator, ConfigMutationError
from evals.autoresearch.evaluator import run_eval_averaged
from evals.autoresearch.experiment_log import ExperimentLog
from evals.autoresearch.git_manager import GitManager, GitError
from evals.autoresearch.metric import compute_composite
from evals.autoresearch.models import (
    EvalScores,
    ExperimentCategory,
    ExperimentResult,
    ExperimentStatus,
    RunConfig,
)
from evals.autoresearch.prompt_mutator import PromptMutator, PromptMutationError
from evals.autoresearch.proposer import ExperimentProposer, ProposerError

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = PROJECT_ROOT / ".autoresearch_state.json"


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_args() -> RunConfig:
    parser = argparse.ArgumentParser(
        description="Autoresearch: automated experiment loop for Taskforce optimization"
    )
    parser.add_argument("--max-iterations", type=int, default=0, help="Max experiments (0=unlimited)")
    parser.add_argument("--max-cost-usd", type=float, default=50.0, help="Max eval cost budget")
    parser.add_argument("--eval-mode", choices=["quick", "full"], default="quick")
    parser.add_argument("--eval-runs", type=int, default=2, help="Eval runs per experiment")
    parser.add_argument("--profile", default="dev", help="Taskforce profile to optimize")
    parser.add_argument("--proposer-model", default="claude-sonnet-4-20250514")
    parser.add_argument("--tolerance", type=float, default=0.02, help="Keep/discard tolerance band")
    parser.add_argument(
        "--categories",
        default="config,prompt",
        help="Comma-separated categories: config,prompt,code",
    )
    parser.add_argument("--resume", action="store_true", help="Resume from existing log")
    parser.add_argument("--full-eval-every-n", type=int, default=5)

    args = parser.parse_args()

    categories = [ExperimentCategory(c.strip()) for c in args.categories.split(",")]

    return RunConfig(
        max_iterations=args.max_iterations,
        max_cost_usd=args.max_cost_usd,
        eval_mode=args.eval_mode,
        eval_runs=args.eval_runs,
        profile=args.profile,
        proposer_model=args.proposer_model,
        tolerance=args.tolerance,
        categories=categories,
        full_eval_every_n=args.full_eval_every_n,
        resume=args.resume,
    )


def _get_eval_task_name(config: RunConfig, experiment_id: int) -> str:
    """Determine which eval task to run based on mode and experiment number."""
    if config.eval_mode == "full":
        return "coding_full"

    # Quick mode: use a subset. Periodically do a full eval.
    if experiment_id > 0 and experiment_id % config.full_eval_every_n == 0:
        logger.info("Periodic full eval (every %d experiments)", config.full_eval_every_n)
        return "coding_full"

    # Quick mode: run generation subset (4 tasks) as a reasonable quick proxy
    return "coding_generation"


def _save_state(experiment_id: int, baseline_sha: str, baseline_composite: float) -> None:
    """Save runner state for crash recovery."""
    state = {
        "experiment_id": experiment_id,
        "baseline_sha": baseline_sha,
        "baseline_composite": baseline_composite,
        "timestamp": datetime.utcnow().isoformat(),
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _load_state() -> dict | None:
    """Load runner state for crash recovery."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return None


def _cleanup_state() -> None:
    """Remove state file after clean exit."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def run(config: RunConfig) -> None:
    """Execute the autoresearch experiment loop."""
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    log_dir = PROJECT_ROOT / "evals" / "autoresearch" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run-{timestamp}.tsv"

    git = GitManager(PROJECT_ROOT)

    # Crash recovery check
    if git.has_uncommitted_changes():
        logger.warning("Uncommitted changes detected. Cleaning working tree...")
        git.clean_working_tree()

    # Create or resume experiment log
    if config.resume:
        # Find the most recent log file
        existing_logs = sorted(log_dir.glob("run-*.tsv"), reverse=True)
        if existing_logs:
            log_path = existing_logs[0]
            logger.info("Resuming from log: %s", log_path)
        else:
            logger.info("No existing log found, starting fresh")

    experiment_log = ExperimentLog(log_path)

    # Create branch for this run (unless resuming)
    if not config.resume:
        branch_name = f"autoresearch/run-{timestamp}"
        try:
            git.create_branch(branch_name)
        except GitError:
            logger.info("Branch creation skipped (may already exist)")

    # Initialize mutators and proposer
    config_mutator = ConfigMutator(PROJECT_ROOT)
    prompt_mutator = PromptMutator(PROJECT_ROOT)
    code_mutator = CodeMutator(PROJECT_ROOT)
    proposer = ExperimentProposer(PROJECT_ROOT, config, experiment_log)

    # --- Baseline ---
    next_id = experiment_log.next_experiment_id()

    if next_id == 0:
        logger.info("=" * 60)
        logger.info("  BASELINE EVALUATION")
        logger.info("=" * 60)

        baseline_start = time.time()
        baseline_scores, baseline_composite, baseline_cost = run_eval_averaged(
            task_name="coding_full",
            num_runs=config.eval_runs,
            project_root=PROJECT_ROOT,
        )
        baseline_duration = time.time() - baseline_start

        baseline_result = ExperimentResult(
            experiment_id=0,
            timestamp=datetime.utcnow(),
            category=ExperimentCategory.CONFIG,
            description="Baseline (no changes)",
            hypothesis="Establish baseline performance",
            git_sha=git.get_current_sha(),
            status=ExperimentStatus.BASELINE,
            scores=baseline_scores,
            composite_score=baseline_composite,
            baseline_composite=baseline_composite,
            eval_runs=config.eval_runs,
            eval_cost_usd=baseline_cost,
            duration_seconds=baseline_duration,
        )
        experiment_log.append(baseline_result)
        next_id = 1

        logger.info(
            "Baseline: composite=%.4f (tc=%.2f, oa=%.2f, qa=%.2f, steps=%.0f, tokens=%.0f)",
            baseline_composite,
            baseline_scores.task_completion,
            baseline_scores.output_accuracy,
            baseline_scores.model_graded_qa,
            baseline_scores.efficiency_steps,
            baseline_scores.efficiency_tokens,
        )
    else:
        # Resume: load baseline from log
        all_results = experiment_log.read_all()
        baseline_entry = all_results[0]
        baseline_scores = baseline_entry.scores
        baseline_composite = baseline_entry.composite_score
        # Update baseline to the last kept experiment
        for r in all_results:
            if r.status in (ExperimentStatus.KEPT, ExperimentStatus.BASELINE):
                baseline_scores = r.scores
                baseline_composite = r.composite_score
        logger.info("Resumed. Current baseline composite: %.4f", baseline_composite)

    baseline_sha = git.get_current_sha()
    _save_state(next_id, baseline_sha, baseline_composite)

    # --- Experiment Loop ---
    iteration = 0
    total_cost = experiment_log.total_cost()

    while True:
        experiment_id = next_id + iteration
        iteration += 1

        # Check stopping conditions
        if config.max_iterations > 0 and iteration > config.max_iterations:
            logger.info("Reached max iterations (%d). Stopping.", config.max_iterations)
            break

        if total_cost >= config.max_cost_usd:
            logger.info("Reached cost budget ($%.2f >= $%.2f). Stopping.", total_cost, config.max_cost_usd)
            break

        logger.info("")
        logger.info("=" * 60)
        logger.info("  EXPERIMENT #%d  (iteration %d, budget: $%.2f/$%.2f)",
                     experiment_id, iteration, total_cost, config.max_cost_usd)
        logger.info("=" * 60)

        exp_start = time.time()

        # 1. Propose experiment
        try:
            plan = proposer.propose(baseline_scores)
        except ProposerError as e:
            logger.error("Proposer failed: %s", e)
            continue

        logger.info("Proposed [%s]: %s", plan.category.value, plan.description)
        logger.info("Hypothesis: %s", plan.hypothesis)

        # 2. Apply experiment
        modified_files: list[str] = []
        try:
            if plan.category == ExperimentCategory.CONFIG:
                modified_files = config_mutator.apply(plan)
            elif plan.category == ExperimentCategory.PROMPT:
                modified_files = prompt_mutator.apply(plan)
            elif plan.category == ExperimentCategory.CODE:
                modified_files = code_mutator.apply(plan)
        except (ConfigMutationError, PromptMutationError, CodeMutationError, PreflightError) as e:
            logger.error("Mutation failed: %s", e)
            git.clean_working_tree()

            error_result = ExperimentResult(
                experiment_id=experiment_id,
                timestamp=datetime.utcnow(),
                category=plan.category,
                description=plan.description,
                hypothesis=plan.hypothesis,
                git_sha=git.get_current_sha(),
                status=ExperimentStatus.ERROR,
                scores=EvalScores(),
                composite_score=0.0,
                baseline_composite=baseline_composite,
                eval_runs=0,
                eval_cost_usd=0.0,
                files_modified=[f.path for f in plan.files],
                duration_seconds=time.time() - exp_start,
            )
            experiment_log.append(error_result)
            continue

        if not modified_files:
            logger.warning("No files were modified. Skipping eval.")
            continue

        # 3. Commit experiment
        try:
            commit_sha = git.commit_experiment(experiment_id, plan.description, modified_files)
        except GitError as e:
            logger.error("Git commit failed: %s", e)
            git.clean_working_tree()
            continue

        # 4. Run eval
        task_name = _get_eval_task_name(config, experiment_id)
        logger.info("Running eval: %s (%d runs)", task_name, config.eval_runs)

        scores, composite, eval_cost = run_eval_averaged(
            task_name=task_name,
            num_runs=config.eval_runs,
            project_root=PROJECT_ROOT,
            baseline_scores=baseline_scores,
        )
        total_cost += eval_cost
        exp_duration = time.time() - exp_start

        delta = composite - baseline_composite
        logger.info(
            "Result: composite=%.4f (delta=%+.4f, threshold=%+.4f)",
            composite, delta, -config.tolerance,
        )

        # 5. Keep or discard
        if composite >= baseline_composite - config.tolerance:
            status = ExperimentStatus.KEPT
            baseline_scores = scores
            baseline_composite = composite
            baseline_sha = commit_sha
            logger.info("KEPT — new baseline: %.4f", baseline_composite)
        else:
            status = ExperimentStatus.DISCARDED
            git.discard_last_commit()
            logger.info("DISCARDED — baseline unchanged: %.4f", baseline_composite)

        # 6. Log result
        result = ExperimentResult(
            experiment_id=experiment_id,
            timestamp=datetime.utcnow(),
            category=plan.category,
            description=plan.description,
            hypothesis=plan.hypothesis,
            git_sha=commit_sha,
            status=status,
            scores=scores,
            composite_score=composite,
            baseline_composite=baseline_composite,
            eval_runs=config.eval_runs,
            eval_cost_usd=eval_cost,
            files_modified=modified_files,
            duration_seconds=exp_duration,
        )
        experiment_log.append(result)
        _save_state(experiment_id + 1, baseline_sha, baseline_composite)

        # If a large improvement was found on quick eval, validate with full eval
        if (
            status == ExperimentStatus.KEPT
            and delta > 0.05
            and task_name != "coding_full"
        ):
            logger.info("Large improvement detected (+%.4f). Running full eval to validate...", delta)
            full_scores, full_composite, full_cost = run_eval_averaged(
                task_name="coding_full",
                num_runs=config.eval_runs,
                project_root=PROJECT_ROOT,
                baseline_scores=baseline_scores,
            )
            total_cost += full_cost
            logger.info(
                "Full eval validation: composite=%.4f (quick was %.4f)",
                full_composite, composite,
            )

    # --- Summary ---
    logger.info("")
    logger.info("=" * 60)
    logger.info("  AUTORESEARCH COMPLETE")
    logger.info("=" * 60)
    logger.info("Iterations: %d", iteration - 1)
    logger.info("Total cost: $%.2f", total_cost)
    logger.info("Final baseline composite: %.4f", baseline_composite)
    logger.info("Log: %s", log_path)

    all_results = experiment_log.read_all()
    kept = [r for r in all_results if r.status == ExperimentStatus.KEPT]
    discarded = [r for r in all_results if r.status == ExperimentStatus.DISCARDED]
    errors = [r for r in all_results if r.status == ExperimentStatus.ERROR]
    logger.info("Kept: %d, Discarded: %d, Errors: %d", len(kept), len(discarded), len(errors))

    if kept:
        logger.info("Kept experiments:")
        for r in kept:
            logger.info("  #%d [%s]: %s (composite=%.4f)", r.experiment_id, r.category.value, r.description, r.composite_score)

    _cleanup_state()


def main() -> None:
    _setup_logging()
    config = _parse_args()
    logger.info("Autoresearch starting with config:")
    logger.info("  categories: %s", [c.value for c in config.categories])
    logger.info("  eval_mode: %s", config.eval_mode)
    logger.info("  proposer_model: %s", config.proposer_model)
    logger.info("  tolerance: %.3f", config.tolerance)
    logger.info("  max_iterations: %s", config.max_iterations or "unlimited")
    logger.info("  max_cost: $%.2f", config.max_cost_usd)

    try:
        run(config)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user. State saved for resume.")
        sys.exit(0)
    except Exception:
        logger.exception("Autoresearch failed with unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
