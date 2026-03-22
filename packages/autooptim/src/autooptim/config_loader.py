"""YAML configuration loader for AutoOptim.

Parses the optimization target YAML config into RunConfig and
instantiates the appropriate components (mutators, evaluator, metric).
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from autooptim.errors import ConfigError
from autooptim.models import (
    CategoryConfig,
    CompositeGroup,
    EvaluatorConfig,
    MetricConfig,
    MutatorConfig,
    ProposerConfig,
    RunConfig,
    ScoreDefinition,
)

logger = logging.getLogger(__name__)


def load_config(config_path: str | Path) -> RunConfig:
    """Load an optimization config from a YAML file.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        Fully parsed RunConfig.

    Raises:
        ConfigError: If the config is invalid.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError("Config file must be a YAML dict")

    config_dir = config_path.parent

    return RunConfig(
        name=raw.get("name", "optimization"),
        description=raw.get("description", ""),
        project_root=raw.get("project_root", "."),
        categories=_parse_categories(raw.get("categories", {})),
        evaluator=_parse_evaluator(raw.get("evaluator", {})),
        metric=_parse_metric(raw.get("metric", {})),
        proposer=_parse_proposer(raw.get("proposer", {}), config_dir),
        max_iterations=raw.get("runner", {}).get("max_iterations", 0),
        max_cost_usd=raw.get("runner", {}).get("max_cost_usd", 50.0),
        eval_runs=raw.get("runner", {}).get("eval_runs", 2),
        tolerance=raw.get("runner", {}).get("tolerance", 0.02),
        full_eval_every_n=raw.get("runner", {}).get("full_eval_every_n", 5),
        large_improvement_threshold=raw.get("runner", {}).get(
            "large_improvement_threshold", 0.05
        ),
        eval_mode=raw.get("runner", {}).get("eval_mode", "quick"),
    )


def _parse_categories(raw: dict) -> dict[str, CategoryConfig]:
    """Parse the categories section."""
    categories = {}
    for name, cat_raw in raw.items():
        if not isinstance(cat_raw, dict):
            raise ConfigError(f"Category '{name}' must be a dict")

        mutator_raw = cat_raw.get("mutator", {})
        mutator = MutatorConfig(
            type=mutator_raw.get("type", "text"),
            allowed_paths=mutator_raw.get("allowed_paths", []),
            blocked_paths=mutator_raw.get("blocked_paths", []),
            safe_keys=mutator_raw.get("safe_keys"),
            preflight_commands=mutator_raw.get("preflight", []),
            custom_class=mutator_raw.get("class"),
            validation_rules=mutator_raw.get("validation_rules"),
        )

        categories[name] = CategoryConfig(
            weight=float(cat_raw.get("weight", 1.0)),
            mutator=mutator,
            context_files=cat_raw.get("context_files", []),
        )

    return categories


def _parse_evaluator(raw: dict) -> EvaluatorConfig:
    """Parse the evaluator section."""
    parser_raw = raw.get("parser", {})
    return EvaluatorConfig(
        type=raw.get("type", "command"),
        command=raw.get("command", ""),
        script=raw.get("script", ""),
        custom_class=raw.get("class"),
        quick_task=raw.get("quick_task", "quick"),
        full_task=raw.get("full_task", "full"),
        timeout=raw.get("timeout", 600),
        parser_type=parser_raw.get("type", "json"),
        parser_class=parser_raw.get("class"),
    )


def _parse_metric(raw: dict) -> MetricConfig:
    """Parse the metric section."""
    scores = []
    for s in raw.get("scores", []):
        score_range = s.get("range", [0.0, 1.0])
        scores.append(ScoreDefinition(
            name=s["name"],
            range=tuple(score_range) if isinstance(score_range, list) else (0.0, 1.0),
            type=s.get("type", "higher_is_better"),
        ))

    composite = raw.get("composite", {})

    quality_raw = composite.get("quality", {})
    quality = CompositeGroup(
        weight=quality_raw.get("weight", 0.9),
        components=quality_raw.get("components", {}),
        type=quality_raw.get("type", "weighted_sum"),
    )

    efficiency_raw = composite.get("efficiency", {})
    efficiency = CompositeGroup(
        weight=efficiency_raw.get("weight", 0.1),
        components=efficiency_raw.get("components", []),
        type=efficiency_raw.get("type", "ratio_to_baseline"),
    )

    # Parse any additional composite groups (e.g. future_readiness)
    extra_groups: dict[str, CompositeGroup] = {}
    for group_name, group_raw in composite.items():
        if group_name in ("quality", "efficiency"):
            continue
        if not isinstance(group_raw, dict):
            continue
        extra_groups[group_name] = CompositeGroup(
            weight=group_raw.get("weight", 0.0),
            components=group_raw.get("components", {}),
            type=group_raw.get("type", "weighted_sum"),
        )

    return MetricConfig(
        scores=scores, quality=quality, efficiency=efficiency,
        extra_groups=extra_groups,
    )


def _parse_proposer(raw: dict, config_dir: Path) -> ProposerConfig:
    """Parse the proposer section, resolving file paths relative to config dir."""
    config = ProposerConfig(
        model=raw.get("model", "claude-sonnet-4-20250514"),
        temperature=raw.get("temperature", 0.7),
        max_tokens=raw.get("max_tokens", 4000),
        system_prompt=raw.get("system_prompt"),
        user_template=raw.get("user_template"),
    )

    # Resolve file paths relative to config directory
    if "system_prompt_file" in raw:
        prompt_file = config_dir / raw["system_prompt_file"]
        if prompt_file.exists():
            config.system_prompt_file = str(prompt_file)
        else:
            logger.warning("System prompt file not found: %s", prompt_file)

    if "user_template_file" in raw:
        template_file = config_dir / raw["user_template_file"]
        if template_file.exists():
            config.user_template_file = str(template_file)
        else:
            logger.warning("User template file not found: %s", template_file)

    return config
