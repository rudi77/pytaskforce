"""
YAML I/O Utilities
==================

Provides atomic, cross-platform YAML file read/write operations.

The atomic write strategy ensures that partial writes never corrupt
existing files, even on platforms (Windows) where ``os.rename`` cannot
overwrite an existing target.

Clean Architecture Notes:
- Infrastructure layer: pure I/O utility with no domain logic
- No dependencies on other Taskforce layers (uses stdlib + PyYAML only)
"""

import os
import tempfile
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()


def atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    """
    Write a dictionary to a YAML file atomically.

    Implementation strategy:
    1. Write to a temporary file in the same directory (same filesystem).
    2. If the target already exists, delete it first (Windows requirement).
    3. Rename the temp file to the target path (atomic on POSIX).

    Args:
        path: Target file path.
        data: Dictionary to serialize as YAML.

    Raises:
        OSError: If file operations fail.
    """
    temp_fd, temp_path = tempfile.mkstemp(
        dir=path.parent, suffix=".tmp", prefix=".agent_"
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        # Windows: must delete target before rename
        if path.exists():
            path.unlink()

        # Atomic rename
        Path(temp_path).rename(path)

        logger.debug("agent.yaml.written", agent_file=str(path), atomic=True)

    except Exception:
        # Clean up temp file on error
        if Path(temp_path).exists():
            Path(temp_path).unlink()
        raise


def safe_load_yaml(path: Path) -> dict[str, Any] | None:
    """
    Safely load a YAML file, returning None on any error.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed dictionary on success, None if the file does not exist
        or cannot be parsed.
    """
    if not path.exists():
        return None

    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(
            "yaml.load.failed",
            path=str(path),
            error=str(e),
        )
        return None
