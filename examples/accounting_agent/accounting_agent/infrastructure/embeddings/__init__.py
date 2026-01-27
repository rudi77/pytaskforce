"""
Embeddings Infrastructure Package

Provides embedding services for semantic similarity matching.
"""

from accounting_agent.infrastructure.embeddings.azure_embeddings import (
    AzureEmbeddingService,
)

__all__ = ["AzureEmbeddingService"]
