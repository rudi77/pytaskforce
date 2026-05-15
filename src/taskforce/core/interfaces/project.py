"""
Project Store Protocol

Persistence contract for the project registry. A project is a directory
on disk plus a small piece of metadata (id, display name, created_at).
The framework default is a JSON file under
``<work_dir>/projects.json``; enterprise plugins can swap in a
tenant-scoped backend via ``set_project_store_override``.
"""

from __future__ import annotations

from typing import Protocol

from taskforce.core.domain.project import Project


class ProjectStoreProtocol(Protocol):
    """Persistence contract for projects."""

    async def create(self, name: str, path: str) -> Project:
        """Persist a new project, returning the stored entity.

        The store is responsible for assigning ``project_id`` and
        stamping ``created_at``. Implementations should reject:

        * Empty ``name`` or ``path``.
        * Duplicate ``path`` values (a project's path identifies it
          on disk — two projects pointing at the same directory would
          collide on writes).
        """
        ...

    async def get(self, project_id: str) -> Project | None:
        """Return the project by id, or ``None`` if not found."""
        ...

    async def list(self) -> list[Project]:
        """Return all projects ordered by ``created_at`` (newest first)."""
        ...

    async def delete(self, project_id: str) -> None:
        """Remove the project from the registry.

        Implementations MUST NOT delete the directory on disk — only
        the registry entry. The user is responsible for the directory's
        lifecycle outside of taskforce.
        """
        ...
