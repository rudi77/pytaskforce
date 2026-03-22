"""YAML config file mutator.

Safely modifies YAML files using a whitelist of safe keys from config.
Supports deep merging of dict values.
"""

import logging
from pathlib import Path

import yaml

from autooptim.errors import MutationError
from autooptim.models import ExperimentPlan, MutatorConfig
from autooptim.mutators.base import BaseMutator

logger = logging.getLogger(__name__)


class YamlMutator(BaseMutator):
    """Safely modifies YAML config files.

    Changes are validated against a configurable whitelist of safe keys.
    Values are deep-merged into existing config files.
    """

    def __init__(self, project_root: Path, config: MutatorConfig) -> None:
        super().__init__(project_root, config)
        # Convert safe_keys from config format to internal format
        # Config format: {"section": ["key1", "key2"]} or {"section": null}
        self.safe_keys: dict[str, set[str] | None] = {}
        if config.safe_keys:
            for section, keys in config.safe_keys.items():
                if keys is None:
                    self.safe_keys[section] = None
                elif isinstance(keys, list):
                    self.safe_keys[section] = set(keys)
                elif isinstance(keys, set):
                    self.safe_keys[section] = keys

    def apply(self, plan: ExperimentPlan) -> list[str]:
        """Apply config changes from the experiment plan.

        Args:
            plan: Experiment plan with file changes (content = YAML dict of keys).

        Returns:
            List of modified file paths.

        Raises:
            MutationError: If keys are unsafe or YAML is invalid.
        """
        modified: list[str] = []

        for change in plan.files:
            self._check_path(change.path)

            full_path = self.project_root / change.path
            if not full_path.exists():
                raise MutationError(f"Config file not found: {change.path}")

            if not change.path.endswith((".yaml", ".yml")):
                raise MutationError(f"Not a YAML file: {change.path}")

            # Parse proposed changes
            try:
                new_values = yaml.safe_load(change.content)
            except yaml.YAMLError as e:
                raise MutationError(f"Invalid YAML in change content: {e}")

            if not isinstance(new_values, dict):
                raise MutationError("Change content must be a YAML dict of keys to modify")

            # Validate keys against safe whitelist (if configured)
            if self.safe_keys:
                self._validate_keys(new_values)

            # Load existing config
            with open(full_path) as f:
                config = yaml.safe_load(f)
            if config is None:
                config = {}

            # Deep merge
            self._deep_merge(config, new_values)

            # Run validation rules if configured
            if self.config.validation_rules:
                self._validate_config(config)

            # Write back
            with open(full_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    config, f, default_flow_style=False, sort_keys=False, allow_unicode=True
                )

            modified.append(change.path)
            logger.info("Modified config: %s", change.path)

        return modified

    def _validate_keys(self, changes: dict) -> None:
        """Ensure all keys in changes are whitelisted."""
        for top_key, value in changes.items():
            if top_key not in self.safe_keys:
                raise MutationError(
                    f"Key '{top_key}' is not in the safe modification whitelist. "
                    f"Allowed top-level keys: {sorted(self.safe_keys.keys())}"
                )

            allowed_sub = self.safe_keys[top_key]
            if allowed_sub is None:
                continue

            if isinstance(value, dict):
                for sub_key in value:
                    if sub_key not in allowed_sub:
                        raise MutationError(
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
        """Run config-driven validation rules.

        Validation rules format in config:
        {
            "section.key": {"type": "int", "min": 1, "max": 200},
            "section.key2": {"type": "str", "choices": ["a", "b"]},
            "section": {"type": "list"},
        }
        """
        if not self.config.validation_rules:
            return

        for path, rule in self.config.validation_rules.items():
            parts = path.split(".")
            value = config
            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    break  # Key not present, skip validation
            else:
                # Value found, validate it
                expected_type = rule.get("type")
                if expected_type == "int":
                    if not isinstance(value, int):
                        raise MutationError(f"{path} must be an integer, got {type(value).__name__}")
                    if "min" in rule and value < rule["min"]:
                        raise MutationError(f"{path} must be >= {rule['min']}, got {value}")
                    if "max" in rule and value > rule["max"]:
                        raise MutationError(f"{path} must be <= {rule['max']}, got {value}")
                elif expected_type == "str":
                    if "choices" in rule and value not in rule["choices"]:
                        raise MutationError(
                            f"{path} must be one of {rule['choices']}, got {value}"
                        )
                elif expected_type == "list":
                    if not isinstance(value, list):
                        raise MutationError(f"{path} must be a list")
                elif expected_type == "positive_int":
                    if not isinstance(value, int) or value < 1:
                        raise MutationError(f"{path} must be a positive integer")
