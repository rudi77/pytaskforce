"""Context enricher domain models.

Defines configuration for the SLM-based context enricher that generates
associative intuitions before the ReAct loop starts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EnrichmentCategory(str, Enum):
    """Categories of enrichment the SLM can produce."""

    FACTUAL = "factual"
    """Factual associations from past memories."""

    BEHAVIORAL = "behavioral"
    """Recognised user behaviour patterns and preferences."""

    DREAMED = "dreamed"
    """Optimisations and insights generated during dream cycles."""


@dataclass
class EnricherConfig:
    """Configuration for the SLM context enricher.

    Attributes:
        enabled: Whether enrichment is active (default ``False``).
        model_alias: LLM model alias to use (should point to an SLM).
        max_tokens: Maximum tokens the SLM may generate per enrichment.
        categories: Which enrichment categories to request.
        timeout_seconds: Abort enrichment after this many seconds.
    """

    enabled: bool = False
    model_alias: str = "slm"
    max_tokens: int = 200
    categories: list[EnrichmentCategory] = field(
        default_factory=lambda: [
            EnrichmentCategory.FACTUAL,
            EnrichmentCategory.BEHAVIORAL,
            EnrichmentCategory.DREAMED,
        ]
    )
    timeout_seconds: float = 5.0
