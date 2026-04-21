"""
Agent File Loader
=================

Parses ``.agent.md`` files — markdown agent definitions with YAML frontmatter.
The frontmatter carries identity and capabilities (tools, sub_agents, mcp_servers,
skills, notifications, rag, workflow) plus an optional ``technical:`` block and
``extends:`` preset references. The markdown body becomes the agent's system
prompt body that the :class:`SystemPromptAssembler` appends to the lean kernel.

Downstream code (``ProfileLoader``, ``AgentFactory``, ``InfrastructureBuilder``)
consumes plain dicts with top-level keys like ``tools``, ``persistence``, ``llm``,
``agent``, etc. This module normalizes agent files into that shape so the
rest of the pipeline keeps working unchanged.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)


# Keys inside a ``technical:`` block whose list values get concatenated with the
# base config instead of replaced. These align with the existing
# ``merge_plugin_config`` semantics in ``profile_loader.py``.
_LIST_CONCAT_KEYS: frozenset[str] = frozenset(
    {"tools", "sub_agents", "mcp_servers", "event_sources", "rules"}
)


@dataclass(frozen=True)
class AgentFile:
    """Parsed ``.agent.md`` file.

    Attributes:
        frontmatter: YAML frontmatter as a dict.
        body: Markdown body (after the closing ``---`` line), stripped of
            surrounding whitespace.
        path: Source file path (for diagnostics).
    """

    frontmatter: dict[str, Any]
    body: str
    path: Path


def load_agent_md(path: Path) -> AgentFile:
    """Parse a ``.agent.md`` file into an :class:`AgentFile`.

    File format::

        ---
        <yaml frontmatter>
        ---
        <markdown body>

    Args:
        path: Absolute path to the ``.agent.md`` file.

    Returns:
        Parsed :class:`AgentFile`.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the frontmatter is missing or malformed.
    """
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text, path)
    return AgentFile(frontmatter=frontmatter, body=body, path=path)


def _split_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    """Split a markdown file with YAML frontmatter into (dict, body)."""
    if not text.startswith("---"):
        raise ValueError(f"Agent file missing frontmatter (expected leading '---'): {path}")

    # Find the closing '---' on its own line after the opening.
    lines = text.splitlines()
    closing_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            closing_idx = i
            break
    if closing_idx is None:
        raise ValueError(f"Agent file frontmatter not terminated by '---': {path}")

    frontmatter_yaml = "\n".join(lines[1:closing_idx])
    body = "\n".join(lines[closing_idx + 1 :])

    parsed = yaml.safe_load(frontmatter_yaml) or {}
    if not isinstance(parsed, dict):
        raise ValueError(
            f"Agent file frontmatter must be a YAML mapping, got "
            f"{type(parsed).__name__}: {path}"
        )
    return parsed, body


def agent_file_to_config(
    agent_file: AgentFile,
    *,
    preset_dirs: list[Path] | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert an :class:`AgentFile` into a flat config dict.

    Pipeline:
    1. Start from ``defaults`` (framework baseline).
    2. Apply any ``extends:`` presets in left-to-right order.
    3. Apply the frontmatter itself (minus ``technical:`` and ``extends:``).
    4. Flatten the ``technical:`` block onto the top level.
    5. Inject the markdown body as ``system_prompt``.

    Args:
        agent_file: Parsed agent definition.
        preset_dirs: Directories to search for named presets referenced by
            ``extends:``. When ``None``, presets are not resolved.
        defaults: Optional baseline config merged in first.

    Returns:
        Flat config dict suitable for the rest of the profile pipeline.
    """
    frontmatter = dict(agent_file.frontmatter)
    extends = frontmatter.pop("extends", None)
    technical = frontmatter.pop("technical", None) or {}

    config: dict[str, Any] = copy.deepcopy(defaults) if defaults else {}

    if extends and preset_dirs:
        for preset in _normalize_extends(extends):
            preset_data = _load_preset(preset, preset_dirs)
            config = _deep_merge(config, preset_data)

    # Frontmatter (agent description) — merged next so it overrides presets.
    config = _deep_merge(config, frontmatter)

    # Technical block flattened onto top level.
    config = _deep_merge(config, technical)

    # Body becomes the system prompt. An inline system_prompt in frontmatter
    # still wins if the author explicitly set one.
    #
    # The body is wrapped with leading/trailing newlines to mirror the
    # whitespace of the triple-quoted Python prompt strings the assembler
    # used to receive — keeps byte-level parity with pre-migration prompts.
    if agent_file.body and not config.get("system_prompt"):
        config["system_prompt"] = "\n" + agent_file.body.strip("\n") + "\n"

    return config


def _normalize_extends(extends: Any) -> list[str]:
    """Coerce ``extends:`` value to a list of preset names."""
    if isinstance(extends, str):
        return [extends]
    if isinstance(extends, list):
        return [str(item) for item in extends if item]
    raise ValueError(
        f"'extends:' must be a string or list of strings, got {type(extends).__name__}"
    )


def _load_preset(name: str, preset_dirs: list[Path]) -> dict[str, Any]:
    """Load a named preset YAML from any of the given directories."""
    for preset_dir in preset_dirs:
        candidate = preset_dir / f"{name}.yaml"
        if candidate.is_file():
            with open(candidate, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                raise ValueError(f"Preset '{name}' must be a YAML mapping: {candidate}")
            logger.debug("preset_loaded", preset=name, path=str(candidate))
            return data
    searched = [str(d / f"{name}.yaml") for d in preset_dirs]
    raise FileNotFoundError(f"Preset '{name}' not found. Searched: {', '.join(searched)}")


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``overlay`` into ``base``.

    Semantics:
    * Dicts → recursively deep-merged.
    * Lists → replaced, except keys in :data:`_LIST_CONCAT_KEYS` which are
      concatenated (``base + overlay``).
    * Scalars → replaced.

    Neither input is mutated; the result is a fresh dict.
    """
    result = copy.deepcopy(base)
    for key, overlay_value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(overlay_value, dict):
            result[key] = _deep_merge(result[key], overlay_value)
        elif (
            key in _LIST_CONCAT_KEYS
            and isinstance(result.get(key), list)
            and isinstance(overlay_value, list)
        ):
            result[key] = list(result[key]) + list(overlay_value)
        else:
            result[key] = copy.deepcopy(overlay_value)
    return result
