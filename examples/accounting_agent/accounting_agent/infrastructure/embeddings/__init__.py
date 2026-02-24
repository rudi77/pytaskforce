"""
Embeddings Infrastructure Package

Provides embedding services for semantic similarity matching.
"""

from accounting_agent.infrastructure.embeddings.azure_embeddings import (
    AzureEmbeddingService,
)
from accounting_agent.infrastructure.embeddings.litellm_embeddings import (
    LiteLLMEmbeddingService,
    cosine_similarity,
)

__all__ = ["AzureEmbeddingService", "LiteLLMEmbeddingService", "cosine_similarity"]
