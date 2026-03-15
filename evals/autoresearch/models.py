"""Data models for the autoresearch experiment loop."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ExperimentCategory(Enum):
    CONFIG = "config"
    PROMPT = "prompt"
    CODE = "code"


class ExperimentStatus(Enum):
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

    category: ExperimentCategory
    hypothesis: str
    description: str
    files: list[FileChange]
    risk: str = "low"
    expected_impact: str = ""


@dataclass
class EvalScores:
    """Scores from a single eval run."""

    task_completion: float = 0.0  # 0.0-1.0
    output_accuracy: float = 0.0  # 0.0-1.0
    model_graded_qa: float = 0.0  # 0.0-1.0
    efficiency_steps: float = 0.0  # raw step count
    efficiency_tokens: float = 0.0  # raw token count


@dataclass
class ExperimentResult:
    """Full result of a single experiment cycle."""

    experiment_id: int
    timestamp: datetime
    category: ExperimentCategory
    description: str
    hypothesis: str
    git_sha: str
    status: ExperimentStatus
    scores: EvalScores
    composite_score: float
    baseline_composite: float
    eval_runs: int
    eval_cost_usd: float
    files_modified: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class RunConfig:
    """Configuration for the autoresearch runner."""

    max_iterations: int = 0  # 0 = unlimited
    max_cost_usd: float = 50.0
    eval_mode: str = "quick"  # "quick" | "full"
    eval_runs: int = 2
    profile: str = "dev"
    proposer_model: str = "claude-sonnet-4-20250514"
    tolerance: float = 0.02
    categories: list[ExperimentCategory] = field(
        default_factory=lambda: [ExperimentCategory.CONFIG, ExperimentCategory.PROMPT]
    )
    category_weights: dict[ExperimentCategory, float] = field(
        default_factory=lambda: {
            ExperimentCategory.CONFIG: 0.50,
            ExperimentCategory.PROMPT: 0.35,
            ExperimentCategory.CODE: 0.15,
        }
    )
    quick_eval_task_ids: list[int] = field(default_factory=lambda: [0, 3, 6])
    full_eval_every_n: int = 5
    resume: bool = False
