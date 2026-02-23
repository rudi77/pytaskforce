"""
LLM configuration loading and model resolution.

Internal helper for LiteLLMService. Not part of the public API.

Handles:
- YAML config file resolution and loading (sync + async)
- Model alias resolution from config
- Per-model parameter merging with defaults
- Retry policy extraction
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiofiles
import structlog
import yaml

logger = structlog.get_logger(__name__)


@dataclass
class RetryPolicy:
    """Retry policy configuration for LLM API calls."""

    max_attempts: int = 3
    backoff_multiplier: float = 2.0
    timeout: int = 60


class LLMConfigLoader:
    """Loads and manages LLM configuration from YAML files.

    Provides both synchronous (for ``__init__``) and asynchronous config
    loading, model alias resolution, and parameter merging.

    Args:
        config_path: Path to the YAML configuration file.

    Raises:
        FileNotFoundError: If the config file cannot be found.
        ValueError: If the config is empty or missing required sections.
    """

    def __init__(self, config_path: str) -> None:
        self.logger = structlog.get_logger(__name__)
        self._config_path: str = config_path
        self._config_loaded: bool = False

        # Initialize attributes with defaults so that attribute access before
        # async init still works.
        self.default_model: str = "main"
        self.models: dict[str, str] = {}
        self.model_params: dict[str, dict[str, Any]] = {}
        self.default_params: dict[str, Any] = {}
        self.retry_policy: RetryPolicy = RetryPolicy()
        self.logging_config: dict[str, Any] = {}
        self.tracing_config: dict[str, Any] = {}
        self.routing_config: dict[str, Any] = {}

        # Eagerly resolve and validate the config file path so that
        # FileNotFoundError is raised immediately (preserving existing behavior).
        self._resolved_config_path: Path = self._resolve_config_path(config_path)

        # Synchronous fallback load for backward compatibility — existing callers
        # construct the service and immediately access .models, .routing_config, etc.
        self._load_config_sync(self._resolved_config_path)

    @property
    def config_loaded(self) -> bool:
        """Whether the configuration has been loaded."""
        return self._config_loaded

    def _resolve_config_path(self, config_path: str) -> Path:
        """Resolve and validate the configuration file path.

        Args:
            config_path: Raw path string from the caller.

        Returns:
            Resolved ``Path`` object pointing to an existing file.

        Raises:
            FileNotFoundError: If no matching config file is found.
        """
        config_file = Path(config_path)

        # Backward compatibility: try src/taskforce_extensions/configs/ as fallback
        if (
            not config_file.exists()
            and not config_file.is_absolute()
            and "configs/" in str(config_path)
        ):
            project_root = Path(__file__).parent.parent.parent.parent.parent
            new_path = project_root / "src" / "taskforce_extensions" / config_path
            if new_path.exists():
                config_file = new_path

        if not config_file.exists():
            raise FileNotFoundError(f"LLM config not found: {config_path}")

        return config_file

    def _load_config_sync(self, config_file: Path) -> None:
        """Load configuration synchronously (fallback for non-async contexts).

        This is called from ``__init__`` so that attribute access on a freshly
        constructed instance works immediately.  Prefer ``ensure_config_loaded``
        in async code paths.

        Args:
            config_file: Validated path to the YAML config file.

        Raises:
            ValueError: If config is empty or missing the ``models`` section.
        """
        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        self._apply_config(config)

    async def load_config_async(self) -> None:
        """Load configuration asynchronously using ``aiofiles``.

        Reads the YAML file without blocking the event loop and applies the
        parsed configuration via ``_apply_config``.
        """
        async with aiofiles.open(self._resolved_config_path, encoding="utf-8") as f:
            raw = await f.read()
        config = yaml.safe_load(raw)
        self._apply_config(config)

    def _apply_config(self, config: Any) -> None:
        """Validate and apply a parsed YAML config dict to instance attributes.

        Args:
            config: Parsed YAML dictionary (may be ``None`` for empty files).

        Raises:
            ValueError: If config is empty or missing the ``models`` section.
        """
        if config is None:
            raise ValueError(f"Config file is empty or invalid: {self._config_path}")

        self.default_model = config.get("default_model", "main")
        self.models = config.get("models", {})
        self.model_params = config.get("model_params", {})
        self.default_params = config.get("default_params", {})

        if not self.models:
            raise ValueError("Config must define at least one model in 'models' section")

        self._apply_retry_policy(config)
        self.logging_config = config.get("logging", {})
        self.tracing_config = config.get("tracing", {})
        self.routing_config = config.get("routing", {})
        self._config_loaded = True

        self.logger.info(
            "llm_config_loaded",
            default_model=self.default_model,
            model_aliases=list(self.models.keys()),
        )

    def _apply_retry_policy(self, config: dict[str, Any]) -> None:
        """Extract and apply retry policy from config.

        Args:
            config: Parsed YAML configuration dictionary.
        """
        retry_cfg = config.get("retry", config.get("retry_policy", {}))
        self.retry_policy = RetryPolicy(
            max_attempts=retry_cfg.get("max_attempts", 3),
            backoff_multiplier=retry_cfg.get("backoff_multiplier", 2.0),
            timeout=retry_cfg.get("timeout", 60),
        )

    async def ensure_config_loaded(self) -> None:
        """Ensure configuration is loaded, using async I/O if not yet loaded.

        Safe to call multiple times; only the first call performs I/O.
        """
        if not self._config_loaded:
            await self.load_config_async()

    def resolve_model(self, model_alias: str | None) -> str:
        """Resolve model alias to LiteLLM model string.

        If the alias exists in the models dict, returns the mapped value.
        Otherwise returns the alias as-is (allows direct model strings).

        Args:
            model_alias: Model alias (e.g., "main") or None for default.

        Returns:
            LiteLLM model string (e.g., "gpt-4.1", "anthropic/claude-sonnet-4-20250514").
        """
        alias = model_alias or self.default_model
        resolved = self.models.get(alias, alias)
        self.logger.debug("model_resolved", alias=alias, resolved=resolved)
        return resolved

    def get_params(self, model_alias: str, **kwargs: Any) -> dict[str, Any]:
        """Build parameter dict by merging defaults, model params, and call kwargs.

        Merge order (later overrides earlier):
        1. default_params from config
        2. model_params for the resolved model or alias
        3. kwargs from the caller

        Args:
            model_alias: The alias used for lookup in model_params.
            **kwargs: Additional parameters from the caller.

        Returns:
            Merged parameter dictionary.
        """
        params: dict[str, Any] = {**self.default_params}

        # Try exact alias match first, then resolved model name
        resolved = self.models.get(model_alias, model_alias)
        if model_alias in self.model_params:
            params.update(self.model_params[model_alias])
        elif resolved in self.model_params:
            params.update(self.model_params[resolved])
        else:
            # Try prefix match (e.g., "gpt-4" matches "gpt-4-turbo")
            for key, model_cfg in self.model_params.items():
                if resolved.startswith(key):
                    params.update(model_cfg)
                    break

        # Caller kwargs override everything
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return params
