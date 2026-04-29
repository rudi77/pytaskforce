"""Environment loading helpers for CLI entry points."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv_if_present(
    start_directory: Path | None = None,
) -> None:
    """Load a local .env file without overriding existing environment variables."""
    env_file = _find_dotenv(start_directory or Path.cwd())
    if env_file is None:
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line.removeprefix("export ").strip()

        key, separator, value = line.partition("=")
        if not separator:
            continue

        key = key.strip()
        if not key or key in os.environ:
            continue

        os.environ[key] = _normalize_env_value(value.strip())


def _find_dotenv(start_directory: Path) -> Path | None:
    """Find the nearest .env file by walking upward."""
    current = start_directory.resolve()
    if current.is_file():
        current = current.parent

    for directory in (current, *current.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate

    return None


def _normalize_env_value(value: str) -> str:
    """Strip common .env quoting while preserving the raw secret value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
