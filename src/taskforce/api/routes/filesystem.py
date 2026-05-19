"""Filesystem Browse API.

Read-only directory listing used by the "New project" → folder-picker UI.
Unlike :mod:`taskforce.api.routes.workspace`, which is sandboxed to the
single ``TASKFORCE_WORKSPACE_ROOT`` for the chat ``@mention`` picker,
this endpoint lets the user browse anywhere their server process can
see — needed to point a new project at an arbitrary directory on disk.

Endpoint:

* ``GET /filesystem/browse?path=<abs_path>`` — list directories under
  ``path``. When ``path`` is omitted, defaults to the user's home
  directory. On Windows a drive root (``C:\\``) has ``parent=null`` and
  the response includes ``drives`` for switching between drives.

Cross-platform notes
--------------------

The picker only walks **directories** — never files — since projects
live in folders. Hidden dot-dirs and well-known noise (``.git``,
``node_modules``, …) are filtered out by default; pass
``include_hidden=true`` to include dotfiles.
"""

from __future__ import annotations

import os
import string
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from taskforce.api.errors import http_exception as _http_exception
from taskforce.api.schemas.errors import ErrorResponse

router = APIRouter(prefix="/filesystem", tags=["filesystem"])


_HIDDEN_NOISE = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".taskforce",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        ".idea",
        ".vscode",
        "htmlcov",
        ".coverage",
        "$RECYCLE.BIN",
        "System Volume Information",
    }
)


class DirectoryEntry(BaseModel):
    name: str = Field(..., description="Basename of the directory.")
    path: str = Field(..., description="Absolute path of the directory.")


class BrowseResponse(BaseModel):
    path: str = Field(..., description="Absolute path that was listed.")
    parent: str | None = Field(
        default=None,
        description=(
            "Absolute path of the parent directory, or ``null`` when "
            "``path`` is a filesystem root (``/`` on POSIX, ``X:\\`` on "
            "Windows)."
        ),
    )
    entries: list[DirectoryEntry] = Field(
        default_factory=list,
        description="Subdirectories of ``path``, sorted case-insensitively.",
    )
    drives: list[str] = Field(
        default_factory=list,
        description=(
            "On Windows only: available drive roots (``C:\\``, ``D:\\`` …) "
            "so the picker can switch drives. Empty on POSIX."
        ),
    )
    is_windows: bool = Field(
        default=False,
        description="True when the server runs on Windows.",
    )


def _is_windows() -> bool:
    return os.name == "nt"


def _list_windows_drives() -> list[str]:
    """Return the set of accessible drive roots (``C:\\``, ``D:\\`` …)."""
    drives: list[str] = []
    for letter in string.ascii_uppercase:
        candidate = Path(f"{letter}:\\")
        try:
            if candidate.exists():
                drives.append(str(candidate))
        except OSError:
            continue
    return drives


def _is_filesystem_root(path: Path) -> bool:
    """True when ``path`` has no meaningful parent."""
    return path == path.parent


@router.get(
    "/browse",
    response_model=BrowseResponse,
    summary="List directories at an absolute filesystem path.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid path."},
        404: {"model": ErrorResponse, "description": "Path does not exist."},
    },
)
def browse_filesystem(
    path: str = Query(
        default="",
        description=(
            "Absolute path to list. When empty, defaults to the user's "
            "home directory."
        ),
    ),
    include_hidden: bool = Query(
        default=False,
        description="Include dot-directories and well-known build/cache noise.",
    ),
) -> BrowseResponse:
    is_windows = _is_windows()
    raw = (path or "").strip().strip('"').strip("'")
    target = Path(raw).expanduser() if raw else Path.home()

    try:
        resolved = target.resolve()
    except OSError as exc:
        raise _http_exception(
            status_code=400,
            code="invalid_path",
            message=f"Could not resolve path: {exc}",
            details={"path": raw},
        ) from exc

    if not resolved.is_absolute():
        raise _http_exception(
            status_code=400,
            code="invalid_path",
            message="Path must be absolute.",
            details={"path": raw},
        )

    if not resolved.exists():
        raise _http_exception(
            status_code=404,
            code="path_not_found",
            message=f"Directory does not exist: {resolved}",
            details={"path": str(resolved)},
        )

    if not resolved.is_dir():
        raise _http_exception(
            status_code=400,
            code="not_a_directory",
            message=f"Not a directory: {resolved}",
            details={"path": str(resolved)},
        )

    entries: list[DirectoryEntry] = []
    try:
        for child in resolved.iterdir():
            try:
                if not child.is_dir():
                    continue
            except OSError:
                continue
            name = child.name
            if not include_hidden:
                if name.startswith("."):
                    continue
                if name in _HIDDEN_NOISE:
                    continue
            entries.append(DirectoryEntry(name=name, path=str(child)))
    except PermissionError:
        # Listing was partially blocked — still return what we have.
        pass

    entries.sort(key=lambda e: e.name.lower())

    parent = None if _is_filesystem_root(resolved) else str(resolved.parent)
    drives = _list_windows_drives() if is_windows else []

    return BrowseResponse(
        path=str(resolved),
        parent=parent,
        entries=entries,
        drives=drives,
        is_windows=is_windows,
    )
