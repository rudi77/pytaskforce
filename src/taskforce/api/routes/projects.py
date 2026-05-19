"""Project Management API routes.

Cowork-style projects: a project is a directory on disk that holds
everything the agent needs for a specific body of work (CLAUDE.md,
skills/, free-form context). Conversations carry an optional
``project_id`` — when set, the agent's working_dir is rooted at the
project's path instead of the global ``TASKFORCE_WORK_DIR``.

Endpoints:

* ``POST /projects``               -- create or import a project
* ``GET  /projects``               -- list projects
* ``GET  /projects/{id}``          -- get a single project
* ``DELETE /projects/{id}``        -- remove from registry (directory stays)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from taskforce.api.dependencies import get_project_store
from taskforce.api.errors import http_exception as _error_response
from taskforce.api.schemas.errors import ErrorResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    """Body for ``POST /projects``."""

    name: str = Field(..., min_length=1, max_length=200, description="Display name.")
    path: str = Field(
        ...,
        min_length=1,
        description=(
            "Absolute filesystem path where the project lives. The "
            "directory is created if it does not exist (when ``mode`` "
            "is ``scratch``). For ``existing`` it must already exist."
        ),
    )
    mode: Literal["scratch", "existing"] = Field(
        default="scratch",
        description=(
            "``scratch``: create the directory (and a stub ``CLAUDE.md`` "
            "+ ``skills/`` folder) if they don't exist. ``existing``: "
            "point at a directory the user already maintains; the route "
            "still ensures ``CLAUDE.md`` + ``skills/`` exist but does "
            "not overwrite anything."
        ),
    )


class ProjectResponse(BaseModel):
    """A project as returned to the UI."""

    project_id: str
    name: str
    path: str
    created_at: datetime


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def create_project(
    request: CreateProjectRequest,
    store=Depends(get_project_store),
) -> ProjectResponse:
    """Register a new project.

    Both ``scratch`` and ``existing`` modes end with the directory
    containing at minimum a ``CLAUDE.md`` file and a ``skills/`` folder.
    The user is free to add any other structure they want — taskforce
    does not enforce a fixed layout beyond those two anchors.
    """
    raw_path = request.path.strip()
    if not raw_path:
        raise _error_response(
            status_code=400,
            code="invalid_path",
            message="Path must not be empty.",
            details={"field": "path"},
        )

    resolved = Path(raw_path).expanduser().resolve()

    if request.mode == "existing":
        if not resolved.exists():
            raise _error_response(
                status_code=400,
                code="path_not_found",
                message=f"Directory does not exist: {resolved}",
                details={"path": str(resolved)},
            )
        if not resolved.is_dir():
            raise _error_response(
                status_code=400,
                code="path_not_directory",
                message=f"Path is not a directory: {resolved}",
                details={"path": str(resolved)},
            )

    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _error_response(
            status_code=400,
            code="path_create_failed",
            message=f"Could not create directory: {exc}",
            details={"path": str(resolved), "error": str(exc)},
        ) from exc

    _ensure_workspace_anchors(resolved, project_name=request.name)

    try:
        project = await store.create(name=request.name, path=str(resolved))
    except ValueError as exc:
        # FileProjectStore raises ValueError on duplicate path. Distinguish
        # the duplicate case from generic validation errors so the UI can
        # surface it clearly.
        msg = str(exc)
        status = 409 if "already exists" in msg else 400
        raise _error_response(
            status_code=status,
            code="project_create_failed",
            message=msg,
            details={"path": str(resolved)},
        ) from exc

    return _to_response(project)


@router.get("", response_model=list[ProjectResponse])
async def list_projects(store=Depends(get_project_store)) -> list[ProjectResponse]:
    """List all registered projects, newest first."""
    projects = await store.list()
    return [_to_response(p) for p in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_project(
    project_id: str,
    store=Depends(get_project_store),
) -> ProjectResponse:
    """Get a single project by id."""
    project = await store.get(project_id)
    if project is None:
        raise _error_response(
            status_code=404,
            code="project_not_found",
            message=f"No project with id {project_id!r}.",
            details={"project_id": project_id},
        )
    return _to_response(project)


@router.delete(
    "/{project_id}",
    status_code=204,
    responses={404: {"model": ErrorResponse}},
)
async def delete_project(
    project_id: str,
    store=Depends(get_project_store),
) -> None:
    """Remove the project from the registry (directory stays on disk)."""
    existing = await store.get(project_id)
    if existing is None:
        raise _error_response(
            status_code=404,
            code="project_not_found",
            message=f"No project with id {project_id!r}.",
            details={"project_id": project_id},
        )
    await store.delete(project_id)


# ------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------


_CLAUDE_MD_STUB = """# {name}

This is the entry point for the **{name}** project. Edit this file to
describe what the project is, what the agent is allowed to do here, and
what the agent must escalate.

## CoWork baseline rules
- Treat this directory as the CoWork project home. Start each task from
  this `CLAUDE.md`, then use `skills/` for workflow-specific instructions.
- For project work, prefer relative paths from this directory when using
  file, search, edit, shell, or Python tools.
- Search, read, and write inside this project unless the user explicitly
  asks for an external path or source. If an external path is needed,
  explain why before using it.
- Never delete, move, or overwrite user files unless the user explicitly
  asks for that exact change.
- When information is missing or ambiguous, create a proposal or draft and
  escalate the open question instead of guessing.
- Customer-specific rules and workflow details belong below this baseline
  and may make these rules stricter for the use case.

## What the agent does
- ...

## What the agent does NOT do
- ...

## Workflows / Skills
See ``skills/`` for per-workflow instructions.
"""


def _ensure_workspace_anchors(path: Path, *, project_name: str) -> None:
    """Make sure ``CLAUDE.md`` and ``skills/`` exist inside the project dir.

    Never overwrites existing content — the user's files win. We only
    create the anchors when they are missing so a freshly minted
    project is immediately usable by the agent and an imported
    directory gains the structure if it didn't already have it.
    """
    claude_md = path / "CLAUDE.md"
    if not claude_md.exists():
        claude_md.write_text(
            _CLAUDE_MD_STUB.format(name=project_name),
            encoding="utf-8",
        )

    skills_dir = path / "skills"
    skills_dir.mkdir(exist_ok=True)


def _to_response(project) -> ProjectResponse:
    return ProjectResponse(
        project_id=project.project_id,
        name=project.name,
        path=project.path,
        created_at=project.created_at,
    )
