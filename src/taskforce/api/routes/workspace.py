"""
Workspace Browse API
====================

Read-only file-tree listing for the chat ``@mention`` picker (Cowork-parity
Phase 1 follow-up). The picker lets users reference local project files in
their prompts; selecting an entry inserts ``@relative/path/to/file`` into
the prompt and the agent uses its existing ``file_read`` / ``glob`` tools
to load contents when needed.

This module deliberately does NOT serve file CONTENTS — that's what the
agent's tool layer is for. We only list paths so the UI can render a
filterable picker.

Workspace root resolution (first match wins):

1. ``TASKFORCE_WORKSPACE_ROOT`` env var, if it points to an existing dir.
2. Process current working directory.

The root is computed once per request; admins can swap it via env without
restarting the API.

Security
--------

- Path traversal is rejected (resolved path must stay under root).
- A hard denylist hides VCS / build / cache directories (``.git``,
  ``node_modules``, ``.venv``, ``__pycache__``, ``.taskforce``, ``dist``,
  ``.next``) — these add no value for prompt referencing and would
  drown the picker in noise. Configurable via
  ``TASKFORCE_WORKSPACE_EXCLUDE`` (comma-separated names).
- Symlinks that escape the root are filtered out.
- Hidden files (leading ``.``) are excluded by default. Set
  ``include_hidden=true`` on the query to include them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from taskforce.api.errors import http_exception as _http_exception
from taskforce.api.schemas.errors import ErrorResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class WorkspaceEntry(BaseModel):
    """One filesystem entry inside the workspace."""

    path: str = Field(
        ...,
        description=(
            "Path RELATIVE to the workspace root, forward-slash-separated. "
            "This is what gets inserted into the prompt as ``@<path>``."
        ),
    )
    name: str = Field(..., description="Basename of the entry.")
    type: Literal["file", "dir"] = Field(
        ..., description="``file`` or ``dir``. Dirs can be drilled into."
    )
    size: int | None = Field(
        default=None,
        description="Byte size for files; ``null`` for directories.",
    )


class WorkspaceListResponse(BaseModel):
    """Response shape for ``GET /workspace/browse``."""

    root: str = Field(..., description="Absolute path of the workspace root.")
    path: str = Field(
        ...,
        description=(
            "Relative path within the root that was listed (``""`` for the "
            "root itself)."
        ),
    )
    entries: list[WorkspaceEntry]
    truncated: bool = Field(
        default=False,
        description=(
            "True when more entries existed than ``limit`` allowed. The "
            "picker uses this to nudge the user to narrow the filter."
        ),
    )


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


_DEFAULT_EXCLUDES = frozenset(
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
        "target",  # Rust
        ".idea",
        ".vscode",
        "htmlcov",
        ".coverage",
    }
)


def _resolve_workspace_root() -> Path:
    """Pick the directory the picker browses against."""
    env_root = os.getenv("TASKFORCE_WORKSPACE_ROOT", "").strip()
    if env_root:
        root = Path(env_root).expanduser()
        if root.is_dir():
            return root.resolve()
    return Path.cwd().resolve()


def _excluded_names() -> frozenset[str]:
    """Set of directory names that the picker hides."""
    extra = os.getenv("TASKFORCE_WORKSPACE_EXCLUDE", "").strip()
    if not extra:
        return _DEFAULT_EXCLUDES
    extras = {name.strip() for name in extra.split(",") if name.strip()}
    return _DEFAULT_EXCLUDES | extras


@dataclass(frozen=True)
class _ResolvedTarget:
    root: Path
    target: Path
    relative: str


def _resolve_target(rel_path: str) -> _ResolvedTarget:
    """Resolve a user-supplied relative path against the workspace root.

    Raises HTTP 400 on traversal attempts (``..``, absolute paths that
    escape root) and HTTP 404 when the target doesn't exist or isn't a
    directory.
    """
    root = _resolve_workspace_root()
    cleaned = (rel_path or "").strip().lstrip("/")
    # Normalize forward-slash input on Windows too.
    cleaned = cleaned.replace("\\", "/")
    target = (root / cleaned).resolve() if cleaned else root

    # Guard against ``..`` traversal AND symlinks that escape the root.
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise _http_exception(
            status_code=400,
            code="invalid_path",
            message="Path escapes the workspace root.",
            details={"path": rel_path},
        ) from exc

    if not target.exists():
        raise _http_exception(
            status_code=404,
            code="path_not_found",
            message=f"No such path inside the workspace: {cleaned or '.'}",
            details={"path": cleaned},
        )
    if not target.is_dir():
        raise _http_exception(
            status_code=400,
            code="not_a_directory",
            message="Workspace browse only lists directories.",
            details={"path": cleaned},
        )

    return _ResolvedTarget(root=root, target=target, relative=cleaned)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/workspace/browse",
    response_model=WorkspaceListResponse,
    summary="List files and directories under the workspace root",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid path."},
        404: {"model": ErrorResponse, "description": "Path does not exist."},
    },
)
def browse_workspace(
    path: str = Query(
        default="",
        description=(
            "Directory relative to the workspace root to list. Empty "
            "string (default) lists the root."
        ),
    ),
    q: str = Query(
        default="",
        description=(
            "Optional case-insensitive substring filter applied to the "
            "basename of each entry. Used by the @mention picker for "
            "type-to-narrow."
        ),
    ),
    include_hidden: bool = Query(
        default=False,
        description="Include dotfiles / dot-directories.",
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=2000,
        description="Maximum number of entries to return (after filtering).",
    ),
) -> WorkspaceListResponse:
    """Return a single directory listing relative to the workspace root.

    The endpoint is intentionally **flat per call** (no recursive walk):
    the picker drills into subdirectories one at a time. This keeps
    response payloads bounded even for monorepos and avoids streaming
    huge trees that the user wouldn't scroll through anyway.
    """
    resolved = _resolve_target(path)
    excludes = _excluded_names()
    query = q.strip().lower()

    raw_entries: list[WorkspaceEntry] = []
    try:
        children = list(resolved.target.iterdir())
    except PermissionError as exc:
        raise _http_exception(
            status_code=403,
            code="permission_denied",
            message="Cannot read directory contents.",
            details={"path": resolved.relative},
        ) from exc

    for entry in children:
        name = entry.name
        if not include_hidden and name.startswith("."):
            continue
        if name in excludes:
            continue

        # Resolve symlinks to make sure they don't escape the workspace
        # root; silently skip any that do.
        try:
            resolved_entry = entry.resolve()
            resolved_entry.relative_to(resolved.root)
        except (ValueError, OSError):
            continue

        is_dir = entry.is_dir()
        if query and query not in name.lower():
            continue

        rel = entry.relative_to(resolved.root).as_posix()
        size: int | None = None
        if not is_dir:
            try:
                size = entry.stat().st_size
            except OSError:
                size = None
        raw_entries.append(
            WorkspaceEntry(
                path=rel,
                name=name,
                type="dir" if is_dir else "file",
                size=size,
            )
        )

    # Dirs first, then files; within each group sort case-insensitively
    # by name. Matches what most IDE file pickers do.
    raw_entries.sort(key=lambda e: (e.type == "file", e.name.lower()))

    truncated = len(raw_entries) > limit
    entries = raw_entries[:limit]

    return WorkspaceListResponse(
        root=str(resolved.root),
        path=resolved.relative,
        entries=entries,
        truncated=truncated,
    )
