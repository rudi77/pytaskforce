"""LLM-based experiment proposer.

Uses LiteLLM directly to generate experiment proposals. All domain context
(system prompts, user templates, context files) comes from configuration.
"""

import json
import logging
import random
from pathlib import Path

import litellm

from autooptim.errors import ProposerError
from autooptim.experiment_log import ExperimentLog
from autooptim.models import (
    ExperimentPlan,
    FileChange,
    ProposerConfig,
    RunConfig,
    Scores,
)

logger = logging.getLogger(__name__)

# Default prompts if no config-specific ones are provided
DEFAULT_PROMPTS_DIR = Path(__file__).parent / "prompts"

DEFAULT_SYSTEM_PROMPT = """\
# AutoOptim Experiment Proposer

You are an AI research assistant tasked with optimizing a software system
through iterative single-variable experiments.

## Your Role

You receive:
1. The experiment history (what was tried, what worked/failed)
2. The current state of files you can modify
3. The assigned experiment category
4. The current baseline scores

You output a structured JSON experiment plan.

## Rules

1. **One thing at a time**: Change ONE variable per experiment.
2. **Build on success**: Review what worked before and extend it.
3. **Don't repeat failures**: If something was tried and failed, propose something different.
4. **Be specific**: Provide exact file paths and complete content.
5. **For text/code changes**: Provide the FULL new file content, not a diff.
6. **For config changes**: Provide only the keys to change as a YAML dict.

## Output Format

Return a single JSON object (no markdown code fences):

{
  "category": "config",
  "hypothesis": "What you expect to happen and why",
  "description": "Short description of the change (one sentence)",
  "files": [
    {
      "path": "relative/path/to/file",
      "action": "modify",
      "content": "new content or YAML dict of changes"
    }
  ],
  "risk": "low",
  "expected_impact": "score_name +5%"
}
"""

DEFAULT_USER_TEMPLATE = """\
# Experiment Proposal Request

## Assigned Category: {category}

## Experiment History

{experiment_history}

## Current Baseline

Composite score: {baseline_composite:.4f}
{baseline_scores_text}

## Current File State

{current_files}

## Instructions

Propose a SINGLE experiment in the "{category}" category that you believe
will improve the composite score.

Remember:
- Change only ONE variable
- Be specific and provide complete file content
- Build on what worked before; avoid repeating what failed
- The experiment must be in the "{category}" category

Return your experiment plan as a JSON object.
"""


class ExperimentProposer:
    """Generates experiment proposals using an LLM.

    All domain context is loaded from the RunConfig, not hardcoded.
    """

    def __init__(
        self,
        project_root: Path,
        config: RunConfig,
        experiment_log: ExperimentLog,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self.log = experiment_log
        self._system_prompt = self._load_system_prompt()
        self._user_template = self._load_user_template()

    def _load_system_prompt(self) -> str:
        """Load system prompt from config or use default."""
        pc = self.config.proposer
        if pc.system_prompt:
            return pc.system_prompt
        if pc.system_prompt_file:
            path = Path(pc.system_prompt_file)
            if path.exists():
                return path.read_text(encoding="utf-8")
        # Try default prompts dir
        default = DEFAULT_PROMPTS_DIR / "default_system.md"
        if default.exists():
            return default.read_text(encoding="utf-8")
        return DEFAULT_SYSTEM_PROMPT

    def _load_user_template(self) -> str:
        """Load user template from config or use default."""
        pc = self.config.proposer
        if pc.user_template:
            return pc.user_template
        if pc.user_template_file:
            path = Path(pc.user_template_file)
            if path.exists():
                return path.read_text(encoding="utf-8")
        default = DEFAULT_PROMPTS_DIR / "default_user.md"
        if default.exists():
            return default.read_text(encoding="utf-8")
        return DEFAULT_USER_TEMPLATE

    def select_category(self) -> str:
        """Select experiment category using weighted random selection."""
        categories = list(self.config.categories.keys())
        if not categories:
            raise ProposerError("No categories configured")

        weights = [self.config.categories[c].weight for c in categories]
        total = sum(weights)
        if total == 0:
            return random.choice(categories)
        return random.choices(categories, weights=weights, k=1)[0]

    def _read_file(self, path: str) -> str:
        """Read a file from the project root, truncating if too large."""
        full_path = self.project_root / path
        if not full_path.exists():
            return f"# File not found: {path}"
        content = full_path.read_text(encoding="utf-8", errors="replace")
        if len(content) > 8000:
            content = content[:8000] + "\n\n... (truncated) ..."
        return content

    def _build_context(
        self,
        category: str,
        baseline_scores: Scores,
    ) -> tuple[str, str]:
        """Build system and user prompts for the proposer LLM.

        Returns:
            Tuple of (system_prompt, user_prompt).
        """
        # Build current file state for this category
        cat_config = self.config.categories.get(category)
        context_files = cat_config.context_files if cat_config else []

        file_sections: list[str] = []
        for fp in context_files:
            content = self._read_file(fp)
            file_sections.append(f"### {fp}\n```\n{content}\n```")
        current_files = "\n\n".join(file_sections) if file_sections else "No files to show."

        # Build experiment history
        score_names = [s.name for s in self.config.metric.scores]
        experiment_history = self.log.summary_text(score_names=score_names)

        # Build baseline scores text
        baseline_parts = []
        for name in score_names:
            val = baseline_scores.get(name)
            baseline_parts.append(f"- {name}: {val:.4f}")
        baseline_scores_text = "\n".join(baseline_parts) if baseline_parts else "No scores yet."

        # Compute composite for display
        from autooptim.metric import ConfigurableMetric

        metric = ConfigurableMetric(self.config.metric)
        baseline_composite = metric.compute(baseline_scores)

        user_prompt = self._user_template.format(
            category=category,
            experiment_history=experiment_history,
            baseline_composite=baseline_composite,
            baseline_scores_text=baseline_scores_text,
            current_files=current_files,
        )

        return self._system_prompt, user_prompt

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
        if category is None:
            category = self.select_category()

        system_prompt, user_prompt = self._build_context(category, baseline_scores)

        logger.info(
            "Proposing %s experiment via %s", category, self.config.proposer.model
        )

        try:
            response = litellm.completion(
                model=self.config.proposer.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.config.proposer.temperature,
                max_tokens=self.config.proposer.max_tokens,
                drop_params=True,
            )
        except Exception as e:
            raise ProposerError(f"LLM call failed: {e}")

        content = response.choices[0].message.content
        if not content:
            raise ProposerError("Empty response from proposer LLM")

        return self._parse_response(content, category)

    def _parse_response(self, content: str, expected_category: str) -> ExperimentPlan:
        """Parse the LLM response into an ExperimentPlan."""
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            content = "\n".join(lines)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            # Try to extract JSON from the response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(content[start:end])
                except json.JSONDecodeError:
                    raise ProposerError(f"Could not parse JSON from response: {e}")
            else:
                raise ProposerError(f"No JSON found in response: {e}")

        # Validate and convert
        category = data.get("category", expected_category)
        # Ensure category is valid
        if category not in self.config.categories:
            category = expected_category

        files = []
        for f in data.get("files", []):
            files.append(
                FileChange(
                    path=f.get("path", ""),
                    action=f.get("action", "modify"),
                    content=f.get("content", ""),
                )
            )

        if not files:
            raise ProposerError("Experiment plan has no file changes")

        return ExperimentPlan(
            category=category,
            hypothesis=data.get("hypothesis", ""),
            description=data.get("description", ""),
            files=files,
            risk=data.get("risk", "low"),
            expected_impact=data.get("expected_impact", ""),
        )
