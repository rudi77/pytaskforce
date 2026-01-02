"""
State Management Protocol

This module defines the protocol interface for state persistence implementations.
State managers are responsible for persisting and retrieving agent session state,
including conversation history, todo lists, and execution context.

Protocol implementations must be async-compatible and handle concurrent access
to session state safely.
"""

from typing import Any, Protocol


class StateManagerProtocol(Protocol):
    """
    Protocol defining the contract for state persistence.

    Implementations must provide async methods for saving, loading, and managing
    session state. State data is stored as dictionaries containing:
    - session_id: Unique identifier for the session
    - todolist_id: ID of the current todo list
    - answers: User-provided answers to clarification questions
    - pending_question: Current question awaiting user response
    - message_history: Conversation context
    - _version: State version for optimistic locking
    - _updated_at: Last update timestamp

    Thread Safety:
        Implementations must handle concurrent access to the same session_id
        safely, typically using locks or database transactions.

    Error Handling:
        - save_state: Returns False on failure, logs error internally
        - load_state: Returns None if session not found or on error
        - delete_state: Should not raise if session doesn't exist
        - list_sessions: Returns empty list on error
    """

    async def save_state(self, session_id: str, state_data: dict[str, Any]) -> bool:
        """
        Save session state asynchronously with versioning.

        The implementation should:
        1. Acquire a lock for the session_id (if applicable)
        2. Increment the _version field in state_data
        3. Set _updated_at timestamp
        4. Persist the state atomically
        5. Log success/failure

        Args:
            session_id: Unique identifier for the session
            state_data: Dictionary containing session state. Will be modified
                       to include _version and _updated_at fields.

        Returns:
            True if state was saved successfully, False otherwise

        Example:
            >>> state_data = {
            ...     "todolist_id": "abc-123",
            ...     "answers": {"project_name": "myapp"},
            ...     "pending_question": None
            ... }
            >>> success = await state_manager.save_state("session_1", state_data)
            >>> assert success is True
            >>> assert "_version" in state_data
            >>> assert "_updated_at" in state_data
        """
        ...

    async def load_state(self, session_id: str) -> dict[str, Any] | None:
        """
        Load session state by ID asynchronously.

        The implementation should:
        1. Check if session exists
        2. Read state data from storage
        3. Return the state_data dictionary (without metadata wrapper)
        4. Log success/failure

        Args:
            session_id: Unique identifier for the session

        Returns:
            Dictionary containing session state if found, empty dict if session
            exists but has no state, None if session doesn't exist or on error

        Example:
            >>> state = await state_manager.load_state("session_1")
            >>> if state is not None:
            ...     print(f"Version: {state.get('_version', 0)}")
            ...     print(f"TodoList: {state.get('todolist_id')}")
        """
        ...

    async def delete_state(self, session_id: str) -> None:
        """
        Delete session state asynchronously.

        The implementation should:
        1. Remove state file/record for session_id
        2. Clean up any associated locks
        3. Log deletion
        4. Not raise exception if session doesn't exist (idempotent)

        Args:
            session_id: Unique identifier for the session

        Example:
            >>> await state_manager.delete_state("session_1")
            >>> state = await state_manager.load_state("session_1")
            >>> assert state is None
        """
        ...

    async def list_sessions(self) -> list[str]:
        """
        List all session IDs asynchronously.

        The implementation should:
        1. Scan storage for all session state files/records
        2. Extract session_id from each
        3. Return sorted list of session IDs
        4. Return empty list if no sessions or on error

        Returns:
            List of session IDs (strings), sorted alphabetically

        Example:
            >>> sessions = await state_manager.list_sessions()
            >>> print(f"Found {len(sessions)} sessions")
            >>> for session_id in sessions:
            ...     state = await state_manager.load_state(session_id)
            ...     print(f"{session_id}: version {state.get('_version', 0)}")
        """
        ...
