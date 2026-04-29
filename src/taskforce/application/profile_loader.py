"""
Profile Loader
==============

Loads and resolves agent configuration profiles. Supports two file formats:

* **``{name}.agent.md``** — markdown with YAML frontmatter. Frontmatter carries
  identity + capabilities (tools, sub_agents, mcp_servers, skills, ...) and an
  optional ``technical:`` block plus ``extends:`` preset references. The body
  becomes the system prompt.
* **``{name}.yaml``** — legacy flat YAML profile. Kept for backward
  compatibility; fully supported until all agents migrate.

Responsibilities:
- Search standard and extra (agent-package) config directories.
- Apply framework ``defaults.yaml`` as baseline for ``.agent.md`` files.
- Resolve ``extends:`` chains against ``presets/*.yaml``.
- Validate the resulting dict against the Pydantic schema (warning on failure).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import structlog
import yaml

from taskforce.application.agent_file_loader import (
    agent_file_to_config,
    load_agent_md,
)
from taskforce.application.config_schema import (
    ConfigValidationError,
    validate_profile_config,
)

logger = structlog.get_logger(__name__)

# ------------------------------------------------------------------
# Module-level extra config directory registry
# ------------------------------------------------------------------

_extra_config_dirs: list[Path] = []


def register_config_dir(path: Path | str) -> None:
    """Register an additional directory to search for profile files.

    Agent packages (e.g. ``taskforce_butler``, ``taskforce_coding_agent``)
    call this at CLI startup so their shipped configs are discoverable by
    :class:`ProfileLoader`.

    Duplicate paths are silently ignored.

    Args:
        path: Absolute or relative path to a directory containing
            ``*.agent.md`` or ``*.yaml`` profile files.
    """
    resolved = Path(path).resolve()
    if resolved not in _extra_config_dirs:
        _extra_config_dirs.append(resolved)
        logger.debug("config_dir_registered", path=str(resolved))


def get_extra_config_dirs() -> list[Path]:
    """Return the list of registered extra config directories."""
    return list(_extra_config_dirs)


def clear_extra_config_dirs() -> None:
    """Remove all registered extra config directories (useful in tests)."""
    _extra_config_dirs.clear()


# Default tool names used when no profile or inline tools are specified.
DEFAULT_TOOL_NAMES: list[str] = [
    "web_search",
    "web_fetch",
    "file_read",
    "file_write",
    "python",
    "shell",
    "ask_user",
]

# Minimal fallback used when ``configs/defaults.yaml`` cannot be located
# (e.g. stripped-down installs). Kept as module-level constant for
# backward compatibility with tests and tooling that reference it.
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
    """Load and resolve agent configuration profiles.

    Search order for ``load(name)``:

    1. ``{primary}/ {name}.agent.md``
    2. ``{primary}/ {name}.yaml``
    3. ``{primary}/custom/{name}.agent.md``
    4. ``{primary}/custom/{name}.yaml``
    5. Same probe sequence in each registered extra directory.

    ``.agent.md`` files are post-processed: framework defaults (``defaults.yaml``)
    are applied first, then any ``extends:`` presets, then the frontmatter, then
    the ``technical:`` block flattened onto the top level, and finally the body
    is stored as ``system_prompt``.
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        if config_dir is None:
            config_dir = self._resolve_default_config_dir()
        self._config_dir = config_dir
        self._logger = logger.bind(component="profile_loader")

    @staticmethod
    def _resolve_default_config_dir() -> Path:
        """Resolve the default config directory."""
        from taskforce.core.utils.paths import get_base_path

        base_path = get_base_path()
        new_config_dir = base_path / "src" / "taskforce" / "configs"
        if new_config_dir.exists():
            return new_config_dir
        old_config_dir = base_path / "configs"
        if old_config_dir.exists():
            return old_config_dir
        return new_config_dir

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _probe_dir(config_dir: Path, profile: str) -> Path | None:
        """Check a config directory for a profile file.

        Probes in order: ``{profile}.agent.md`` → ``{profile}.yaml`` →
        ``custom/{profile}.agent.md`` → ``custom/{profile}.yaml``.

        Returns:
            The resolved path if found, otherwise ``None``.
        """
        candidates = [
            config_dir / f"{profile}.agent.md",
            config_dir / f"{profile}.yaml",
            config_dir / "custom" / f"{profile}.agent.md",
            config_dir / "custom" / f"{profile}.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _find_profile_path(self, profile: str) -> Path | None:
        """Search all config directories for a profile file."""
        result = self._probe_dir(self._config_dir, profile)
        if result is not None:
            return result

        for extra_dir in _extra_config_dirs:
            result = self._probe_dir(extra_dir, profile)
            if result is not None:
                self._logger.debug(
                    "profile_found_in_extra_dir",
                    profile=profile,
                    config_dir=str(extra_dir),
                )
                return result
        return None

    def _preset_dirs(self) -> list[Path]:
        """Directories searched when resolving ``extends:`` references."""
        dirs: list[Path] = []
        primary_presets = self._config_dir / "presets"
        if primary_presets.is_dir():
            dirs.append(primary_presets)
        for extra_dir in _extra_config_dirs:
            presets_dir = extra_dir / "presets"
            if presets_dir.is_dir():
                dirs.append(presets_dir)
        return dirs

    def _load_defaults(self) -> dict[str, Any]:
        """Load ``configs/defaults.yaml`` as baseline config, or ``{}``."""
        defaults_path = self._config_dir / "defaults.yaml"
        if not defaults_path.is_file():
            return {}
        with open(defaults_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            self._logger.warning("defaults_yaml_not_a_mapping", path=str(defaults_path))
            return {}
        return data

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, profile: str) -> dict[str, Any]:
        """Load a profile by name.

        Args:
            profile: Profile name (e.g. ``"butler"``, ``"coding_agent"``).

        Returns:
            Parsed configuration dictionary.

        Raises:
            FileNotFoundError: If no matching file is found.
        """
        profile_path = self._find_profile_path(profile)
        if profile_path is None:
            searched = [str(self._config_dir)]
            searched.extend(str(d) for d in _extra_config_dirs)
            raise FileNotFoundError(
                f"Profile '{profile}' not found. Searched: {', '.join(searched)}"
            )

        if profile_path.name.endswith(".agent.md"):
            agent_file = load_agent_md(profile_path)
            config = agent_file_to_config(
                agent_file,
                preset_dirs=self._preset_dirs(),
                defaults=self._load_defaults(),
            )
        else:
            with open(profile_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

        if not isinstance(config, dict):
            raise ValueError(f"Profile '{profile}' did not parse to a mapping: {profile_path}")

        # Validate against Pydantic schema — warn on failure, do not reject.
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
            path=str(profile_path),
            config_keys=list(config.keys()),
        )
        return config

    def load_safe(self, profile: str) -> dict[str, Any]:
        """Load a profile, falling back to defaults on ``FileNotFoundError``."""
        try:
            return self.load(profile)
        except FileNotFoundError:
            self._logger.debug(
                "profile_not_found_using_defaults",
                profile=profile,
            )
            return self.get_defaults()

    def get_defaults(self) -> dict[str, Any]:
        """Return the framework defaults dict.

        Loads ``configs/defaults.yaml`` if present, else returns a minimal
        hard-coded fallback so the framework still starts in a broken repo.
        """
        data = self._load_defaults()
        if data:
            return copy.deepcopy(data)
        return copy.deepcopy(_FALLBACK_CONFIG)

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
        """
        merged = copy.deepcopy(base_config)

        if "agent" in plugin_config:
            merged.setdefault("agent", {}).update(plugin_config["agent"])

        if "context_policy" in plugin_config:
            merged["context_policy"] = plugin_config["context_policy"]

        if "specialist" in plugin_config:
            merged["specialist"] = plugin_config["specialist"]

        if plugin_config.get("persistence", {}).get("work_dir"):
            merged.setdefault("persistence", {})["work_dir"] = plugin_config["persistence"][
                "work_dir"
            ]

        if "mcp_servers" in plugin_config:
            base_mcp = merged.get("mcp_servers", [])
            merged["mcp_servers"] = base_mcp + plugin_config["mcp_servers"]

        if "context_management" in plugin_config:
            merged.setdefault("context_management", {}).update(plugin_config["context_management"])

        if "memory" in plugin_config:
            merged.setdefault("memory", {}).update(plugin_config["memory"])

        if "llm" in plugin_config:
            merged.setdefault("llm", {}).update(plugin_config["llm"])

        return merged

    # ------------------------------------------------------------------
    # Discovery (used by management UI / API)
    # ------------------------------------------------------------------

    # Names that should not be surfaced as profiles even if they live in
    # one of the searched directories.
    _RESERVED_BASENAMES: tuple[str, ...] = (
        "defaults",
        "llm_config",
        "pricing",
    )

    @staticmethod
    def _profile_name_from_path(path: Path) -> str:
        """Strip extension(s) from a profile filename to return its name."""
        if path.name.endswith(".agent.md"):
            return path.name[: -len(".agent.md")]
        return path.stem

    def _all_search_dirs(self) -> list[Path]:
        """Return all directories searched for profile files (de-duplicated)."""
        seen: set[Path] = set()
        result: list[Path] = []
        for candidate in [self._config_dir, *_extra_config_dirs]:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            result.append(candidate)
        return result

    def list_profiles(self) -> list[dict[str, Any]]:
        """Discover all profile files in the framework + extra config dirs.

        Returns one entry per *unique* profile name. When the same name
        appears in multiple search directories, the first hit wins (this
        matches the resolution order of :meth:`load`).

        Each entry is a plain dict with keys:

        * ``name`` — profile name (e.g. ``"butler"``, ``"accountant"``)
        * ``path`` — absolute path to the source file
        * ``format`` — ``"agent_md"`` or ``"yaml"``
        * ``description`` — best-effort description (``description`` field
          or first non-empty line of the body), may be empty
        * ``specialist`` — value of the top-level ``specialist`` field if
          present, else ``None``
        * ``is_custom`` — ``True`` if the file lives under a ``custom/``
          subdirectory
        """
        seen: set[str] = set()
        results: list[dict[str, Any]] = []

        for search_dir in self._all_search_dirs():
            if not search_dir.is_dir():
                continue
            for candidate_dir, is_custom in [
                (search_dir, False),
                (search_dir / "custom", True),
                (search_dir / "roles", False),
            ]:
                if not candidate_dir.is_dir():
                    continue
                for entry in sorted(candidate_dir.iterdir()):
                    if not entry.is_file():
                        continue
                    if not (entry.name.endswith(".agent.md") or entry.suffix == ".yaml"):
                        continue
                    name = self._profile_name_from_path(entry)
                    if name in self._RESERVED_BASENAMES:
                        continue
                    if name in seen:
                        continue
                    seen.add(name)
                    summary = self._summarize_profile(entry)
                    summary["name"] = name
                    summary["path"] = str(entry)
                    summary["is_custom"] = is_custom
                    results.append(summary)

        results.sort(key=lambda item: item["name"])
        return results

    @staticmethod
    def _summarize_profile(path: Path) -> dict[str, Any]:
        """Extract lightweight summary fields without full schema validation."""
        result: dict[str, Any] = {
            "format": "agent_md" if path.name.endswith(".agent.md") else "yaml",
            "description": "",
            "specialist": None,
            "name_label": None,
        }
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return result

        if path.name.endswith(".agent.md"):
            frontmatter, body = _split_agent_md_frontmatter(text)
            data: dict[str, Any] = {}
            if frontmatter:
                try:
                    parsed = yaml.safe_load(frontmatter) or {}
                    if isinstance(parsed, dict):
                        data = parsed
                except yaml.YAMLError:
                    data = {}
            result["description"] = str(data.get("description") or "").strip()
            result["specialist"] = data.get("specialist")
            result["name_label"] = data.get("name")
            if not result["description"] and body:
                first_line = next(
                    (line.strip() for line in body.splitlines() if line.strip()),
                    "",
                )
                result["description"] = first_line[:200]
        else:
            try:
                parsed = yaml.safe_load(text) or {}
            except yaml.YAMLError:
                parsed = {}
            if isinstance(parsed, dict):
                result["description"] = str(parsed.get("description") or "").strip()
                result["specialist"] = parsed.get("specialist")
                result["name_label"] = parsed.get("name")
        return result

    def load_with_raw(self, profile: str) -> tuple[dict[str, Any], str, Path]:
        """Load a profile and return ``(parsed_config, raw_text, path)``.

        Useful for management UIs that want both the normalised
        configuration and the original on-disk YAML/markdown text.

        Raises:
            FileNotFoundError: if the profile cannot be located.
        """
        profile_path = self._find_profile_path(profile)
        if profile_path is None:
            searched = [str(d) for d in self._all_search_dirs()]
            raise FileNotFoundError(
                f"Profile '{profile}' not found. Searched: {', '.join(searched)}"
            )
        raw_text = profile_path.read_text(encoding="utf-8")
        config = self.load(profile)
        return config, raw_text, profile_path


def _split_agent_md_frontmatter(text: str) -> tuple[str, str]:
    """Split a `.agent.md` file into (frontmatter_yaml, body).

    Returns ``("", text)`` if no frontmatter delimiter is present.
    """
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return "", text
    # Use the original (non-stripped) text to preserve body indentation.
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "", text
    return parts[1].strip("\n"), parts[2].lstrip("\n")
