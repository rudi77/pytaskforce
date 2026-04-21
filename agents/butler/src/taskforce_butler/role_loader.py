"""Butler role loader -- discovers, loads, and merges role definitions.

A Butler Role is an overlay that defines WHAT the butler is
(persona, sub-agents, tools) while the butler profile defines HOW
it runs (persistence, LLM, scheduler).

Each role is either an ``.agent.md`` file (markdown body + YAML frontmatter,
preferred) or a legacy ``.yaml`` file (``persona_prompt:`` key + YAML). The
loader prefers the markdown variant when both exist.

Search order for role files:
1. ``{package}/configs/roles/{role_name}.agent.md`` (butler-package-bundled, preferred)
2. ``{package}/configs/roles/{role_name}.yaml`` (butler-package-bundled, legacy)
3. ``{package}/configs/butler_roles/{role_name}.yaml`` (legacy framework location)
4. ``{config_dir}/butler_roles/{role_name}.yaml`` (legacy framework location)
5. ``.taskforce/butler_roles/{role_name}.agent.md`` (project-local, preferred)
6. ``.taskforce/butler_roles/{role_name}.yaml`` (project-local, legacy)

See ADR-013 and ADR-017 for design rationale.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import structlog

from taskforce_butler.domain.butler_role import ButlerRole

logger = structlog.get_logger(__name__)


def _butler_package_config_dir() -> Path | None:
    """Locate the configs/ directory shipped with the butler package."""
    try:
        import taskforce_butler

        if taskforce_butler.__file__ is None:
            return None
        package_dir = Path(taskforce_butler.__file__).resolve().parent
        # Typical: .../agents/butler/src/taskforce_butler/__init__.py
        # Configs are at .../agents/butler/configs/
        candidates = [
            package_dir / "configs",
            package_dir.parent / "configs",
            package_dir.parent.parent / "configs",
        ]
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
    except ImportError:
        pass
    return None


class ButlerRoleLoader:
    """Loads and resolves Butler role definitions.

    Args:
        config_dir: Path to the framework configs directory (kept for
            legacy role lookups at ``{config_dir}/butler_roles/``).
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
        self._search_dirs = self._resolve_search_dirs()

    def _resolve_search_dirs(self) -> list[Path]:
        """Build the ordered list of directories searched for role files."""
        dirs: list[Path] = []
        package_dir = _butler_package_config_dir()
        if package_dir is not None:
            dirs.append(package_dir / "roles")
            dirs.append(package_dir / "butler_roles")
        dirs.append(self._config_dir / "butler_roles")
        dirs.append(self._project_dir / "butler_roles")
        dirs.append(self._project_dir / "roles")
        return dirs

    def load(self, role_name: str) -> ButlerRole:
        """Load a role by name. Prefers ``.agent.md`` over ``.yaml``."""
        for search_dir in self._search_dirs:
            md_path = search_dir / f"{role_name}.agent.md"
            if md_path.is_file():
                logger.info(
                    "butler_role.loaded",
                    role=role_name,
                    path=str(md_path),
                    format="agent_md",
                )
                return self._load_agent_md(md_path, role_name)

            yaml_path = search_dir / f"{role_name}.yaml"
            if yaml_path.is_file():
                logger.info(
                    "butler_role.loaded",
                    role=role_name,
                    path=str(yaml_path),
                    format="yaml",
                )
                return self._load_yaml(yaml_path, role_name)

        searched: list[str] = []
        for d in self._search_dirs:
            searched.append(str(d / f"{role_name}.agent.md"))
            searched.append(str(d / f"{role_name}.yaml"))
        raise FileNotFoundError(f"Butler role '{role_name}' not found. Searched: {searched}")

    def _load_agent_md(self, path: Path, role_name: str) -> ButlerRole:
        """Parse a role from an ``.agent.md`` file."""
        from taskforce.application.agent_file_loader import load_agent_md

        agent_file = load_agent_md(path)
        data = dict(agent_file.frontmatter)
        # Body of the markdown is the persona prompt.
        # Wrap with leading/trailing newlines to match the legacy
        # ``persona_prompt:`` YAML-block-scalar whitespace convention.
        body = agent_file.body.strip("\n")
        data["persona_prompt"] = "\n" + body + "\n" if body else ""
        if "name" not in data:
            data["name"] = role_name
        return ButlerRole.from_dict(data)

    def _load_yaml(self, path: Path, role_name: str) -> ButlerRole:
        """Parse a role from a legacy YAML file."""
        import yaml  # type: ignore[import-untyped]

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "name" not in data:
            data["name"] = role_name
        return ButlerRole.from_dict(data)

    def list_available(self) -> list[ButlerRole]:
        """List all available role definitions."""
        roles: list[ButlerRole] = []
        seen_names: set[str] = set()

        for search_dir in self._search_dirs:
            if not search_dir.is_dir():
                continue
            # Collect stems from both file types, in deterministic order.
            stems: list[str] = []
            for md_file in sorted(search_dir.glob("*.agent.md")):
                # Path.stem on "foo.agent.md" returns "foo.agent" (splitext keeps
                # only the last extension). Strip the trailing ".agent" ourselves.
                name = md_file.name[: -len(".agent.md")]
                stems.append(name)
            for yaml_file in sorted(search_dir.glob("*.yaml")):
                stems.append(yaml_file.stem)

            for stem in stems:
                if stem in seen_names:
                    continue
                try:
                    role = self.load(stem)
                    roles.append(role)
                    seen_names.add(stem)
                except Exception as exc:
                    logger.warning(
                        "butler_role.list_skip",
                        role=stem,
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
        """
        merged = copy.deepcopy(base_config)

        merged["specialist"] = None
        merged["system_prompt"] = role.persona_prompt

        if role.sub_agents:
            merged["sub_agents"] = list(role.sub_agents)
        if role.tools:
            merged["tools"] = list(role.tools)

        if role.event_sources:
            existing_sources = merged.get("event_sources", []) or []
            merged["event_sources"] = existing_sources + list(role.event_sources)
        if role.rules:
            existing_rules = merged.get("rules", []) or []
            merged["rules"] = existing_rules + list(role.rules)
        if role.mcp_servers:
            existing_mcp = merged.get("mcp_servers", []) or []
            merged["mcp_servers"] = existing_mcp + list(role.mcp_servers)

        merged["_role_name"] = role.name
        merged["_role_description"] = role.description

        logger.info(
            "butler_role.merged",
            role=role.name,
            sub_agents=len(role.sub_agents),
            tools=len(role.tools),
        )

        return merged
