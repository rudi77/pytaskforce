"""Protocol for text embedding services."""

from __future__ import annotations

from typing import Protocol


class EmbeddingProviderProtocol(Protocol):
    """Protocol for text embedding services.

    Implementations generate vector embeddings for text, supporting both
    single texts and batch operations.  Used by the memory system for
    semantic search.
    """

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for a single text.

        Args:
            text: Text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors (one per input text, same order).
        """
        ...
