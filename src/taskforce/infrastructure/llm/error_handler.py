"""
Deprecated: Error handling is now simplified in LiteLLMService.

LiteLLM normalizes errors across providers. Provider-specific error parsing
(Azure regex patterns, etc.) is no longer needed. This module is kept for
backward compatibility only.
"""

from typing import Any


class LLMErrorHandler:
    """Deprecated: Error handling is built into LiteLLMService."""

    def __init__(self, provider_config: dict[str, Any] | None = None) -> None:
        pass

    def parse_error(self, error: Exception) -> dict[str, str]:
        """Parse an error into a standardized dict.

        Args:
            error: The exception to parse.

        Returns:
            Dict with error_type and error_message keys.
        """
        return {
            "error_type": type(error).__name__,
            "error_message": str(error),
        }

    def should_retry(self, error: Exception) -> bool:
        """Determine if an error is retryable.

        Args:
            error: The exception to check.

        Returns:
            Always False since retry logic is in LiteLLMService.
        """
        return False
