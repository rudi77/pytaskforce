"""
Path utilities for resource file resolution.

Handles path resolution for:
1. PyInstaller frozen executables (sys._MEIPASS)
2. Source tree development (pyproject.toml / .git markers)
3. Pip-installed packages (importlib.resources fallback)
"""

import importlib.resources
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_base_path() -> Path:
    """
    Get base path for resource files.

    Resolution order:
    1. PyInstaller executable → sys._MEIPASS
    2. Source tree (pyproject.toml/.git found) → project root
    3. Pip-installed package → package root via importlib.resources

    The result is cached for performance.

    Returns:
        Path to the base directory containing configs and other resources.
    """
    if getattr(sys, "frozen", False):
        # Running as PyInstaller executable
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]

    # Try source tree first
    project_root = _find_project_root()
    if project_root and (project_root / "src" / "taskforce" / "configs").exists():
        return project_root

    # Pip-installed: configs are inside the package at taskforce/configs/
    return _get_installed_package_root()


@lru_cache(maxsize=1)
def _get_installed_package_root() -> Path:
    """Get root path for a pip-installed taskforce package.

    When installed via pip, the package lives in site-packages/taskforce/.
    The configs directory is at site-packages/taskforce/configs/.
    We return a path such that <result>/taskforce/configs/ exists.

    Returns:
        Path to the parent of the taskforce package directory.
    """
    try:
        pkg_path = importlib.resources.files("taskforce")
        # pkg_path points to site-packages/taskforce/
        # Return its parent so that <result>/taskforce/configs/ works
        # via the standard "src/taskforce/configs" path resolution
        resolved = Path(str(pkg_path))
        if (resolved / "configs").is_dir():
            return resolved.parent
    except Exception:
        pass

    # Final fallback: 4 levels up from this file (core/utils/paths.py)
    return Path(__file__).parent.parent.parent.parent


@lru_cache(maxsize=1)
def _find_project_root() -> Path | None:
    """Find project root by searching upward for marker files.

    Returns:
        Path to the project root, or None if not in a source tree.
    """
    current = Path(__file__).resolve().parent
    markers = ["pyproject.toml", ".git"]

    for _ in range(10):
        for marker in markers:
            if (current / marker).exists():
                return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """Find project root by searching for marker directories/files.

    Searches upward from this file's location for directories that
    indicate the project root (pyproject.toml, .git).

    Returns:
        Path to the project root directory.

    Raises:
        RuntimeError: If project root cannot be determined.
    """
    root = _find_project_root()
    if root is not None:
        return root

    # Fallback for pip-installed packages
    return _get_installed_package_root()
