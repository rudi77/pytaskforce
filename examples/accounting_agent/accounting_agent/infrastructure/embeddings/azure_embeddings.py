"""
Azure OpenAI Embedding Service

Provides text embeddings using Azure OpenAI's text-embedding-ada-002 model.
Implements EmbeddingProviderProtocol with caching support.
"""

import hashlib
import math
import os
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class EmbeddingCache:
    """
    Simple in-memory cache for embeddings.

    Reduces API calls for repeated text embedding requests.
    """

    def __init__(self, max_size: int = 1000):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of embeddings to cache
        """
        self._cache: dict[str, list[float]] = {}
        self._max_size = max_size

    def _hash_text(self, text: str) -> str:
        """Create hash key for text."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def get(self, text: str) -> Optional[list[float]]:
        """Get cached embedding for text."""
        key = self._hash_text(text)
        return self._cache.get(key)

    def put(self, text: str, embedding: list[float]) -> None:
        """Cache embedding for text."""
        if len(self._cache) >= self._max_size:
            # Simple eviction: remove oldest entry
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        key = self._hash_text(text)
        self._cache[key] = embedding

    def clear(self) -> None:
        """Clear all cached embeddings."""
        self._cache.clear()


class AzureEmbeddingService:
    """
    Azure OpenAI embedding service implementation.

    Uses text-embedding-ada-002 for generating embeddings.
    Implements EmbeddingProviderProtocol.

    Configuration via environment variables:
    - AZURE_OPENAI_API_KEY: API key for Azure OpenAI
    - AZURE_OPENAI_ENDPOINT: Azure OpenAI endpoint URL
    - AZURE_OPENAI_EMBEDDING_DEPLOYMENT: Deployment name (default: text-embedding-ada-002)
    - AZURE_OPENAI_API_VERSION: API version (default: 2024-02-01)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        deployment_name: Optional[str] = None,
        api_version: str = "2024-02-01",
        cache_enabled: bool = True,
        cache_max_size: int = 1000,
    ):
        """
        Initialize Azure embedding service.

        Args:
            api_key: Azure OpenAI API key (or from env AZURE_OPENAI_API_KEY)
            endpoint: Azure OpenAI endpoint (or from env AZURE_OPENAI_ENDPOINT)
            deployment_name: Embedding deployment name (or from env)
            api_version: Azure OpenAI API version
            cache_enabled: Whether to cache embeddings
            cache_max_size: Maximum cache size
        """
        self._api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self._endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        self._deployment = deployment_name or os.environ.get(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"
        )
        self._api_version = api_version

        self._cache_enabled = cache_enabled
        self._cache = EmbeddingCache(max_size=cache_max_size) if cache_enabled else None

        self._client: Optional["openai.AsyncAzureOpenAI"] = None

        if not self._api_key:
            logger.warning("azure_embedding.no_api_key", hint="Set AZURE_OPENAI_API_KEY")
        if not self._endpoint:
            logger.warning("azure_embedding.no_endpoint", hint="Set AZURE_OPENAI_ENDPOINT")

    async def _get_client(self) -> "openai.AsyncAzureOpenAI":
        """Get or create the Azure OpenAI async client."""
        if self._client is None:
            try:
                import openai

                self._client = openai.AsyncAzureOpenAI(
                    api_key=self._api_key,
                    api_version=self._api_version,
                    azure_endpoint=self._endpoint,
                )
            except ImportError:
                raise ImportError(
                    "openai package required for Azure embeddings. "
                    "Install with: pip install openai"
                )
        return self._client

    async def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding vector for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        # Check cache first
        if self._cache_enabled and self._cache:
            cached = self._cache.get(text)
            if cached:
                logger.debug("azure_embedding.cache_hit", text_length=len(text))
                return cached

        client = await self._get_client()

        try:
            response = await client.embeddings.create(
                model=self._deployment,
                input=text,
            )
            embedding = response.data[0].embedding

            # Cache the result
            if self._cache_enabled and self._cache:
                self._cache.put(text, embedding)

            logger.debug(
                "azure_embedding.generated",
                text_length=len(text),
                embedding_dim=len(embedding),
            )
            return embedding

        except Exception as e:
            logger.error(
                "azure_embedding.error",
                error=str(e),
                text_length=len(text),
            )
            raise

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for multiple texts.

        Uses batching for efficiency and respects Azure API limits.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors (one per input text)
        """
        if not texts:
            return []

        # Check cache for each text
        results: list[Optional[list[float]]] = [None] * len(texts)
        texts_to_embed: list[tuple[int, str]] = []

        if self._cache_enabled and self._cache:
            for i, text in enumerate(texts):
                cached = self._cache.get(text)
                if cached:
                    results[i] = cached
                else:
                    texts_to_embed.append((i, text))
        else:
            texts_to_embed = list(enumerate(texts))

        # If all cached, return early
        if not texts_to_embed:
            logger.debug("azure_embedding.batch_all_cached", count=len(texts))
            return [r for r in results if r is not None]

        client = await self._get_client()

        # Azure has limits on batch size, process in chunks
        batch_size = 16  # Azure embedding API limit
        for chunk_start in range(0, len(texts_to_embed), batch_size):
            chunk = texts_to_embed[chunk_start : chunk_start + batch_size]
            chunk_indices = [idx for idx, _ in chunk]
            chunk_texts = [text for _, text in chunk]

            try:
                response = await client.embeddings.create(
                    model=self._deployment,
                    input=chunk_texts,
                )

                for i, emb_data in enumerate(response.data):
                    original_idx = chunk_indices[i]
                    embedding = emb_data.embedding
                    results[original_idx] = embedding

                    # Cache the result
                    if self._cache_enabled and self._cache:
                        self._cache.put(chunk_texts[i], embedding)

            except Exception as e:
                logger.error(
                    "azure_embedding.batch_error",
                    error=str(e),
                    batch_size=len(chunk_texts),
                )
                raise

        logger.debug(
            "azure_embedding.batch_complete",
            total=len(texts),
            from_cache=len(texts) - len(texts_to_embed),
            from_api=len(texts_to_embed),
        )

        return [r for r in results if r is not None]

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
        if len(embedding1) != len(embedding2):
            raise ValueError(
                f"Embedding dimensions must match: {len(embedding1)} vs {len(embedding2)}"
            )

        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        norm1 = math.sqrt(sum(a * a for a in embedding1))
        norm2 = math.sqrt(sum(b * b for b in embedding2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    async def find_most_similar(
        self,
        query_embedding: list[float],
        candidate_embeddings: list[list[float]],
        threshold: float = 0.0,
    ) -> list[tuple[int, float]]:
        """
        Find most similar embeddings to a query embedding.

        Args:
            query_embedding: Query embedding vector
            candidate_embeddings: List of candidate embedding vectors
            threshold: Minimum similarity threshold

        Returns:
            List of (index, similarity) tuples, sorted by similarity descending
        """
        similarities = []
        for i, candidate in enumerate(candidate_embeddings):
            sim = self.cosine_similarity(query_embedding, candidate)
            if sim >= threshold:
                similarities.append((i, sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        if self._cache:
            self._cache.clear()
            logger.info("azure_embedding.cache_cleared")
