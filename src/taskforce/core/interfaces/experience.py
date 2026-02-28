"""Protocol for experience persistence."""

from __future__ import annotations

from typing import Protocol

from taskforce.core.domain.experience import SessionExperience


class ExperienceStoreProtocol(Protocol):
    """Protocol for storing and retrieving agent session experiences."""

    async def save_experience(self, experience: SessionExperience) -> None:
        """Persist a session experience record.

        Args:
            experience: The session experience to persist.
        """
        ...

    async def load_experience(self, session_id: str) -> SessionExperience | None:
        """Load a session experience by ID.

        Args:
            session_id: The session identifier.

        Returns:
            The session experience, or None if not found.
        """
        ...

    async def list_experiences(
        self,
        limit: int = 50,
        unprocessed_only: bool = False,
    ) -> list[SessionExperience]:
        """List stored experiences.

        Args:
            limit: Maximum number of experiences to return.
            unprocessed_only: If True, only return experiences not yet consolidated.

        Returns:
            List of session experiences, most recent first.
        """
        ...

    async def mark_processed(
        self,
        session_ids: list[str],
        consolidation_id: str,
    ) -> None:
        """Mark experiences as processed by a consolidation run.

        Args:
            session_ids: Session IDs to mark.
            consolidation_id: ID of the consolidation run.
        """
        ...

    async def delete_experience(self, session_id: str) -> bool:
        """Delete a session experience.

        Args:
            session_id: The session identifier.

        Returns:
            True if the experience was deleted, False if not found.
        """
        ...
