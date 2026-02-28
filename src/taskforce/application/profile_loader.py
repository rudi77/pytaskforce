"""
Profile Loader
==============

Loads and resolves YAML configuration profiles for agent creation.
Extracted from AgentFactory to enforce single-responsibility.

Responsibilities:
- Load profile YAML files from standard and custom directories
- Validate profiles against Pydantic schema on load
- Provide sensible defaults when no profile exists
- Merge plugin configurations with base profiles
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import structlog
import yaml

from taskforce.core.domain.config_schema import (
    ConfigValidationError,
    validate_profile_config,
)

logger = structlog.get_logger(__name__)


# Default tool names used when no profile or inline tools are specified.
DEFAULT_TOOL_NAMES: list[str] = [
    "web_search",
    "web_fetch",
    "file_read",
    "file_write",
    "python",
    "powershell",
    "ask_user",
]

# Minimal fallback config when no ``dev.yaml`` profile exists.
_FALLBACK_CONFIG: dict[str, Any] = {
    "persistence": {"type": "file", "work_dir": ".taskforce"},
    "llm": {
        "config_path": "src/taskforce/configs/llm_config.yaml",
        "default_model": "main",
    },
    "agent": {"max_steps": 30},
    "logging": {"level": "WARNING"},
}


class ProfileLoader:
    """Load and resolve YAML configuration profiles.

    Encapsulates the profile search order (standard → custom → defaults)
    and provides a single source of truth for default configuration.

    Args:
        config_dir: Root directory containing profile YAML files.
    """

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = config_dir
        self._logger = logger.bind(component="profile_loader")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, profile: str) -> dict[str, Any]:
        """Load a profile by name.

        Search order:
        1. ``{config_dir}/{profile}.yaml``
        2. ``{config_dir}/custom/{profile}.yaml``

        Args:
            profile: Profile name (e.g. ``"dev"``, ``"coding_agent"``).

        Returns:
            Parsed YAML configuration dictionary.

        Raises:
            FileNotFoundError: If no matching YAML file is found.
        """
        profile_path = self._config_dir / f"{profile}.yaml"

        if not profile_path.exists():
            custom_path = self._config_dir / "custom" / f"{profile}.yaml"
            if custom_path.exists():
                self._logger.debug(
                    "profile_using_custom_agent",
                    profile=profile,
                    custom_path=str(custom_path),
                )
                profile_path = custom_path
            else:
                raise FileNotFoundError(
                    f"Profile not found: {profile_path} or {custom_path}"
                )

        with open(profile_path) as f:
            config: dict[str, Any] = yaml.safe_load(f)

        # Validate against Pydantic schema — logs a warning on failure
        # but does NOT reject the config to stay backwards-compatible.
        try:
            validate_profile_config(config, file_path=profile_path)
        except ConfigValidationError as exc:
            self._logger.warning(
                "profile_validation_warning",
                profile=profile,
                path=str(profile_path),
                error=str(exc),
            )

        self._logger.debug(
            "profile_loaded",
            profile=profile,
            config_keys=list(config.keys()),
        )
        return config

    def load_safe(self, profile: str) -> dict[str, Any]:
        """Load a profile, falling back to defaults on ``FileNotFoundError``.

        Args:
            profile: Profile name.

        Returns:
            Parsed configuration, or :data:`_FALLBACK_CONFIG` if not found.
        """
        try:
            return self.load(profile)
        except FileNotFoundError:
            self._logger.debug(
                "profile_not_found_using_defaults",
                profile=profile,
            )
            return copy.deepcopy(_FALLBACK_CONFIG)

    def get_defaults(self) -> dict[str, Any]:
        """Return default configuration (loads ``dev`` or falls back).

        Returns:
            Configuration dictionary.
        """
        return self.load_safe("dev")

    # ------------------------------------------------------------------
    # Plugin config merging
    # ------------------------------------------------------------------

    def merge_plugin_config(
        self,
        base_config: dict[str, Any],
        plugin_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge a plugin configuration into a base profile.

        Merge semantics (by key):

        * ``agent`` — shallow dict update (plugin overrides individual keys)
        * ``context_policy`` — full replace
        * ``specialist`` — full replace
        * ``persistence.work_dir`` — overridden if plugin specifies it
        * ``mcp_servers`` — concatenated (base + plugin)
        * ``context_management`` — shallow dict update
        * ``llm`` — shallow dict update (plugin can override ``default_model``
          and ``config_path`` to use its own LLM configuration)

        The ``persistence.type`` key always comes from *base_config* for
        security (prevents plugins from switching storage backends).

        Note: ``llm`` overrides are allowed because plugins are user-installed
        and may legitimately need their own model provider configuration
        (e.g. an Anthropic-based plugin vs. an Azure-based base profile).

        Args:
            base_config: Base profile configuration.
            plugin_config: Plugin-specific overrides.

        Returns:
            Deep-copied merged configuration.
        """
        merged = copy.deepcopy(base_config)

        if "agent" in plugin_config:
            merged.setdefault("agent", {}).update(plugin_config["agent"])

        if "context_policy" in plugin_config:
            merged["context_policy"] = plugin_config["context_policy"]

        if "specialist" in plugin_config:
            merged["specialist"] = plugin_config["specialist"]

        if plugin_config.get("persistence", {}).get("work_dir"):
            merged.setdefault("persistence", {})["work_dir"] = plugin_config[
                "persistence"
            ]["work_dir"]

        if "mcp_servers" in plugin_config:
            base_mcp = merged.get("mcp_servers", [])
            merged["mcp_servers"] = base_mcp + plugin_config["mcp_servers"]

        if "context_management" in plugin_config:
            merged.setdefault("context_management", {}).update(
                plugin_config["context_management"]
            )

        if "memory" in plugin_config:
            merged.setdefault("memory", {}).update(plugin_config["memory"])

        if "llm" in plugin_config:
            merged.setdefault("llm", {}).update(plugin_config["llm"])

        return merged
