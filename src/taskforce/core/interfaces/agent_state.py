"""
Agent State Protocol

Defines the contract for singleton agent state persistence in the persistent
agent architecture (ADR-016). Unlike ``StateManagerProtocol`` which is keyed
by ``session_id``, this protocol manages a single, global agent state.
"""

from __future__ import annotations

from typing import Any, Protocol


class AgentStateProtocol(Protocol):
    """Persistent state for the singleton agent.

    Stores agent-global runtime data such as active conversation IDs,
    scheduler state references, and configuration overrides. This is
    deliberately *not* keyed by session — there is exactly one agent.
    """

    async def save(self, state_data: dict[str, Any]) -> None:
        """Persist the agent's global state.

        Args:
            state_data: Arbitrary state dictionary. The implementation
                        should handle versioning and timestamps internally.
        """
        ...

    async def load(self) -> dict[str, Any] | None:
        """Load the agent's global state.

        Returns:
            The state dictionary, or ``None`` if no state has been persisted yet.
        """
        ...
