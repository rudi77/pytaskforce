"""
Domain Protocols for Accounting Agent

This module defines protocol interfaces (PEP 544) for the semantic rules engine,
embedding services, and persistence adapters. These protocols enable dependency
injection and clean architecture separation.

All protocols follow the Taskforce framework patterns.
"""

from typing import Protocol, Optional, Any


class EmbeddingProviderProtocol(Protocol):
    """
    Protocol for text embedding services.

    Implementations should provide vector embeddings for text,
    supporting both single texts and batch operations.
    """

    async def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding vector for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors (one per input text)
        """
        ...

    def cosine_similarity(
        self, embedding1: list[float], embedding2: list[float]
    ) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0.0 to 1.0)
        """
        ...


class RuleRepositoryProtocol(Protocol):
    """
    Protocol for accounting rule persistence.

    Implementations should support CRUD operations for accounting rules
    with versioning and activation/deactivation support.
    """

    async def get_active_rules(self) -> list[Any]:
        """
        Get all active accounting rules, sorted by priority.

        Returns:
            List of AccountingRule objects
        """
        ...

    async def get_rule_by_id(self, rule_id: str) -> Optional[Any]:
        """
        Get a specific rule by its ID.

        Args:
            rule_id: Unique rule identifier

        Returns:
            AccountingRule or None if not found
        """
        ...

    async def save_rule(self, rule: Any) -> None:
        """
        Save or update an accounting rule.

        Creates a new version if the rule already exists.

        Args:
            rule: AccountingRule to save
        """
        ...

    async def deactivate_rule(self, rule_id: str) -> bool:
        """
        Deactivate a rule by ID.

        Args:
            rule_id: Rule to deactivate

        Returns:
            True if rule was found and deactivated
        """
        ...

    async def get_rule_history(self, rule_id: str) -> list[Any]:
        """
        Get version history for a rule.

        Args:
            rule_id: Rule ID

        Returns:
            List of rule versions, newest first
        """
        ...


class BookingHistoryProtocol(Protocol):
    """
    Protocol for booking history persistence.

    Supports GoBD-compliant storage of completed bookings
    and semantic search for RAG fallback.
    """

    async def save_booking(self, booking: dict[str, Any]) -> str:
        """
        Save a completed booking to history.

        Args:
            booking: Booking data including invoice details,
                    account assignment, and confidence

        Returns:
            Unique booking ID
        """
        ...

    async def search_similar(
        self,
        query: str,
        vendor_name: Optional[str] = None,
        limit: int = 5
    ) -> list[dict[str, Any]]:
        """
        Search for similar historical bookings.

        Uses semantic similarity on item descriptions and optionally
        filters by vendor name.

        Args:
            query: Search query (item description or invoice text)
            vendor_name: Optional vendor name to filter by
            limit: Maximum number of results

        Returns:
            List of similar bookings with similarity scores
        """
        ...

    async def get_booking_by_id(self, booking_id: str) -> Optional[dict[str, Any]]:
        """
        Get a specific booking by ID.

        Args:
            booking_id: Unique booking identifier

        Returns:
            Booking data or None if not found
        """
        ...

    async def get_vendor_history(
        self,
        vendor_name: str,
        limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        Get booking history for a specific vendor.

        Args:
            vendor_name: Vendor name to search for
            limit: Maximum number of results

        Returns:
            List of bookings for this vendor, newest first
        """
        ...


class LLMProviderProtocol(Protocol):
    """
    Protocol for LLM service integration.

    Compatible with the Taskforce framework's LLMProviderProtocol.
    Used by RAG fallback for generating booking suggestions.
    """

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a completion for the given prompt.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated completion text
        """
        ...

    async def complete_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """
        Generate a JSON-structured completion.

        Args:
            prompt: User prompt requesting JSON output
            system_prompt: Optional system prompt
            temperature: Sampling temperature (lower for consistency)

        Returns:
            Parsed JSON response as dictionary
        """
        ...
