"""Agent role loader — discovers, loads, and merges role definitions.

An :class:`taskforce.core.domain.agent_role.AgentRole` is an overlay that
defines WHAT an agent is (persona, sub-agents, tools) while the agent
profile defines HOW it runs (persistence, LLM, scheduler).

Each role is either an ``.agent.md`` file (markdown body + YAML frontmatter,
preferred) or a legacy ``.yaml`` file (``persona_prompt:`` key + YAML). The
loader prefers the markdown variant when both exist.

The loader is constructed with an explicit ``search_dirs`` sequence so it
is agent-agnostic — callers (e.g. an :class:`AgentDaemon`) decide which
directories to probe. The Butler daemon passes the union of its package
``configs/roles/`` directory and the project-local ``.taskforce/roles/``
override.

See ADR-013, ADR-017, and ADR-027 (which generalises this from a
Butler-only helper to a framework primitive).
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import structlog

from taskforce.core.domain.agent_role import AgentRole

logger = structlog.get_logger(__name__)


class AgentRoleLoader:
    """Loads and resolves :class:`AgentRole` definitions from disk.

    Args:
        search_dirs: Ordered list of directories to probe for role files.
            The first matching ``<role>.agent.md`` or ``<role>.yaml`` wins.
    """

    def __init__(self, search_dirs: Sequence[Path]) -> None:
        self._search_dirs: list[Path] = list(search_dirs)

    def load(self, role_name: str) -> AgentRole:
        """Load a role by name. Prefers ``.agent.md`` over ``.yaml``.

        Raises:
            FileNotFoundError: If no matching role file is found in any
                search directory.
        """
        for search_dir in self._search_dirs:
            md_path = search_dir / f"{role_name}.agent.md"
            if md_path.is_file():
                logger.info(
                    "agent_role.loaded",
                    role=role_name,
                    path=str(md_path),
                    format="agent_md",
                )
                return self._load_agent_md(md_path, role_name)

            yaml_path = search_dir / f"{role_name}.yaml"
            if yaml_path.is_file():
                logger.info(
                    "agent_role.loaded",
                    role=role_name,
                    path=str(yaml_path),
                    format="yaml",
                )
                return self._load_yaml(yaml_path, role_name)

        searched: list[str] = []
        for d in self._search_dirs:
            searched.append(str(d / f"{role_name}.agent.md"))
            searched.append(str(d / f"{role_name}.yaml"))
        raise FileNotFoundError(f"Agent role '{role_name}' not found. Searched: {searched}")

    def _load_agent_md(self, path: Path, role_name: str) -> AgentRole:
        """Parse a role from an ``.agent.md`` file."""
        from taskforce.application.agent_file_loader import load_agent_md

        agent_file = load_agent_md(path)
        data = dict(agent_file.frontmatter)
        # Body of the markdown is the persona prompt. Wrap with leading/
        # trailing newlines to match the legacy ``persona_prompt:`` YAML-
        # block-scalar whitespace convention.
        body = agent_file.body.strip("\n")
        data["persona_prompt"] = "\n" + body + "\n" if body else ""
        if "name" not in data:
            data["name"] = role_name
        return AgentRole.from_dict(data)

    def _load_yaml(self, path: Path, role_name: str) -> AgentRole:
        """Parse a role from a legacy YAML file."""
        import yaml  # type: ignore[import-untyped]

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "name" not in data:
            data["name"] = role_name
        return AgentRole.from_dict(data)

    def list_available(self) -> list[AgentRole]:
        """List all available role definitions across the search directories.

        First match (per role name) wins — later occurrences are skipped so
        a project-local override hides the package default.
        """
        roles: list[AgentRole] = []
        seen_names: set[str] = set()

        for search_dir in self._search_dirs:
            if not search_dir.is_dir():
                continue
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
                        "agent_role.list_skip",
                        role=stem,
                        error=str(exc),
                    )
        return roles

    def merge_into_config(
        self,
        base_config: dict[str, Any],
        role: AgentRole,
    ) -> dict[str, Any]:
        """Merge a role definition into the agent base configuration.

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
            "agent_role.merged",
            role=role.name,
            sub_agents=len(role.sub_agents),
            tools=len(role.tools),
        )

        return merged
