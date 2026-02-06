"""
Deprecated: Error handling is now simplified in LiteLLMService.

LiteLLM normalizes errors across providers. Provider-specific error parsing
(Azure regex patterns, etc.) is no longer needed. This module is kept for
backward compatibility only.
"""


class LLMErrorHandler:
    """Deprecated: Error handling is built into LiteLLMService."""

    def __init__(self, provider_config=None):
        pass

    def parse_error(self, error):
        return {
            "error_type": type(error).__name__,
            "error_message": str(error),
        }

    def should_retry(self, error):
        return False
