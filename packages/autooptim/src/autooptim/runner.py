"""Main optimization loop runner.

Orchestrates the full cycle: propose -> mutate -> eval -> keep/discard.
All domain-specific behavior comes from the config-driven components.
"""

import importlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from autooptim.errors import GitError, MutationError, PreflightError, ProposerError
from autooptim.evaluators.command_evaluator import CommandEvaluator
from autooptim.evaluators.script_evaluator import ScriptEvaluator
from autooptim.experiment_log import ExperimentLog
from autooptim.git_manager import GitManager
from autooptim.metric import ConfigurableMetric
from autooptim.models import (
    ExperimentResult,
    ExperimentStatus,
    RunConfig,
    Scores,
)
from autooptim.mutators.code_mutator import CodeMutator
from autooptim.mutators.text_mutator import TextMutator
from autooptim.mutators.yaml_mutator import YamlMutator
from autooptim.proposer import ExperimentProposer

logger = logging.getLogger(__name__)


def _load_custom_class(class_path: str) -> type:
    """Load a class from a dotted path like 'package.module:ClassName'."""
    module_path, class_name = class_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _build_mutators(
    config: RunConfig, project_root: Path
) -> dict[str, YamlMutator | CodeMutator | TextMutator]:
    """Build mutators for each category from config."""
    mutators: dict = {}

    for cat_name, cat_config in config.categories.items():
        mc = cat_config.mutator
        if mc.type == "yaml":
            mutators[cat_name] = YamlMutator(project_root, mc)
        elif mc.type == "code":
            mutators[cat_name] = CodeMutator(project_root, mc)
        elif mc.type == "text":
            mutators[cat_name] = TextMutator(project_root, mc)
        elif mc.type == "custom" and mc.custom_class:
            cls = _load_custom_class(mc.custom_class)
            mutators[cat_name] = cls(project_root, mc)
        else:
            # Default to text mutator
            mutators[cat_name] = TextMutator(project_root, mc)

    return mutators


def _build_evaluator(
    config: RunConfig, project_root: Path, metric: ConfigurableMetric
) -> CommandEvaluator | ScriptEvaluator:
    """Build evaluator from config."""
    ec = config.evaluator

    if ec.type == "script":
        return ScriptEvaluator(ec, project_root, metric)
    elif ec.type == "custom" and ec.custom_class:
        cls = _load_custom_class(ec.custom_class)
        return cls(ec, project_root, metric)
    else:
        # Default to command evaluator
        parser = None
        if ec.parser_class:
            parser_cls = _load_custom_class(ec.parser_class)
            parser = parser_cls()
        return CommandEvaluator(ec, project_root, metric, score_parser=parser)


def _get_eval_task_name(config: RunConfig, experiment_id: int) -> str:
    """Determine which eval task to run based on mode and experiment number.

    eval_mode is passed directly as the task name to the evaluator command.
    The special values "quick" and "full" map to evaluator.quick_task and
    evaluator.full_task for backward compatibility; any other value (e.g.
    "daily", "memory", "all") is forwarded as-is.
    """
    # Map legacy names to configured task names
    mode = config.eval_mode
    if mode == "quick":
        base_task = config.evaluator.quick_task
    elif mode == "full":
        base_task = config.evaluator.full_task
    else:
        # Custom mode (daily, memory, all, etc.) — use directly
        base_task = mode

    return base_task


