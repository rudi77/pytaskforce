"""
LLM Parameter Mapper

Maps and validates parameters for different LLM model families.
Handles differences between GPT-4 (traditional) and GPT-5/o1/o3 (reasoning) models.
"""

from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


class ParameterMapper:
    """
    Maps parameters for different LLM model families.

    Handles:
    - GPT-4: Traditional parameters (temperature, top_p, max_tokens, etc.)
    - GPT-5/o1/o3: Reasoning parameters (max_completion_tokens only)
    - Azure-specific parameter formatting
    """

    def __init__(
        self,
        model_params: dict[str, dict[str, Any]] | None = None,
        default_params: dict[str, Any] | None = None,
        log_mapping: bool = True,
    ) -> None:
        """
        Initialize the parameter mapper.

        Args:
            model_params: Model-specific parameter overrides
            default_params: Default parameters when no model match
            log_mapping: Whether to log parameter mapping decisions
        """
        self._model_params = model_params or {}
        self._default_params = default_params or {}
        self._log_mapping = log_mapping

    def get_model_parameters(self, model: str) -> dict[str, Any]:
        """
        Get parameters for a specific model.

        Args:
            model: Actual model name

        Returns:
            Model-specific parameters or defaults
        """
        # Check for exact model match
        if model in self._model_params:
            return self._model_params[model].copy()

        # Check for model family match (e.g., "gpt-4" matches "gpt-4-turbo")
        for model_key, params in self._model_params.items():
            if model.startswith(model_key):
                return params.copy()

        # Fallback to defaults
        return self._default_params.copy()

    def map_for_model(self, model: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Map parameters based on model family.

        GPT-4 uses traditional parameters: temperature, top_p, max_tokens, etc.
        GPT-5/o1/o3 uses new parameters: max_completion_tokens only.

        Args:
            model: Actual model name
            params: Input parameters (may contain traditional or new parameters)

        Returns:
            Mapped parameters suitable for the model
        """
        if self._is_reasoning_model(model):
            return self._map_for_reasoning_model(model, params)
        else:
            return self._map_for_traditional_model(model, params)

    def _is_reasoning_model(self, model: str) -> bool:
        """Check if model is a reasoning model (GPT-5/o1/o3)."""
        model_lower = model.lower()
        return any(
            pattern in model_lower for pattern in ["gpt-5", "o1", "o3"]
        )

    def _map_for_reasoning_model(
        self, model: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Map parameters for reasoning models (GPT-5/o1/o3).

        These models only support max_completion_tokens.
        """
        mapped = {}

        # GPT-5 uses max_completion_tokens instead of max_tokens
        if "max_tokens" in params:
            mapped["max_completion_tokens"] = params["max_tokens"]
        if "max_completion_tokens" in params:
            mapped["max_completion_tokens"] = params["max_completion_tokens"]

        # Log ignored parameters
        ignored = [
            k
            for k in params.keys()
            if k not in ["max_tokens", "max_completion_tokens"]
        ]
        if ignored and self._log_mapping:
            logger.info(
                "parameters_ignored_for_reasoning_model",
                model=model,
                ignored_params=ignored,
                hint="GPT-5/o1/o3 models only support max_completion_tokens",
            )

        return mapped

    def _map_for_traditional_model(
        self, model: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Map parameters for traditional models (GPT-4, etc.).

        Filters to only allowed parameters and formats response_format.
        """
        allowed_params = [
            "temperature",
            "top_p",
            "max_tokens",
            "frequency_penalty",
            "presence_penalty",
            "response_format",
        ]
        filtered = {k: v for k, v in params.items() if k in allowed_params}

        # Ensure response_format is properly formatted
        # Azure requires response_format as a simple dict
        if "response_format" in filtered:
            rf = filtered["response_format"]
            if isinstance(rf, dict):
                filtered["response_format"] = {"type": rf.get("type", "json_object")}

        return filtered

    def validate_params(
        self, model: str, params: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """
        Validate parameters for a model.

        Args:
            model: Model name
            params: Parameters to validate

        Returns:
            Tuple of (is_valid, list of warnings)
        """
        warnings = []

        if self._is_reasoning_model(model):
            # Check for unsupported parameters
            unsupported = [
                k
                for k in params.keys()
                if k not in ["max_tokens", "max_completion_tokens"]
            ]
            if unsupported:
                warnings.append(
                    f"Parameters {unsupported} are not supported by reasoning models"
                )

            # Check for required parameters
            if "max_tokens" not in params and "max_completion_tokens" not in params:
                warnings.append(
                    "Reasoning models require max_completion_tokens or max_tokens"
                )

        return len(warnings) == 0, warnings
