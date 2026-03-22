"""Data models for the AutoOptim framework.

All models are generic and domain-agnostic. Score names, categories,
and configurations are defined by the user's YAML config file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ExperimentStatus(Enum):
    """Status of an experiment after evaluation."""

    KEPT = "kept"
    DISCARDED = "discarded"
    ERROR = "error"
    BASELINE = "baseline"


@dataclass
class FileChange:
    """A single file modification within an experiment."""

    path: str
    action: str  # "modify" | "create" | "delete"
    content: str  # full new content or description of changes


@dataclass
class ExperimentPlan:
    """LLM-generated experiment proposal."""

    category: str  # domain-defined string (e.g., "config", "prompt", "code", "refactor")
    hypothesis: str
    description: str
    files: list[FileChange]
    risk: str = "low"
    expected_impact: str = ""


@dataclass
class Scores:
    """Generic scores container. Keys are domain-defined.

    Score names are not hardcoded — they come from the YAML config's
    metric.scores section. This allows the same framework to handle
    any evaluation domain.
    """

    values: dict[str, float] = field(default_factory=dict)

    def get(self, name: str, default: float = 0.0) -> float:
        """Get a score by name, with a default."""
        return self.values.get(name, default)

    def __repr__(self) -> str:
        items = ", ".join(f"{k}={v:.4f}" for k, v in self.values.items())
        return f"Scores({items})"


@dataclass
class ExperimentResult:
    """Full result of a single experiment cycle."""

    experiment_id: int
    timestamp: datetime
    category: str
    description: str
    hypothesis: str
    git_sha: str
    status: ExperimentStatus
    scores: Scores
    composite_score: float
    baseline_composite: float
    eval_runs: int
    eval_cost_usd: float
    files_modified: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class MutatorConfig:
    """Configuration for a single mutator type."""

    type: str  # "yaml" | "code" | "text" | "custom"
    allowed_paths: list[str] = field(default_factory=list)
    blocked_paths: list[str] = field(default_factory=list)
    safe_keys: dict | None = None  # For YAML mutator: {section: [keys]} or {section: None}
    preflight_commands: list[str] = field(default_factory=list)
    custom_class: str | None = None  # "my_package.module:ClassName" for custom mutator
    validation_rules: dict | None = None  # Optional validation rules for YAML mutator


@dataclass
class CategoryConfig:
    """Configuration for a single optimization category."""

    weight: float = 1.0
    mutator: MutatorConfig = field(default_factory=lambda: MutatorConfig(type="text"))
    context_files: list[str] = field(default_factory=list)


@dataclass
class ScoreDefinition:
    """Definition of a single score metric."""

    name: str
    range: tuple[float, float] = (0.0, 1.0)
    type: str = "higher_is_better"  # "higher_is_better" | "lower_is_better"


@dataclass
class CompositeGroup:
    """A group of scores in the composite metric."""

    weight: float
    components: dict[str, float] | list[str] = field(default_factory=dict)
    type: str = "weighted_sum"  # "weighted_sum" | "ratio_to_baseline"


@dataclass
class MetricConfig:
    """Configuration for the composite metric."""

    scores: list[ScoreDefinition] = field(default_factory=list)
    quality: CompositeGroup = field(
        default_factory=lambda: CompositeGroup(weight=0.9, components={})
    )
    efficiency: CompositeGroup = field(
        default_factory=lambda: CompositeGroup(
            weight=0.1, components=[], type="ratio_to_baseline"
        )
    )
    extra_groups: dict[str, CompositeGroup] = field(default_factory=dict)


@dataclass
class EvaluatorConfig:
    """Configuration for the evaluator."""

    type: str = "command"  # "command" | "script" | "custom"
    command: str = ""
    script: str = ""
    custom_class: str | None = None
    quick_task: str = "quick"
    full_task: str = "full"
    timeout: int = 600
    parser_type: str = "json"  # "json" | "custom"
    parser_class: str | None = None


@dataclass
class ProposerConfig:
    """Configuration for the LLM proposer."""

    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.7
    max_tokens: int = 4000
    system_prompt_file: str | None = None  # path relative to config dir
    user_template_file: str | None = None
    system_prompt: str | None = None  # inline prompt
    user_template: str | None = None  # inline template


@dataclass
class RunConfig:
    """Full configuration for an optimization run."""

    name: str = "optimization"
    description: str = ""
    project_root: str = "."

    # Categories
    categories: dict[str, CategoryConfig] = field(default_factory=dict)

    # Evaluator
    evaluator: EvaluatorConfig = field(default_factory=EvaluatorConfig)

    # Metric
    metric: MetricConfig = field(default_factory=MetricConfig)

    # Proposer
    proposer: ProposerConfig = field(default_factory=ProposerConfig)

    # Runner settings
    max_iterations: int = 0  # 0 = unlimited
    max_cost_usd: float = 50.0
    eval_runs: int = 2
    tolerance: float = 0.02
    full_eval_every_n: int = 5
    large_improvement_threshold: float = 0.05
    resume: bool = False
    eval_mode: str = "quick"  # task name passed to evaluator (e.g. "quick", "full", "daily")