def _save_state(
    state_file: Path,
    experiment_id: int,
    baseline_sha: str,
    baseline_composite: float,
) -> None:
    """Save runner state for crash recovery."""
    state = {
        "experiment_id": experiment_id,
        "baseline_sha": baseline_sha,
        "baseline_composite": baseline_composite,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _cleanup_state(state_file: Path) -> None:
    """Remove state file after clean exit."""
    if state_file.exists():
        state_file.unlink()


def run(config: RunConfig) -> None:
    """Execute the optimization experiment loop.

    This is the core of AutoOptim: a generic propose -> mutate -> eval -> keep/discard
    loop that is configured entirely through RunConfig.

    Args:
        config: Full run configuration (typically loaded from YAML).
    """
    project_root = Path(config.project_root).resolve()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    # Set up log directory
    log_dir = project_root / ".autooptim" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run-{timestamp}.tsv"

    state_file = project_root / ".autooptim_state.json"

    git = GitManager(project_root)

    # Crash recovery check
    if git.has_uncommitted_changes():
        logger.warning("Uncommitted changes detected. Cleaning working tree...")
        git.clean_working_tree()

    # Handle resume
    if config.resume:
        existing_logs = sorted(log_dir.glob("run-*.tsv"), reverse=True)
        if existing_logs:
            log_path = existing_logs[0]
            logger.info("Resuming from log: %s", log_path)
        else:
            logger.info("No existing log found, starting fresh")

    experiment_log = ExperimentLog(log_path)

    # Create branch for this run (unless resuming)
    if not config.resume:
        branch_name = f"autooptim/run-{timestamp}"
        try:
            git.create_branch(branch_name)
        except GitError:
            logger.info("Branch creation skipped (may already exist)")

    # Build components from config
    metric = ConfigurableMetric(config.metric)
    mutators = _build_mutators(config, project_root)
    evaluator = _build_evaluator(config, project_root, metric)
    proposer = ExperimentProposer(project_root, config, experiment_log)

    # --- Baseline ---
    next_id = experiment_log.next_experiment_id()

    if next_id == 0:
        logger.info("=" * 60)
        logger.info("  BASELINE EVALUATION")
        logger.info("=" * 60)

        baseline_task = _get_eval_task_name(config, 0)
        baseline_start = time.time()
        baseline_scores, baseline_composite, baseline_cost = evaluator.evaluate(
            task_name=baseline_task,
            num_runs=config.eval_runs,
        )
        baseline_duration = time.time() - baseline_start

        # Use first category as default for baseline
        first_category = next(iter(config.categories), "baseline")

        baseline_result = ExperimentResult(
            experiment_id=0,
            timestamp=datetime.now(timezone.utc),
            category=first_category,
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

        logger.info("Baseline: composite=%.4f | %s", baseline_composite, baseline_scores)
    else:
        # Resume: load baseline from log
        all_results = experiment_log.read_all()
        baseline_scores = all_results[0].scores
        baseline_composite = all_results[0].composite_score
        for r in all_results:
            if r.status in (ExperimentStatus.KEPT, ExperimentStatus.BASELINE):
                baseline_scores = r.scores
                baseline_composite = r.composite_score
        logger.info("Resumed. Current baseline composite: %.4f", baseline_composite)

    baseline_sha = git.get_current_sha()
    _save_state(state_file, next_id, baseline_sha, baseline_composite)

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
            logger.info(
                "Reached cost budget ($%.2f >= $%.2f). Stopping.",
                total_cost,
                config.max_cost_usd,
            )
            break

        logger.info("")
        logger.info("=" * 60)
        logger.info(
            "  EXPERIMENT #%d  (iteration %d, budget: $%.2f/$%.2f)",
            experiment_id,
            iteration,
            total_cost,
            config.max_cost_usd,
        )
        logger.info("=" * 60)

        exp_start = time.time()

        # 1. Propose experiment
        try:
            plan = proposer.propose(baseline_scores)
        except ProposerError as e:
            logger.error("Proposer failed: %s", e)
            continue

        logger.info("Proposed [%s]: %s", plan.category, plan.description)
        logger.info("Hypothesis: %s", plan.hypothesis)

        # 2. Apply experiment
        modified_files: list[str] = []
        mutator = mutators.get(plan.category)
        if mutator is None:
            logger.error("No mutator for category: %s", plan.category)
            continue

        try:
            modified_files = mutator.apply(plan)
        except (MutationError, PreflightError) as e:
            logger.error("Mutation failed: %s", e)
            git.clean_working_tree()

            error_result = ExperimentResult(
                experiment_id=experiment_id,
                timestamp=datetime.now(timezone.utc),
                category=plan.category,
                description=plan.description,
                hypothesis=plan.hypothesis,
                git_sha=git.get_current_sha(),
                status=ExperimentStatus.ERROR,
                scores=Scores(),
                composite_score=0.0,
                baseline_composite=baseline_composite,
                eval_runs=0,
                eval_cost_usd=0.0,
                files_modified=[f.path for f in plan.files],
                duration_seconds=time.time() - exp_start,
            )
            try:
                experiment_log.append(error_result)
            except OSError as log_err:
                logger.warning("Failed to write error result to log: %s", log_err)
            continue

        if not modified_files:
            logger.warning("No files were modified. Skipping eval.")
            continue

        # 3. Commit experiment
        try:
            commit_sha = git.commit_experiment(
                experiment_id, plan.description, modified_files
            )
        except GitError as e:
            logger.error("Git commit failed: %s", e)
            git.clean_working_tree()
            continue

        # 4. Run eval
        task_name = _get_eval_task_name(config, experiment_id)
        logger.info("Running eval: %s (%d runs)", task_name, config.eval_runs)

        scores, composite, eval_cost = evaluator.evaluate(
            task_name=task_name,
            num_runs=config.eval_runs,
            baseline_scores=baseline_scores,
        )
        total_cost += eval_cost
        exp_duration = time.time() - exp_start

        delta = composite - baseline_composite
        logger.info(
            "Result: composite=%.4f (delta=%+.4f, threshold=%+.4f)",
            composite,
            delta,
            -config.tolerance,
        )

        # 5. Keep or discard
        pre_experiment_composite = baseline_composite
        pre_experiment_scores = baseline_scores
        pre_experiment_sha = baseline_sha
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
            timestamp=datetime.now(timezone.utc),
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
        _save_state(state_file, experiment_id + 1, baseline_sha, baseline_composite)

        # If large improvement on quick eval, validate with full eval to catch
        # overfitting. Only applies when eval_mode is "quick" (the fast smoke-test
        # mode). For broader modes (daily, full, all) the eval is already
        # comprehensive enough that a separate validation pass adds cost without
        # value.
        if (
            status == ExperimentStatus.KEPT
            and delta > config.large_improvement_threshold
            and config.eval_mode == "quick"
        ):
            logger.info(
                "Large improvement (+%.4f). Running full eval to validate...", delta
            )
            full_scores, full_composite, full_cost = evaluator.evaluate(
                task_name=config.evaluator.full_task,
                num_runs=config.eval_runs,
            )
            total_cost += full_cost
            logger.info(
                "Full eval validation: composite=%.4f (quick was %.4f)",
                full_composite,
                composite,
            )

            # If full eval shows regression vs pre-experiment baseline, discard
            if full_composite < pre_experiment_composite - config.tolerance:
                logger.warning(
                    "Full eval REGRESSED (%.4f < %.4f). Reverting experiment.",
                    full_composite,
                    pre_experiment_composite,
                )
                git.discard_last_commit()
                # Restore baseline to pre-experiment state
                baseline_scores = pre_experiment_scores
                baseline_composite = pre_experiment_composite
                baseline_sha = pre_experiment_sha
            else:
                # Full eval confirms improvement — use full eval scores as new baseline
                baseline_scores = full_scores
                baseline_composite = full_composite
                baseline_sha = commit_sha
                logger.info("Full eval CONFIRMED. New baseline: %.4f", baseline_composite)

            _save_state(state_file, experiment_id + 1, baseline_sha, baseline_composite)

    # --- Summary ---
    logger.info("")
    logger.info("=" * 60)
    logger.info("  AUTOOPTIM COMPLETE")
    logger.info("=" * 60)
    logger.info("Iterations: %d", iteration - 1)
    logger.info("Total cost: $%.2f", total_cost)
    logger.info("Final baseline composite: %.4f", baseline_composite)
    logger.info("Log: %s", log_path)

    all_results = experiment_log.read_all()
    kept = [r for r in all_results if r.status == ExperimentStatus.KEPT]
    discarded = [r for r in all_results if r.status == ExperimentStatus.DISCARDED]
    errors = [r for r in all_results if r.status == ExperimentStatus.ERROR]
    logger.info(
        "Kept: %d, Discarded: %d, Errors: %d", len(kept), len(discarded), len(errors)
    )

    if kept:
        logger.info("Kept experiments:")
        for r in kept:
            logger.info(
                "  #%d [%s]: %s (composite=%.4f)",
                r.experiment_id,
                r.category,
                r.description,
                r.composite_score,
            )

    _cleanup_state(state_file)
