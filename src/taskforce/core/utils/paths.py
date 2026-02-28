"""
Path utilities for resource file resolution.

Handles path resolution for both normal Python execution and
PyInstaller frozen executables.
"""

import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_base_path() -> Path:
    """
    Get base path for resource files, handling frozen executables.

    When running as a PyInstaller executable, resources are extracted to
    a temporary directory (sys._MEIPASS). When running as a normal Python
    script, returns the project root directory.

    The result is cached for performance.

    Returns:
        Path to the base directory containing configs and other resources.
    """
    if getattr(sys, "frozen", False):
        # Running as PyInstaller executable
        # Resources are extracted to sys._MEIPASS
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]

    # Running as script - find project root by looking for markers
    return get_project_root()


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """
    Find project root by searching for marker directories/files.

    Searches upward from this file's location for directories that
    indicate the project root (pyproject.toml, configs/, src/).

    Returns:
        Path to the project root directory.

    Raises:
        RuntimeError: If project root cannot be determined.
    """
    # Start from this file's directory
    current = Path(__file__).resolve().parent

    # Search upward for project root markers
    markers = ["pyproject.toml", ".git"]

    for _ in range(10):  # Limit search depth
        for marker in markers:
            if (current / marker).exists():
                return current
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent

    # Fallback: assume standard structure (this file is at core/utils/paths.py)
    # Project root is 4 levels up from paths.py
    return Path(__file__).parent.parent.parent.parent.parent
