"""Butler role loader — discovers, loads, and merges role definitions.

A Butler Role is an overlay YAML that defines WHAT the butler is
(persona, sub-agents, tools) while the butler profile defines HOW
it runs (persistence, LLM, scheduler).

Search order for role files:
1. ``{config_dir}/butler_roles/{role_name}.yaml`` (package-bundled)
2. ``.taskforce/butler_roles/{role_name}.yaml`` (project-local)

See ADR-013 for design rationale.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import structlog

from taskforce.core.domain.butler_role import ButlerRole

logger = structlog.get_logger(__name__)


class ButlerRoleLoader:
    """Loads and resolves Butler role definitions from YAML files.

    Args:
        config_dir: Path to the package configs directory
            (``src/taskforce/configs``).
        project_dir: Path to the project-local ``.taskforce`` directory.
            Defaults to ``.taskforce`` in the current working directory.
    """

    def __init__(
        self,
        config_dir: Path,
        project_dir: Path | None = None,
    ) -> None:
        self._config_dir = config_dir
        self._project_dir = project_dir or Path(".taskforce")
        self._search_dirs = [
            config_dir / "butler_roles",
            self._project_dir / "butler_roles",
        ]

    def load(self, role_name: str) -> ButlerRole:
        """Load a role by name.

        Args:
            role_name: Short name of the role (e.g. ``"accountant"``).

        Returns:
            Parsed ``ButlerRole`` instance.

        Raises:
            FileNotFoundError: If no role YAML was found in any search path.
        """
        import yaml  # type: ignore[import-untyped]

        for search_dir in self._search_dirs:
            role_path = search_dir / f"{role_name}.yaml"
            if role_path.is_file():
                logger.info(
                    "butler_role.loaded",
                    role=role_name,
                    path=str(role_path),
                )
                with open(role_path) as f:
                    data = yaml.safe_load(f) or {}
                # Ensure name is set from the file if not in YAML
                if "name" not in data:
                    data["name"] = role_name
                return ButlerRole.from_dict(data)

        searched = [str(d / f"{role_name}.yaml") for d in self._search_dirs]
        raise FileNotFoundError(f"Butler role '{role_name}' not found. Searched: {searched}")

    def list_available(self) -> list[ButlerRole]:
        """List all available role definitions.

        Returns:
            List of ``ButlerRole`` instances (loaded with full data).
        """
        roles: list[ButlerRole] = []
        seen_names: set[str] = set()

        for search_dir in self._search_dirs:
            if not search_dir.is_dir():
                continue
            for yaml_file in sorted(search_dir.glob("*.yaml")):
                role_name = yaml_file.stem
                if role_name in seen_names:
                    continue
                try:
                    role = self.load(role_name)
                    roles.append(role)
                    seen_names.add(role_name)
                except Exception as exc:
                    logger.warning(
                        "butler_role.list_skip",
                        role=role_name,
                        error=str(exc),
                    )
        return roles

    def merge_into_config(
        self,
        base_config: dict[str, Any],
        role: ButlerRole,
    ) -> dict[str, Any]:
        """Merge a role definition into the butler base configuration.

        Merge semantics:
        - ``sub_agents``: **REPLACED** by role (role defines the complete set).
        - ``tools``: **REPLACED** by role.
        - ``event_sources``: **APPENDED** (base + role).
        - ``rules``: **APPENDED** (base + role).
        - ``mcp_servers``: **APPENDED** (base + role).
        - ``system_prompt``: **SET** from ``role.persona_prompt``.
        - ``specialist``: **SET** to ``None`` (role replaces specialist lookup).

        Infrastructure keys (persistence, llm, scheduler, security, etc.)
        always come from the base config.

        Args:
            base_config: The butler profile YAML as a dict.
            role: The role to merge in.

        Returns:
            New config dict with role overrides applied.
        """
        merged = copy.deepcopy(base_config)

        # Replace identity
        merged["specialist"] = None
        merged["system_prompt"] = role.persona_prompt

        # Replace sub-agents and tools
        if role.sub_agents:
            merged["sub_agents"] = list(role.sub_agents)
        if role.tools:
            merged["tools"] = list(role.tools)

        # Append event sources, rules, mcp_servers
        if role.event_sources:
            existing_sources = merged.get("event_sources", []) or []
            merged["event_sources"] = existing_sources + list(role.event_sources)
        if role.rules:
            existing_rules = merged.get("rules", []) or []
            merged["rules"] = existing_rules + list(role.rules)
        if role.mcp_servers:
            existing_mcp = merged.get("mcp_servers", []) or []
            merged["mcp_servers"] = existing_mcp + list(role.mcp_servers)

        # Stash role metadata for status reporting
        merged["_role_name"] = role.name
        merged["_role_description"] = role.description

        logger.info(
            "butler_role.merged",
            role=role.name,
            sub_agents=len(role.sub_agents),
            tools=len(role.tools),
        )

        return merged
