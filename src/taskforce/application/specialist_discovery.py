"""
Specialist Discovery Service
=============================

Scans available specialist agents from built-in profiles, configs/custom/,
and plugin directories. Produces a compact index for system prompt injection
without bloating the context window.

Each specialist is represented as a one-liner: name + short description.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SpecialistInfo:
    """Compact specialist descriptor for prompt injection."""

    name: str
    description: str
    source: str  # "builtin" | "custom" | "plugin"


# Built-in specialists always available via the factory.
_BUILTIN_SPECIALISTS: list[SpecialistInfo] = [
    SpecialistInfo(
        name="coding",
        description="Senior Software Engineer for code analysis and development",
        source="builtin",
    ),
    SpecialistInfo(
        name="rag",
        description="Document retrieval and knowledge synthesis (RAG)",
        source="builtin",
    ),
    SpecialistInfo(
        name="wiki",
        description="Wikipedia/wiki research and navigation",
        source="builtin",
    ),
]

class SpecialistDiscovery:
    """Discover and index available specialist agents.

    Scans three sources:
    1. Built-in specialists (coding, rag, wiki)
    2. Custom agents from ``configs/custom/*.yaml``
    3. Plugin agents from ``plugins/*/configs/agents/*.yaml``

    Results are cached after the first scan.

    Args:
        config_dir: Path to the configs directory
            (e.g. ``src/taskforce/configs``).
    """

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = config_dir
        self._cache: list[SpecialistInfo] | None = None
        self._logger = logger.bind(component="specialist_discovery")

    def discover(self) -> list[SpecialistInfo]:
        """Discover all available specialists.

        Returns:
            Sorted list of specialist descriptors. Results are cached.
        """
        if self._cache is not None:
            return self._cache

        specialists: list[SpecialistInfo] = list(_BUILTIN_SPECIALISTS)

        # Custom agents
        specialists.extend(self._scan_custom_agents())

        # Plugin agents
        specialists.extend(self._scan_plugin_agents())

        self._logger.debug(
            "specialists_discovered",
            total=len(specialists),
            builtin=len(_BUILTIN_SPECIALISTS),
            custom=len(specialists) - len(_BUILTIN_SPECIALISTS),
        )

        self._cache = specialists
        return specialists

    def format_for_prompt(self) -> str:
        """Format specialists as compact text for system prompt injection.

        Returns:
            Markdown-formatted list of specialists. Typically < 1000 chars
            even with 15+ specialists.
        """
        specialists = self.discover()
        if not specialists:
            return "No specialists available."

        lines: list[str] = []
        for spec in specialists:
            lines.append(f"- `{spec.name}` - {spec.description}")
        return "\n".join(lines)

    def _scan_custom_agents(self) -> list[SpecialistInfo]:
        """Scan configs/custom/ for custom agent definitions."""
        custom_dir = self._config_dir / "custom"
        if not custom_dir.exists():
            return []

        results: list[SpecialistInfo] = []
        for yaml_file in sorted(custom_dir.glob("*.yaml")):
            info = self._parse_agent_yaml(yaml_file, source="custom")
            if info:
                results.append(info)

        return results

    def _scan_plugin_agents(self) -> list[SpecialistInfo]:
        """Scan plugin directories for agent definitions."""
        results: list[SpecialistInfo] = []

        plugins_dirs: list[Path] = []

        # src/taskforce/plugins/ (sibling of configs/)
        if self._config_dir.name == "configs" and self._config_dir.parent.name == "taskforce":
            candidate = self._config_dir.parent / "plugins"
            if candidate.exists() and candidate not in plugins_dirs:
                plugins_dirs.append(candidate)

        for plugins_dir in plugins_dirs:
            for plugin_dir in sorted(plugins_dir.iterdir()):
                if not plugin_dir.is_dir():
                    continue
                agents_dir = plugin_dir / "configs" / "agents"
                if not agents_dir.exists():
                    continue
                for yaml_file in sorted(agents_dir.glob("*.yaml")):
                    info = self._parse_agent_yaml(yaml_file, source="plugin")
                    if info:
                        results.append(info)

        return results

    def _parse_agent_yaml(self, path: Path, source: str) -> SpecialistInfo | None:
        """Extract name and description from an agent YAML file.

        Tries two strategies:
        1. Look for a ``description`` field in the YAML
        2. Fall back to extracting from the header comment block

        Args:
            path: Path to the YAML file.
            source: Source category ("custom" or "plugin").

        Returns:
            SpecialistInfo if a description could be extracted, None otherwise.
        """
        name = path.stem
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            self._logger.warning("cannot_read_agent_yaml", path=str(path))
            return None

        description = self._extract_description_field(text)
        if not description:
            description = self._extract_comment_description(text)
        if not description:
            description = f"Custom agent: {name}"

        return SpecialistInfo(name=name, description=description, source=source)

    @staticmethod
    def _extract_description_field(text: str) -> str | None:
        """Extract ``description:`` value from YAML text without full parsing."""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("description:"):
                value = stripped[len("description:") :].strip()
                # Remove surrounding quotes if present
                if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]
                return value if value else None
        return None

    @staticmethod
    def _extract_comment_description(text: str) -> str | None:
        """Extract description from the YAML header comment block.

        Takes the second non-empty comment line (first is usually the title).
        Lines starting with ``#`` followed by description text.
        """
        comment_lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                content = stripped.lstrip("#").strip()
                if content:
                    comment_lines.append(content)
            elif stripped:
                break  # End of comment block

        # Return the second descriptive line (first is usually the agent title)
        if len(comment_lines) >= 2:
            desc = comment_lines[1]
            # Clean up common prefixes
            for prefix in ("Specialist agent for ", "Sub-agent for "):
                if desc.lower().startswith(prefix.lower()):
                    desc = desc[len(prefix) :]
                    break
            return desc.rstrip(".")
        if comment_lines:
            return comment_lines[0].rstrip(".")
        return None
