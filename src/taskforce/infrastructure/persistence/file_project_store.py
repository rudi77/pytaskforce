"""
File-Based Project Store

Persists projects as a single JSON document at
``<work_dir>/projects.json``. Writes are serialized through an
``asyncio.Lock`` and use the standard temp-file + rename atomic-write
pattern, mirroring the other file-based stores in the framework
(``FileConversationStore``, ``FileStandingGoalStore``).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import structlog

from taskforce.core.domain.project import Project

logger = structlog.get_logger(__name__)


class FileProjectStore:
    """File-backed project registry.

    Stores all projects in a single ``projects.json`` file; one
    JSON object per project. The directory each project points to
    is **not** managed by this store — creation/deletion of the
    on-disk workspace is the API route's responsibility.
    """

    def __init__(self, work_dir: str = ".taskforce") -> None:
        self._base_dir = Path(work_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._base_dir / "projects.json"
        self._lock = asyncio.Lock()

    async def create(self, name: str, path: str) -> Project:
        if not name.strip():
            raise ValueError("Project name must not be empty")
        if not path.strip():
            raise ValueError("Project path must not be empty")

        normalised_path = str(Path(path).expanduser().resolve())

        async with self._lock:
            entries = await self._load_unlocked()
            for entry in entries:
                if entry["path"] == normalised_path:
                    raise ValueError(
                        f"A project already exists for path {normalised_path!r} "
                        f"(id={entry['project_id']!r})"
                    )

            project = Project(name=name.strip(), path=normalised_path)
            entries.append(_to_dict(project))
            await self._save_unlocked(entries)

        logger.info(
            "project.created",
            project_id=project.project_id,
            name=project.name,
            path=project.path,
        )
        return project

    async def get(self, project_id: str) -> Project | None:
        entries = await self._load()
        for entry in entries:
            if entry["project_id"] == project_id:
                return _from_dict(entry)
        return None

    async def list(self) -> list[Project]:
        entries = await self._load()
        entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return [_from_dict(e) for e in entries]

    async def delete(self, project_id: str) -> None:
        async with self._lock:
            entries = await self._load_unlocked()
            remaining = [e for e in entries if e["project_id"] != project_id]
            if len(remaining) == len(entries):
                return
            await self._save_unlocked(remaining)
        logger.info("project.deleted", project_id=project_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load(self) -> list[dict[str, Any]]:
        async with self._lock:
            return await self._load_unlocked()

    async def _load_unlocked(self) -> list[dict[str, Any]]:
        if not self._file.exists():
            return []
        try:
            async with aiofiles.open(self._file, encoding="utf-8") as f:
                content = await f.read()
            return json.loads(content) if content.strip() else []
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("project.index_load_failed", error=str(exc))
            return []

    async def _save_unlocked(self, entries: list[dict[str, Any]]) -> None:
        temp = self._file.with_suffix(".json.tmp")
        payload = json.dumps(entries, indent=2, ensure_ascii=False)
        async with aiofiles.open(temp, "w", encoding="utf-8") as f:
            await f.write(payload)
        if self._file.exists():
            self._file.unlink()
        temp.rename(self._file)


def _to_dict(project: Project) -> dict[str, Any]:
    return {
        "project_id": project.project_id,
        "name": project.name,
        "path": project.path,
        "created_at": project.created_at.isoformat(),
    }


def _from_dict(entry: dict[str, Any]) -> Project:
    return Project(
        project_id=entry["project_id"],
        name=entry["name"],
        path=entry["path"],
        created_at=datetime.fromisoformat(entry["created_at"]),
    )
