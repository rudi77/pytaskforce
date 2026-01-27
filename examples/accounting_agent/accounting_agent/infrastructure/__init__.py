"""
Infrastructure Layer for Accounting Agent

This package provides infrastructure implementations for:
- Embeddings: Azure OpenAI embedding services
- Persistence: Rule repository and booking history storage

All implementations follow Clean Architecture principles and implement
the protocols defined in accounting_agent.domain.protocols.
"""

from accounting_agent.infrastructure.embeddings import AzureEmbeddingService
from accounting_agent.infrastructure.persistence import BookingHistory, RuleRepository

__all__ = [
    "AzureEmbeddingService",
    "BookingHistory",
    "RuleRepository",
]
