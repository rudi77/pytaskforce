"""Config mutator for autoresearch experiments.

Safely modifies YAML profile files, preserving comments and formatting
where possible. Operates on a whitelist of safe configuration keys.
"""

import logging
from pathlib import Path

import yaml

from evals.autoresearch.models import ExperimentPlan

logger = logging.getLogger(__name__)

# Keys that are safe to modify in profile YAML files.
# Organized by top-level section.
SAFE_KEYS = {
    "agent": {
        "planning_strategy",
        "max_steps",
        "planning_strategy_params",
        "max_parallel_tools",
    },
    "context_policy": {
        "max_items",
        "max_chars_per_item",
        "max_total_chars",
    },
    "tools": None,  # entire list can be replaced
    "logging": {
        "level",
    },
}


class ConfigMutationError(Exception):
    """Raised when a config mutation fails validation."""


class ConfigMutator:
    """Safely modifies YAML config files."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def apply(self, plan: ExperimentPlan) -> list[str]:
        """Apply config changes from the experiment plan.

        Args:
            plan: Experiment plan containing file changes.

        Returns:
            List of modified file paths (relative to project root).

        Raises:
            ConfigMutationError: If the plan modifies unsafe keys.
        """
        modified: list[str] = []

        for change in plan.files:
            full_path = self.project_root / change.path
            if not full_path.exists():
                raise ConfigMutationError(f"Config file not found: {change.path}")

            if not change.path.endswith((".yaml", ".yml")):
                raise ConfigMutationError(f"Not a YAML file: {change.path}")

            # Parse the proposed changes
            try:
                new_values = yaml.safe_load(change.content)
            except yaml.YAMLError as e:
                raise ConfigMutationError(f"Invalid YAML in change content: {e}")

            if not isinstance(new_values, dict):
                raise ConfigMutationError(
                    "Change content must be a YAML dict of keys to modify"
                )

            # Validate all keys are in the safe whitelist
            self._validate_keys(new_values)

            # Load existing config
            with open(full_path) as f:
                config = yaml.safe_load(f)

            if config is None:
                config = {}

            # Apply changes (deep merge for dicts, replace for scalars/lists)
            self._deep_merge(config, new_values)

            # Validate the resulting config is loadable
            self._validate_config(config)

            # Write back
            with open(full_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            modified.append(change.path)
            logger.info("Modified config: %s", change.path)

        return modified

    def _validate_keys(self, changes: dict) -> None:
        """Ensure all keys in changes are whitelisted."""
        for top_key, value in changes.items():
            if top_key not in SAFE_KEYS:
                raise ConfigMutationError(
                    f"Key '{top_key}' is not in the safe modification whitelist. "
                    f"Allowed top-level keys: {sorted(SAFE_KEYS.keys())}"
                )

            allowed_sub = SAFE_KEYS[top_key]
            if allowed_sub is None:
                # Entire value can be replaced (e.g., tools list)
                continue

            if isinstance(value, dict):
                for sub_key in value:
                    if sub_key not in allowed_sub:
                        raise ConfigMutationError(
                            f"Sub-key '{top_key}.{sub_key}' is not safe to modify. "
                            f"Allowed: {sorted(allowed_sub)}"
                        )

    def _deep_merge(self, base: dict, override: dict) -> None:
        """Recursively merge override into base, modifying base in place."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _validate_config(self, config: dict) -> None:
        """Validate the merged config is structurally valid."""
        # Basic structure checks
        if "agent" in config:
            agent = config["agent"]
            if "max_steps" in agent:
                steps = agent["max_steps"]
                if not isinstance(steps, int) or steps < 1 or steps > 200:
                    raise ConfigMutationError(
                        f"agent.max_steps must be 1-200, got {steps}"
                    )
            if "planning_strategy" in agent:
                valid = {"native_react", "plan_and_execute", "plan_and_react", "spar"}
                if agent["planning_strategy"] not in valid:
                    raise ConfigMutationError(
                        f"Invalid planning_strategy: {agent['planning_strategy']}"
                    )

        if "context_policy" in config:
            cp = config["context_policy"]
            for k in ("max_items", "max_chars_per_item", "max_total_chars"):
                if k in cp:
                    v = cp[k]
                    if not isinstance(v, int) or v < 1:
                        raise ConfigMutationError(f"context_policy.{k} must be positive int")

        if "tools" in config:
            tools = config["tools"]
            if not isinstance(tools, list):
                raise ConfigMutationError("tools must be a list")

    def read_config(self, config_path: str) -> str:
        """Read a config file and return its content as text."""
        full_path = self.project_root / config_path
        if not full_path.exists():
            return f"# File not found: {config_path}"
        return full_path.read_text()
