"""File-based experience persistence.

Stores session experiences as individual JSON files under a configurable
directory, following the same I/O patterns as ``FileMemoryStore``.

Layout::

    {base_dir}/
        {session_id}.json          # Individual session experiences
        _consolidations/
            {consolidation_id}.json  # Consolidation run results
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from taskforce.core.domain.experience import ConsolidationResult, SessionExperience
from taskforce.core.interfaces.experience import ExperienceStoreProtocol

logger = structlog.get_logger(__name__)


class FileExperienceStore(ExperienceStoreProtocol):
    """Persist session experiences as JSON files.

    Args:
        base_dir: Directory where experience files are stored.
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._dir = Path(base_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._consolidations_dir = self._dir / "_consolidations"
        self._consolidations_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # ExperienceStoreProtocol
    # ------------------------------------------------------------------

    async def save_experience(self, experience: SessionExperience) -> None:
        """Persist a session experience record."""
        path = self._experience_path(experience.session_id)
        path.write_text(
            json.dumps(experience.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

    async def load_experience(self, session_id: str) -> SessionExperience | None:
        """Load a session experience by ID."""
        path = self._experience_path(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionExperience.from_dict(data)

    async def list_experiences(
        self,
        limit: int = 50,
        unprocessed_only: bool = False,
    ) -> list[SessionExperience]:
        """List stored experiences, most recent first."""
        experiences: list[SessionExperience] = []
        json_files = sorted(
            self._dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in json_files:
            if len(experiences) >= limit:
                break
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                exp = SessionExperience.from_dict(data)
                if unprocessed_only and exp.processed_by:
                    continue
                experiences.append(exp)
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.warning("experience.load_failed", path=str(path))
                continue
        return experiences

    async def mark_processed(
        self,
        session_ids: list[str],
        consolidation_id: str,
    ) -> None:
        """Mark experiences as processed by a consolidation run."""
        for sid in session_ids:
            path = self._experience_path(sid)
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                processed = data.get("processed_by", [])
                if consolidation_id not in processed:
                    processed.append(consolidation_id)
                    data["processed_by"] = processed
                    path.write_text(
                        json.dumps(data, indent=2, default=str),
                        encoding="utf-8",
                    )
            except (json.JSONDecodeError, OSError):
                logger.warning("experience.mark_processed_failed", session_id=sid)

    async def delete_experience(self, session_id: str) -> bool:
        """Delete a session experience."""
        path = self._experience_path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    # ------------------------------------------------------------------
    # Consolidation result persistence
    # ------------------------------------------------------------------

    async def save_consolidation(self, result: ConsolidationResult) -> None:
        """Persist a consolidation run result.

        Args:
            result: The consolidation result to save.
        """
        path = self._consolidation_path(result.consolidation_id)
        path.write_text(
            json.dumps(result.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

    async def list_consolidations(self, limit: int = 10) -> list[ConsolidationResult]:
        """List past consolidation runs, most recent first.

        Args:
            limit: Maximum number of results to return.

        Returns:
            List of consolidation results.
        """
        results: list[ConsolidationResult] = []
        json_files = sorted(
            self._consolidations_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in json_files:
            if len(results) >= limit:
                break
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                results.append(ConsolidationResult.from_dict(data))
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.warning("consolidation.load_failed", path=str(path))
                continue
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _experience_path(self, session_id: str) -> Path:
        """Get the file path for a session experience."""
        safe_id = session_id.replace("/", "_").replace("..", "_")
        return self._dir / f"{safe_id}.json"

    def _consolidation_path(self, consolidation_id: str) -> Path:
        """Get the file path for a consolidation result."""
        safe_id = consolidation_id.replace("/", "_").replace("..", "_")
        return self._consolidations_dir / f"{safe_id}.json"
